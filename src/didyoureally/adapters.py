"""Convert common trace formats into the native :class:`Trace`.

Supported today:

* native: ``{"id", "tools", "events"}``
* OpenAI chat messages: a list of messages (or ``{"messages": [...], "tools": [...]}``)
  where assistant turns carry ``tool_calls`` and results come back as ``role: "tool"``.
"""

from __future__ import annotations

import json
from typing import Any

from .schema import Trace

READ_ONLY_PREFIXES = (
    "get_",
    "list_",
    "search_",
    "read_",
    "lookup_",
    "fetch_",
    "find_",
    "query_",
    "check_",
    "view_",
    "describe_",
)


def guess_side_effect(tool: str) -> bool:
    """Tools that only read are assumed side-effect free. Override in the trace."""
    return not tool.lower().startswith(READ_ONLY_PREFIXES)


def _looks_like_error(content: Any) -> bool:
    if isinstance(content, str):
        text = content.strip()
        try:
            content = json.loads(text)
        except (ValueError, TypeError):
            low = text.lower()
            return low.startswith(("error", "exception", "failed", "traceback"))
    if isinstance(content, dict):
        if content.get("error") or content.get("is_error"):
            return True
        status = str(content.get("status", "")).lower()
        return status in {"error", "failed", "failure"}
    return False


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def from_openai_messages(data: Any, trace_id: str = "trace") -> Trace:
    if isinstance(data, dict):
        messages = data.get("messages", [])
        tool_defs = data.get("tools", [])
        trace_id = str(data.get("id", trace_id))
    else:
        messages, tool_defs = data, []

    tools: list[dict[str, Any]] = []
    for t in tool_defs:
        fn = t.get("function", t)
        name = fn["name"]
        tools.append(
            {
                "name": name,
                "description": fn.get("description", ""),
                "side_effect": t.get("side_effect", guess_side_effect(name)),
            }
        )
    known = {t["name"] for t in tools}

    results: dict[str, Any] = {
        m["tool_call_id"]: m.get("content")
        for m in messages
        if m.get("role") == "tool" and "tool_call_id" in m
    }

    events: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            continue
        text = _content_text(m.get("content"))
        if role in ("user", "assistant") and text.strip():
            events.append({"type": "message", "role": role, "content": text})
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except ValueError:
                args = {"_raw": raw}
            result = results.get(tc.get("id"))
            name = fn.get("name", "unknown")
            if name not in known:
                tools.append({"name": name, "side_effect": guess_side_effect(name)})
                known.add(name)
            events.append(
                {
                    "type": "tool_call",
                    "id": tc.get("id"),
                    "tool": name,
                    "args": args,
                    "status": "error" if _looks_like_error(result) else "ok",
                    "result": result,
                }
            )
    return Trace.from_dict({"id": trace_id, "tools": tools, "events": events})


def load_trace(data: Any, trace_id: str = "trace") -> Trace:
    """Detect the format and build a Trace."""
    if isinstance(data, dict) and "trace" in data and isinstance(data["trace"], dict):
        data = data["trace"]  # benchmark case file
    if isinstance(data, dict) and "events" in data:
        return Trace.from_dict(data)
    if isinstance(data, list) or (isinstance(data, dict) and "messages" in data):
        return from_openai_messages(data, trace_id)
    raise ValueError("Unrecognized trace format: expected native 'events' or OpenAI 'messages'.")
