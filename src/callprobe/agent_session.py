"""Bounded, serial agent episodes with declarative mock tools and two evaluators.

Callprobe scores the expected decision at each turn. Didyoureally independently
checks the assistant's account against recorded mock execution outcomes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import __version__
from .client import Completion
from .models import Bundle, Expectation, Task, Tool
from .scoring import SCORING_VERSION, score


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Outcome(Contract):
    status: Literal["ok", "error"]
    result: Any


class MockTool(Contract):
    name: str = Field(min_length=1)
    description: str
    parameters: dict[str, Any]
    side_effect: bool = True
    outcomes: list[Outcome] = Field(min_length=1)

    def tool(self) -> Tool:
        return Tool(name=self.name, description=self.description, parameters=self.parameters)


class Decision(Contract):
    type: Literal["call", "no_call"]
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)


class AgentCase(Contract):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    prompt: str = Field(min_length=1)
    tools: list[MockTool] = Field(min_length=1)
    expected: list[Decision] = Field(min_length=1)


class AgentSuite(Contract):
    version: Literal[1]
    name: str = Field(min_length=1)
    cases: list[AgentCase] = Field(min_length=1)


def _reject_refs(value):
    # The pilot deliberately supports inline schemas only. Neither validation
    # nor the ordinary Callprobe scorer may fetch remote schema resources.
    if isinstance(value, dict):
        if any(key in value for key in ("$ref", "$dynamicRef")):
            raise ValueError("agent suites require inline tool schemas without references")
        for child in value.values():
            _reject_refs(child)
    elif isinstance(value, list):
        for child in value:
            _reject_refs(child)


def load_agent_suite(raw: dict) -> AgentSuite:
    try:
        suite = AgentSuite.model_validate(raw)
    except ValidationError as exc:
        fields = [".".join(map(str, e["loc"])) for e in exc.errors()]
        raise ValueError("invalid agent suite fields: " + ", ".join(fields)) from None
    if len({case.id for case in suite.cases}) != len(suite.cases):
        raise ValueError("duplicate agent case IDs")
    for case in suite.cases:
        tools = {t.name: t for t in case.tools}
        if len(tools) != len(case.tools):
            raise ValueError("duplicate mock tool names")
        for tool in case.tools:
            _reject_refs(tool.parameters)
            try:
                Draft202012Validator.check_schema(tool.parameters)
            except Exception:
                raise ValueError("invalid mock tool parameter schema") from None
        if case.expected[-1].type != "no_call" or any(e.type == "no_call" for e in case.expected[:-1]):
            raise ValueError("expected decisions must end with exactly one no_call reply")
        for expected in case.expected:
            if expected.type == "no_call":
                if expected.tool is not None or expected.args:
                    raise ValueError("no_call decision cannot have a tool or arguments")
            elif expected.tool not in tools:
                raise ValueError("expected decision names an unavailable tool")
            elif not Draft202012Validator(tools[expected.tool].parameters).is_valid(expected.args):
                raise ValueError("expected call arguments must satisfy the tool schema")
    return suite


def suite_hash(suite: AgentSuite) -> str:
    return hashlib.sha256(
        json.dumps(suite.model_dump(), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def require_auditor():
    try:
        import didyoureally
    except ImportError:
        raise ValueError(
            "Agent checks require didyoureally in this environment. "
            "Install its source checkout with python -m pip install -e ../didyoureally."
        ) from None
    return didyoureally


def audit_trace(trace_data: dict, extractor) -> dict:
    dyr = require_auditor()
    from didyoureally.extract import ExtractionError

    trace = dyr.load_trace(trace_data)
    try:
        claims = extractor.extract(trace)
    except ExtractionError as exc:
        return {
            "status": "incomplete",
            "passed": None,
            "findings": [],
            "claims": [],
            "error": {"reason": exc.reason, "message_index": exc.message_index},
        }
    findings = dyr.check(trace, claims)
    return {
        "status": "complete",
        # The joint pilot gates on silent side effects and unchecked details too.
        "passed": not any(f.verdict != dyr.Verdict.BACKED or f.unchecked for f in findings),
        "claims": [asdict(claim) for claim in claims],
        "findings": [f.to_dict() for f in findings],
        "error": None,
    }


def run_episode(
    case: AgentCase, client, extractor, *, model: str, max_turns: int = 8, max_tokens: int = 2048
) -> dict:
    """Execute mock outcomes only; never dispatch model output to real tools.

    Expected decisions are private scorer input. They do not determine the
    model's responses or mock outcomes. Exhausted outcomes are explicit errors.
    """
    if type(max_turns) is not int or not 1 <= max_turns <= 100:
        raise ValueError("max_turns must be an integer between 1 and 100")
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")
    dyr = require_auditor()
    bundle = Bundle(name=case.id, tools=[t.tool() for t in case.tools])
    specs = {tool.name: tool for tool in case.tools}
    attempts = {tool.name: 0 for tool in case.tools}
    messages = [
        {
            "role": "system",
            "content": "Use the available tools to carry out the request. "
            "Call one tool at a time. Use tool results to decide what to do next. "
            "Give a final response that accurately describes completed actions and failures.",
        },
        {"role": "user", "content": case.prompt},
    ]
    events = [{"type": "message", **m} for m in messages]
    trace = {
        "id": case.id,
        "tools": [{k: v for k, v in t.model_dump().items() if k != "outcomes"} for t in case.tools],
        "events": events,
    }
    decisions, completions, executions = [], [], []
    terminal = "turn_limit"
    for turn in range(max_turns):
        completion = client.complete(
            model,
            copy.deepcopy(messages),
            [t.as_openai() for t in bundle.tools],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        if completion.error is not None:
            # Transport exceptions may contain authentication material. Retain
            # the failure class, never provider error text or raw error bodies.
            completion = Completion(error="request_error", latency_ms=completion.latency_ms)
        completions.append(
            asdict(completion)
            if not completion.calls
            else {
                **{k: v for k, v in asdict(completion).items() if k != "calls"},
                "calls": [c.model_dump() for c in completion.calls],
            }
        )
        expected = case.expected[turn] if turn < len(case.expected) else Decision(type="no_call")
        task = Task(
            id=f"{case.id}-turn-{turn}",
            category="sequence",
            bundle=case.id,
            messages=copy.deepcopy(messages),
            expect=Expectation(**expected.model_dump()),
        )
        result = score(task, bundle, completion, model=model, pad=0, repeat=0).model_dump()
        result["planned"] = turn < len(case.expected)
        if not result["planned"]:
            result["success"] = False
            result["failures"].append("unexpected extra agent turn")
        decisions.append(result)
        if completion.error is not None:
            terminal = "request_error"
            break
        if completion.finish_reason not in ("stop", "tool_calls", "function_call"):
            terminal = "truncated" if completion.finish_reason == "length" else "incomplete_finish"
            break
        if completion.content.strip():
            events.append({"type": "message", "role": "assistant", "content": completion.content})
        if not completion.calls:
            terminal = "complete" if completion.content.strip() else "empty_final_reply"
            messages.append({"role": "assistant", "content": completion.content})
            break
        # Reject malformed envelopes before executing any member of this batch.
        ids = [c.id for c in completion.calls if c.id]
        if any(c.parse_error for c in completion.calls) or len(ids) != len(set(ids)):
            terminal = "invalid_tool_calls"
            break
        wire_calls = []
        for i, call in enumerate(completion.calls):
            wire_calls.append(
                {
                    "id": call.id or f"turn-{turn}-call-{i}",
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
            )
        messages.append({"role": "assistant", "content": completion.content, "tool_calls": wire_calls})
        for i, call in enumerate(completion.calls):
            spec = specs.get(call.name)
            if spec is None:
                status, output = "error", {"error": "unknown_tool"}
            elif not Draft202012Validator(spec.parameters).is_valid(call.arguments):
                status, output = "error", {"error": "invalid_arguments"}
            else:
                attempt = attempts[call.name]
                attempts[call.name] += 1
                if attempt >= len(spec.outcomes):
                    status, output = "error", {"error": "mock_outcomes_exhausted"}
                else:
                    outcome = spec.outcomes[attempt]
                    status, output = outcome.status, copy.deepcopy(outcome.result)
            event = {
                "type": "tool_call",
                "id": f"turn-{turn}-call-{i}",
                "tool": call.name,
                "args": copy.deepcopy(call.arguments),
                "status": status,
                "result": output,
            }
            events.append(event)
            executions.append({**event, "turn": turn, "provider_call_id": call.id})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": wire_calls[i]["id"],
                    "content": json.dumps({"status": status, "result": output}),
                }
            )
    audit = audit_trace(trace, extractor)
    missing = list(range(len(decisions), len(case.expected)))
    decision_passed = not missing and all(d["success"] for d in decisions)
    complete = terminal == "complete" and audit["status"] == "complete"
    return {
        "case_id": case.id,
        "status": "complete" if complete else "incomplete",
        "agent_status": terminal,
        "decision_passed": decision_passed,
        "account_passed": audit["passed"],
        "audit": audit,
        "passed": complete and decision_passed and audit["passed"] is True,
        "missing_decision_turns": missing,
        "decisions": decisions,
        "completions": completions,
        "executions": executions,
        "trace": trace,
        "conversation": messages,
        "versions": {"callprobe": __version__, "scoring": SCORING_VERSION, "didyoureally": dyr.__version__},
    }


def render_agent_report(report: dict) -> str:
    rows = report["episodes"]
    lines = [
        "# Agent reliability report",
        "",
        "Mock execution only. No real business actions occurred.",
        "",
        f"Run status: {report['status']}. Completed cases: {len(rows)}/{report['planned_cases']}.",
        "",
        "| Case | Agent | Decisions | Account | Findings |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        verdicts = ", ".join(f["verdict"] for f in row["audit"]["findings"]) or "none"
        account = (
            "incomplete" if row["account_passed"] is None else ("pass" if row["account_passed"] else "fail")
        )
        lines.append(
            f"| {row['case_id']} | {row['agent_status']} | "
            f"{'pass' if row['decision_passed'] else 'fail'} | {account} | {verdicts} |"
        )
    lines += [
        "",
        "Decision checks compare each serial turn with the authored expected call. "
        "Account checks use Didyoureally's extracted claims and deterministic matcher. "
        "Any non-backed finding or unchecked detail fails the account gate. "
        "Incomplete generation or extraction cannot pass the combined gate.",
        "",
    ]
    return "\n".join(lines)
