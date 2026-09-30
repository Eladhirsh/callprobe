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


def _result_status(content: Any, side_effect: bool) -> str:
    """Recognize explicit outcomes, refusing to infer successful writes from silence."""
    if isinstance(content, str):
        text = content.strip()
        try:
            content = json.loads(text)
        except ValueError:
            low = text.lower().rstrip(".! ")
            if low.startswith(("error", "exception", "failed", "traceback")):
                return "error"
            if low in {"ok", "success", "sent", "done", "completed", "cancelled", "deleted"}:
                return "ok"
    if isinstance(content, dict):
        if (
            content.get("error")
            or content.get("is_error") is True
            or content.get("isError") is True
            or content.get("success") is False
            or content.get("ok") is False
        ):
            return "error"
        status = str(content.get("status", "")).lower()
        code = content.get("status_code")
        if status in {"error", "failed", "failure"} or (
            isinstance(code, int) and not isinstance(code, bool) and code >= 400
        ):
            return "error"
        if (
            content.get("success") is True
            or content.get("ok") is True
            or status in {"ok", "success", "sent", "completed", "cancelled", "deleted"}
        ):
            return "ok"
    if content is not None and not side_effect:
        return "ok"
    raise ValueError(
        "Unrecognized or missing tool outcome; normalize this result to native "
        "status 'ok' or 'error' before checking it. Success was not assumed."
    )


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
                "parameters": fn.get("parameters", {}),
                "side_effect": t.get("side_effect", guess_side_effect(name)),
            }
        )
    known = {t["name"] for t in tools}

    # Calls become completed events only when their result arrives. A later
    # result cannot back an earlier completion claim.
    pending: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()
    side_effects = {t["name"]: t["side_effect"] for t in tools}

    events: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            cid = m.get("tool_call_id")
            if cid not in pending:
                raise ValueError(f"Tool result has no pending call: {cid!r}")
            event = pending.pop(cid)
            event["result"] = m.get("content")
            event["status"] = _result_status(event["result"], side_effects[event["tool"]])
            events.append(event)
            completed.add(cid)
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
            name = fn.get("name", "unknown")
            if name not in known:
                tools.append({"name": name, "side_effect": guess_side_effect(name)})
                known.add(name)
            side_effects.setdefault(name, guess_side_effect(name))
            cid = tc.get("id")
            if not isinstance(cid, str) or not cid or cid in pending or cid in completed:
                raise ValueError("Tool calls require unique nonempty string IDs.")
            pending[cid] = {"type": "tool_call", "id": cid, "tool": name, "args": args}
    if pending:
        raise ValueError("Missing tool results; success was not assumed for: " + ", ".join(pending))
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
