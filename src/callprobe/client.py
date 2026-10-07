"""A deliberately small OpenAI-compatible client.

We avoid the official SDK so that any endpoint that speaks
/v1/chat/completions works: Ollama, LM Studio, llama.cpp server, vLLM,
or a hosted provider.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import Call

DEFAULT_RETRIES = 3


def probe_server_version(endpoint: str, timeout: float = 2.0) -> tuple[str | None, str | None]:
    """Best-effort server identification, for provenance in RunConfig.

    Recognize Ollama's /api/version or a llama.cpp /props response.
    Missing, protected, or unrecognized metadata leaves both fields null.
    """
    parts = urlsplit(endpoint)
    root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    def metadata(path: str) -> dict:
        try:
            response = httpx.get(f"{root}{path}", timeout=timeout)
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else {}
        except Exception:  # noqa: BLE001 - purely informational
            return {}

    version = metadata("/api/version").get("version")
    if isinstance(version, str) and version.strip():
        return "ollama", version

    props = metadata("/props")
    build = props.get("build_info")
    # A generic application's /props endpoint is not enough to identify it.
    # Recognize the build convention plus the server's generation/template fields.
    if (isinstance(build, str) and re.fullmatch(r"b\d+-[0-9a-fA-F]{7,40}(?:-dirty)?", build)
            and isinstance(props.get("default_generation_settings"), dict)
            and isinstance(props.get("chat_template"), str)
            and type(props.get("total_slots")) is int and props["total_slots"] > 0):
        return "llama.cpp", build
    return None, None


@dataclass
class Completion:
    calls: list[Call] = field(default_factory=list)
    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    finish_reason: str = ""
    # Some servers put chain of thought in its own field rather than content.
    reasoning: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _is_retryable(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


class ChatClient:
    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        retries: int = DEFAULT_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(timeout=timeout, headers=headers, transport=transport)
        self.retries = retries

    def close(self) -> None:
        self._client.close()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        """Exponential backoff with full jitter, honoring Retry-After."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
                if math.isfinite(delay):
                    return max(0.0, delay)
            except ValueError:
                pass
        ceiling = min(20.0, 0.5 * (2**attempt))
        return random.uniform(0, ceiling)

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> Completion:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        started = time.perf_counter()
        attempts = self.retries + 1
        for attempt in range(attempts):
            last_attempt = attempt + 1 == attempts
            try:
                response = self._client.post(
                    f"{self.endpoint}/chat/completions", json=payload
                )
            except httpx.TransportError as exc:
                if last_attempt:
                    return Completion(
                        latency_ms=(time.perf_counter() - started) * 1000,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                time.sleep(self._backoff(attempt, None))
                continue

            if _is_retryable(response.status_code) and not last_attempt:
                time.sleep(self._backoff(attempt, response.headers.get("Retry-After")))
                continue

            try:
                response.raise_for_status()
                body = response.json()
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                return Completion(
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=f"{type(exc).__name__}: {exc}",
                )

            try:
                return parse_completion(body, (time.perf_counter() - started) * 1000)
            except (AttributeError, TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
                # A malformed provider response is a request error, not a model
                # verdict. Do not abort the suite or expose response contents.
                return Completion(
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=f"invalid chat completion response ({type(exc).__name__})",
                )

        raise AssertionError("unreachable: loop always returns or retries")


def _token_count(value: Any) -> int:
    """Keep compatible integer representations without truncation or coercing flags."""
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("token counts must be nonnegative integers")
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        raise ValueError("token counts must be nonnegative integers")
    try:
        count = int(value)
    except (ValueError, OverflowError):
        raise ValueError("token counts must be nonnegative integers") from None
    if count < 0:
        raise ValueError("token counts must be nonnegative integers")
    return count


def _argument_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("tool arguments contain duplicate object keys")
        result[key] = value
    return result


def _argument_constant(_value: str) -> Any:
    raise ValueError("tool arguments contain nonfinite numbers")


def _argument_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("tool arguments contain nonfinite numbers")
    return number


def parse_completion(body: dict[str, Any], latency_ms: float) -> Completion:
    """Turn a chat completion body into calls, tolerating provider quirks."""
    if not isinstance(body, dict):
        raise ValueError("response must be an object")
    choices = body.get("choices")
    if (not isinstance(choices, list) or not choices
            or not isinstance(choices[0], dict)
            or not isinstance(choices[0].get("message"), dict)):
        raise ValueError("response must contain a choice with a message")
    usage = body.get("usage")
    if usage is None:
        usage = {}
    elif not isinstance(usage, dict):
        raise ValueError("usage must be an object")
    choice = choices[0]
    message = choice["message"]
    # Validate before applying fallbacks: false, zero, and empty containers
    # are malformed text, not evidence of a successful no-call response.
    text_values = [message.get(field) for field in ("content", "reasoning", "reasoning_content")]
    text_values.append(choice.get("finish_reason"))
    if any(value is not None and not isinstance(value, str) for value in text_values):
        raise ValueError("message text and finish reason must be strings or null")
    finish_reason = choice.get("finish_reason") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
        raise ValueError("tool_calls must be an array")
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        raise ValueError("message refusal must be a string or null")
    # Legacy calls are not normalized by this adapter. Preserve the failure
    # outside raw metadata so recording export cannot erase a proposed call
    # and turn it into a successful abstention, including mixed envelopes.
    error = None
    if message.get("function_call") is not None or finish_reason == "function_call":
        error = "unsupported legacy function-call response"
    elif refusal:
        error = "provider refused the completion"

    calls: list[Call] = []
    for entry in message.get("tool_calls") or []:
        function = entry.get("function") or {}
        raw_args = function.get("arguments")
        if raw_args is not None and not isinstance(raw_args, (str, dict)):
            raise ValueError("tool arguments must be a string, object, or null")
        if isinstance(raw_args, dict):
            calls.append(
                Call(
                    id=entry.get("id"),
                    name=function.get("name", ""),
                    arguments=raw_args,
                    raw_arguments=json.dumps(raw_args),
                )
            )
            continue
        raw_args = raw_args or ""
        try:
            parsed = json.loads(
                raw_args, object_pairs_hook=_argument_object,
                parse_constant=_argument_constant, parse_float=_argument_float,
            ) if raw_args.strip() else {}
            if not isinstance(parsed, dict):
                raise ValueError("arguments were not a JSON object")
            calls.append(
                Call(
                    id=entry.get("id"),
                    name=function.get("name", ""),
                    arguments=parsed,
                    raw_arguments=raw_args,
                )
            )
        except Exception as exc:  # noqa: BLE001
            calls.append(
                Call(
                    id=entry.get("id"),
                    name=function.get("name", ""),
                    raw_arguments=raw_args,
                    parse_error=str(exc),
                )
            )

    return Completion(
        calls=calls,
        content=message.get("content") or "",
        prompt_tokens=_token_count(usage.get("prompt_tokens")),
        completion_tokens=_token_count(usage.get("completion_tokens")),
        latency_ms=latency_ms,
        error=error,
        finish_reason=finish_reason,
        reasoning=reasoning,
        raw=body,
    )
