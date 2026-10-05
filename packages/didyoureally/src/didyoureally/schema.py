"""Trace and claim data model.

A trace is the ordered record of one agent session: the tools it had, the
tool calls it made, and the messages exchanged with the user. Every event
carries an ``index`` so claims can be checked only against calls that
happened before the message that made them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .strict_json import ensure_finite_numbers, loads

Status = Literal["ok", "error"]


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _array(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return value


def _name(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


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
        data = _object(data, "trace")
        ensure_finite_numbers(data)
        tools: dict[str, ToolSpec] = {}
        for i, raw in enumerate(_array(data.get("tools", []), "tools")):
            tool = _object(raw, f"tool {i}")
            name = _name(tool.get("name"), f"tool {i} name")
            if name in tools:
                raise ValueError("Tool definitions require unique names")
            side_effect = tool.get("side_effect", True)
            if type(side_effect) is not bool:
                raise ValueError(f"tool {i} side_effect must be a boolean")
            tools[name] = ToolSpec(
                name=name,
                side_effect=side_effect,
                description=_text(tool.get("description", ""), f"tool {i} description"),
                parameters=dict(_object(tool.get("parameters", {}), f"tool {i} parameters")),
            )

        calls: list[ToolCall] = []
        messages: list[Message] = []
        for i, raw in enumerate(_array(data.get("events", []), "events")):
            ev = _object(raw, f"event {i}")
            kind = ev.get("type")
            if kind == "tool_call":
                status = ev.get("status", "ok")
                if status not in ("ok", "error"):
                    raise ValueError(f"event {i} status must be 'ok' or 'error'")
                name = _name(ev.get("tool"), f"event {i} tool")
                calls.append(
                    ToolCall(
                        id=_name(ev.get("id", f"call_{i}"), f"event {i} id"),
                        tool=name,
                        args=dict(_object(ev.get("args", {}), f"event {i} args")),
                        status=status,
                        result=ev.get("result"),
                        index=i,
                    )
                )
                tools.setdefault(name, ToolSpec(name=name))
            elif kind == "message":
                role = ev.get("role")
                if role not in ("user", "assistant", "system", "developer", "tool"):
                    raise ValueError(f"event {i} role is not supported")
                messages.append(
                    Message(role=role, content=_text(ev.get("content", ""), f"event {i} content"), index=i)
                )
            else:
                raise ValueError(f"event {i} type must be 'tool_call' or 'message'")
        trace = cls(
            id=_name(data.get("id", "trace"), "trace id"), tools=tools, calls=calls, messages=messages
        )
        trace.validate_call_ids()
        return trace

    def validate_call_ids(self) -> None:
        """Call identity drives evidence allocation, including for directly constructed traces."""
        seen = set()
        for call in self.calls:
            call_id = _name(call.id, "call id")
            if call_id in seen:
                raise ValueError("Tool calls require unique IDs")
            seen.add(call_id)

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
    group_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        data = _object(data, "claim")
        ensure_finite_numbers(data)
        claim = cls(
            text=data.get("text"),
            tool=data.get("tool"),
            args=dict(_object(data.get("args", {}), "claim args")),
            message_index=data.get("message_index"),
            group_id=data.get("group_id"),
        )
        claim.validate()
        return claim

    def validate(self) -> None:
        """Validate reviewed and directly constructed claims without coercing evidence."""
        _name(self.text, "claim text")
        if self.tool is not None:
            _name(self.tool, "claim tool")
        _object(self.args, "claim args")
        ensure_finite_numbers(self.args)
        if self.message_index is not None and (type(self.message_index) is not int or self.message_index < 0):
            raise ValueError("claim message_index must be a nonnegative integer or null")
        if self.group_id is not None:
            _name(self.group_id, "claim group_id")


def validate_claims(claims: list[Claim], trace: Trace | None = None) -> None:
    valid_indices = {m.index for m in trace.assistant_messages()} if trace is not None else None
    for claim in _array(claims, "claims"):
        if not isinstance(claim, Claim):
            raise ValueError("claims must contain Claim objects")
        claim.validate()
        if (
            valid_indices is not None
            and claim.message_index is not None
            and claim.message_index not in valid_indices
        ):
            raise ValueError("claim message_index must identify a nonempty assistant message")


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())
