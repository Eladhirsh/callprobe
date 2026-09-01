"""The scoring rubric.

Three independent axes, deliberately kept separate because they fail for
different reasons and the mix is the interesting part of a report:

    selection_ok  did it pick the right tool, or correctly decline to call one
    schema_ok     do the arguments validate against the tool's JSON Schema
    args_ok       are the values actually right

success = all three. A model that scores well on selection and schema but
badly on args is the dangerous case: it produces valid calls with wrong
values, which pass every check most people currently run.
"""

from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator

from .models import ArgCheck, Bundle, Call, Task, TaskResult
from .client import Completion

MISSING = object()

THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S)


def visible_text(text: str) -> str:
    """Drop reasoning traces so the digest shows the actual reply."""
    return THINK.sub("", text or "").strip()


def resolve(data: Any, path: str) -> Any:
    """Resolve a dotted path, supporting list indices: a.b.0.c"""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return MISSING
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def apply_check(arguments: dict[str, Any], check: ArgCheck) -> tuple[bool, str]:
    actual = resolve(arguments, check.path)
    label = f"{check.path} {check.op} {check.value!r}"

    if check.op == "exists":
        return (actual is not MISSING, f"{check.path} missing")
    if check.op == "absent":
        return (actual is MISSING, f"{check.path} should not be present")
    if actual is MISSING:
        return (False, f"{check.path} missing")

    try:
        if check.op == "eq":
            ok = actual == check.value
        elif check.op == "neq":
            ok = actual != check.value
        elif check.op == "in":
            ok = actual in check.value
        elif check.op == "contains":
            ok = check.value in actual
        elif check.op == "gte":
            ok = float(actual) >= float(check.value)
        elif check.op == "lte":
            ok = float(actual) <= float(check.value)
        elif check.op == "matches":
            ok = re.fullmatch(str(check.value), str(actual)) is not None
        else:
            return (False, f"unknown op {check.op}")
    except Exception as exc:  # noqa: BLE001
        return (False, f"{label} raised {type(exc).__name__}")

    return (ok, f"{label}, got {actual!r}")


def pick_call(calls: list[Call], expected: str | None) -> Call | None:
    if not calls:
        return None
    if expected:
        for call in calls:
            if call.name == expected:
                return call
    return calls[0]


def score(
    task: Task,
    bundle: Bundle,
    completion: Completion,
    *,
    model: str,
    pad: int,
    repeat: int,
) -> TaskResult:
    result = TaskResult(
        task_id=task.id,
        category=task.category,
        model=model,
        pad=pad,
        repeat=repeat,
        selection_ok=False,
        schema_ok=False,
        args_ok=False,
        success=False,
        expected=task.expect.tool,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        latency_ms=completion.latency_ms,
        error=completion.error,
    )

    if completion.error:
        result.failures.append(f"request failed: {completion.error}")
        return result

    # Abstention tasks: the correct behavior is to call nothing.
    result.truncated = completion.finish_reason == "length"
    text = visible_text(completion.content) or visible_text(completion.reasoning)
    result.response_text = text[:300]

    if task.expect.type == "no_call":
        clean = not completion.calls
        result.selection_ok = clean
        result.schema_ok = clean
        result.args_ok = clean
        result.success = clean
        if not clean:
            result.called = completion.calls[0].name
            result.failures.append(
                f"called {result.called} when no tool applied"
            )
        return result

    call = pick_call(completion.calls, task.expect.tool)
    if call is None:
        if result.truncated:
            result.failures.append(
                "truncated on the token limit before any call, raise --max-tokens"
            )
        else:
            result.failures.append("no tool call produced")
        return result

    result.called = call.name
    acceptable = {task.expect.tool, *task.expect.also_acceptable}
    result.selection_ok = call.name in acceptable
    if not result.selection_ok:
        result.failures.append(f"called {call.name}, expected {task.expect.tool}")

    if len(completion.calls) > 1:
        result.failures.append(f"produced {len(completion.calls)} calls")

    if call.parse_error:
        result.failures.append(f"arguments did not parse: {call.parse_error}")
        return result

    tool = bundle.by_name(call.name)
    if tool is None:
        result.failures.append(f"{call.name} is not a tool in this bundle")
        return result

    errors = sorted(
        Draft202012Validator(tool.parameters).iter_errors(call.arguments),
        key=lambda e: list(e.path),
    )
    result.schema_ok = not errors
    for error in errors[:3]:
        location = ".".join(str(p) for p in error.path) or "(root)"
        result.failures.append(f"schema: {location}: {error.message}")

    args_ok = True
    for key, expected_value in task.expect.args.items():
        actual = resolve(call.arguments, key)
        if actual != expected_value:
            args_ok = False
            shown = "missing" if actual is MISSING else repr(actual)
            result.failures.append(f"{key} expected {expected_value!r}, got {shown}")
    for check in task.expect.arg_checks:
        ok, message = apply_check(call.arguments, check)
        if not ok:
            args_ok = False
            result.failures.append(message)
    result.args_ok = args_ok

    result.success = result.selection_ok and result.schema_ok and result.args_ok
    return result
