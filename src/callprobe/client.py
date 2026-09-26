"""A deliberately small OpenAI-compatible client.

We avoid the official SDK so that any endpoint that speaks
/v1/chat/completions works: Ollama, LM Studio, llama.cpp server, vLLM,
or a hosted provider.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import Call

DEFAULT_RETRIES = 3


def probe_server_version(endpoint: str, timeout: float = 2.0) -> tuple[str | None, str | None]:
    """Best-effort server identification, for provenance in RunConfig.

    Only Ollama's /api/version is checked. Any other server, or no
    response, leaves both fields null rather than guessing.
    """
    parts = urlsplit(endpoint)
    root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    try:
        response = httpx.get(f"{root}/api/version", timeout=timeout)
        response.raise_for_status()
        version = response.json().get("version")
    except Exception:  # noqa: BLE001 - purely informational
        return None, None
    return ("ollama", version) if version else (None, None)


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


def parse_completion(body: dict[str, Any], latency_ms: float) -> Completion:
    """Turn a chat completion body into calls, tolerating provider quirks."""
    if not isinstance(body, dict):
        raise ValueError("response must be an object")
    choices = body.get("choices")
    if (not isinstance(choices, list) or not choices
            or not isinstance(choices[0], dict)
            or not isinstance(choices[0].get("message"), dict)):
        raise ValueError("response must contain a choice with a message")
    usage = body.get("usage") or {}
    choices = body.get("choices") or [{}]
    choice = choices[0] or {}
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    if not all(isinstance(value, str) for value in (
        message.get("content") or "", finish_reason, reasoning
    )):
        raise ValueError("message text and finish reason must be strings")
    if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
        raise ValueError("tool_calls must be an array")

    calls: list[Call] = []
    for entry in message.get("tool_calls") or []:
        function = entry.get("function") or {}
        raw_args = function.get("arguments")
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
            parsed = json.loads(raw_args) if raw_args.strip() else {}
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
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        latency_ms=latency_ms,
        finish_reason=finish_reason,
        reasoning=reasoning,
        raw=body,
    )
