"""Trace and claim data model.

A trace is the ordered record of one agent session: the tools it had, the
tool calls it made, and the messages exchanged with the user. Every event
carries an ``index`` so claims can be checked only against calls that
happened before the message that made them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Status = Literal["ok", "error"]


@dataclass
class ToolSpec:
    name: str
    side_effect: bool = True
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    id: str
    tool: str
    args: dict[str, Any]
    status: Status = "ok"
    result: Any = None
    index: int = 0


@dataclass
class Message:
    role: str
    content: str
    index: int = 0


@dataclass
class Trace:
    id: str
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    calls: list[ToolCall] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)

    # ---- construction -------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trace:
        """Build from the native format: ``{"id", "tools", "events"}``."""
        tools: dict[str, ToolSpec] = {}
        for t in data.get("tools", []):
            spec = ToolSpec(
                name=t["name"],
                side_effect=bool(t.get("side_effect", True)),
                description=t.get("description", ""),
                parameters=dict(t.get("parameters") or {}),
            )
            tools[spec.name] = spec

        calls: list[ToolCall] = []
        messages: list[Message] = []
        for i, ev in enumerate(data.get("events", [])):
            kind = ev.get("type")
            if kind == "tool_call":
                status = ev.get("status", "ok")
                if status not in ("ok", "error"):
                    raise ValueError(f"event {i}: status must be 'ok' or 'error', got {status!r}")
                calls.append(
                    ToolCall(
                        id=str(ev.get("id", f"call_{i}")),
                        tool=ev["tool"],
                        args=dict(ev.get("args", {})),
                        status=status,
                        result=ev.get("result"),
                        index=i,
                    )
                )
                tools.setdefault(ev["tool"], ToolSpec(name=ev["tool"]))
            elif kind == "message":
                messages.append(Message(role=ev["role"], content=ev.get("content", ""), index=i))
            else:
                raise ValueError(f"event {i}: unknown type {kind!r}")
        return cls(id=str(data.get("id", "trace")), tools=tools, calls=calls, messages=messages)

    def to_dict(self) -> dict[str, Any]:
        events: list[tuple[int, dict[str, Any]]] = []
        for c in self.calls:
            events.append(
                (
                    c.index,
                    {
                        "type": "tool_call",
                        "id": c.id,
                        "tool": c.tool,
                        "args": c.args,
                        "status": c.status,
                        "result": c.result,
                    },
                )
            )
        for m in self.messages:
            events.append((m.index, {"type": "message", "role": m.role, "content": m.content}))
        events.sort(key=lambda e: e[0])
        return {
            "id": self.id,
            "tools": [asdict(t) for t in self.tools.values()],
            "events": [e for _, e in events],
        }

    # ---- queries ------------------------------------------------------

    def assistant_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "assistant" and m.content.strip()]

    def is_side_effect(self, tool: str) -> bool:
        spec = self.tools.get(tool)
        return True if spec is None else spec.side_effect


@dataclass
class Claim:
    """One statement the agent made to the user about an action it took.

    ``tool`` is the tool that should back the claim, or ``None`` when the
    claimed action maps to no available tool (which is itself a finding).
    ``args`` holds only the details the agent actually stated.
    """

    text: str
    tool: str | None
    args: dict[str, Any] = field(default_factory=dict)
    message_index: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        return cls(
            text=data["text"],
            tool=data.get("tool"),
            args=dict(data.get("args", {})),
            message_index=data.get("message_index"),
        )


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
