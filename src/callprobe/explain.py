"""Offline failure diagnostics for a saved run: `callprobe explain`.

This reads a `Run` and the suite it was scored against, then turns each
failing `(task, pad, repeat)` case into something actionable: the user
prompt(s) that produced it, what was expected, every call the model
actually produced (parsed arguments, or the raw text and parse error for
a malformed one), the recorded failure reasons, and a small set of
recurring diagnostic categories derived from the fields the scorer
already recorded, not by parsing those failure strings back apart.

For one common and fixable shape of bug, nested-object argument groups
(an imported OpenAPI suite's `path`/`query`/`body`) that a model flattens
or under-wraps, this also proposes a corrected argument shape. The
proposal is only ever offered when it can be validated end to end against
the tool's actual schema; otherwise it is silently withheld rather than
asserted with unearned confidence. It is advisory only: nothing here is
executed, and nothing here is re-scored.

No network access, no model calls, no suite or result mutation. Schema
validation used for diagnostics never resolves a `$ref`: a dedicated
registry refuses every retrieval outright, and anything that structurally
depends on references or other constructs this module does not reason
about is skipped with a clear note rather than guessed at.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry

from .models import Bundle, Run, Suite, Task, TaskResult, Tool
from .scoring import MISSING, apply_check, pick_call, resolve

# Order both drives deterministic output and documents the taxonomy: a
# request error or truncation explains itself and nothing past it is
# meaningful, an abstention that got called or a call that never
# happened preempts anything about the call's shape, and only once a
# tool selection is genuinely usable does schema/value detail apply.
CATEGORY_ORDER = [
    "request_error",
    "truncated",
    "no_call",
    "unexpected_call",
    "multiple_calls",
    "wrong_tool",
    "malformed_arguments",
    "schema",
    "argument_value",
]

CATEGORY_LABELS = {
    "request_error": "request error (endpoint failure, not scored as a model failure)",
    "truncated": "truncated on the token limit before completion",
    "no_call": "expected a call; the model produced none",
    "unexpected_call": "expected no call; the model called a tool anyway",
    "multiple_calls": "produced more than one call",
    "wrong_tool": "called a tool other than the expected/acceptable one",
    "malformed_arguments": "call arguments did not parse as JSON",
    "schema": "arguments failed the tool's JSON Schema",
    "argument_value": "argument values did not match the task's expectation",
}

# Bounds for the shape-hint schema walk. These schemas come from a suite
# already loaded and hashed, not from a network fetch, but a hand-written
# tools.yaml could still contain something pathological.
_SIMPLE_MAX_NODES = 4000
_SIMPLE_MAX_DEPTH = 40

# Anything here disqualifies a schema from shape-hint or schema-error
# reasoning outright, wherever it appears, however deep: reference and
# dynamic-reference keywords (so nothing is ever resolved, local or not),
# every combinator, and the container keywords (contains/prefixItems/
# unevaluatedItems/$defs/definitions/dependentSchemas) whose subschemas
# this module does not otherwise walk into. Presence of the key alone is
# enough to refuse, so a reference hidden inside one of these containers
# can never be reached, let alone resolved.
_UNSUPPORTED_SCHEMA_KEYS = {
    "$ref", "$dynamicRef", "$dynamicAnchor", "$recursiveRef", "$recursiveAnchor",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "patternProperties", "dependentSchemas", "dependentRequired",
    "unevaluatedProperties", "unevaluatedItems", "propertyNames",
    "contains", "prefixItems", "$defs", "definitions",
}

_ADVISORY = (
    "advisory only: not executed or re-scored; the tool and argument shape "
    "are validated, but expectation and value correctness are not guaranteed"
)


# --------------------------------------------------------- safe validation


def _forbid_remote_retrieve(uri: str):
    """Passed to `referencing.Registry` as its only way to fetch a
    resource; raising here instead of fetching is what makes the
    registry incapable of network I/O, independent of any pre-check.
    """
    raise LookupError(f"explain refuses to resolve any schema reference ({uri!r})")


# A registry with nothing pre-loaded and a `retrieve` that always raises:
# no `$ref`, local or remote, can ever be resolved through it. This is
# defense in depth: `_schema_is_simple` already refuses any schema that
# contains a reference before a validator is ever built.
_NO_RETRIEVAL_REGISTRY = Registry(retrieve=_forbid_remote_retrieve)


def _safe_validator(schema: dict) -> Draft202012Validator | None:
    """Build a validator that cannot perform network I/O. Returns None if
    the schema itself can't even be used to build one, so callers report
    a diagnostic limitation instead of crashing.
    """
    try:
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema, registry=_NO_RETRIEVAL_REGISTRY)
    except Exception:  # noqa: BLE001 - any construction failure is "can't validate"
        return None


def _validates(tool: Tool, candidate: dict) -> bool:
    validator = _safe_validator(tool.parameters)
    if validator is None:
        return False
    try:
        return next(validator.iter_errors(candidate), None) is None
    except Exception:  # noqa: BLE001 - never let a schema quirk crash explain
        return False


def _schema_error_detail(tool: Tool, arguments: dict, limit: int = 5) -> list[dict] | None:
    """Structured `(path, message, expected type)` detail, or None if the
    schema could not be safely validated at all (caller shows a
    diagnostic-limitation note instead).
    """
    validator = _safe_validator(tool.parameters)
    if validator is None:
        return None
    try:
        errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.path))
    except Exception:  # noqa: BLE001
        return None
    return [
        {
            "path": ".".join(str(p) for p in error.path) or "(root)",
            "message": error.message,
            "expected_type": error.schema.get("type") if isinstance(error.schema, dict) else None,
        }
        for error in errors[:limit]
    ]


# ------------------------------------------------------------- shape hints


def _schema_is_simple(schema: Any, depth: int = 0, budget: list[int] | None = None) -> bool:
    """True if a schema (and everything nested in it) is plain enough to
    reason about structurally: no references of any kind, no combinators,
    no pattern or schema-valued additionalProperties, and none of the
    container keywords this module does not otherwise walk into. Refusing
    anything else means a hint (or schema-error detail) is only ever
    offered where the schema is fully, safely understood, offline.
    """
    if budget is None:
        budget = [_SIMPLE_MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0 or depth > _SIMPLE_MAX_DEPTH:
        return False
    if isinstance(schema, bool):
        return True
    if not isinstance(schema, dict):
        return False
    if _UNSUPPORTED_SCHEMA_KEYS & schema.keys():
        return False
    if isinstance(schema.get("additionalProperties"), dict):
        return False
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for value in properties.values():
            if not _schema_is_simple(value, depth + 1, budget):
                return False
    items = schema.get("items")
    if isinstance(items, list):
        for item in items:
            if not _schema_is_simple(item, depth + 1, budget):
                return False
    elif items is not None:
        if not _schema_is_simple(items, depth + 1, budget):
            return False
    return True


def _is_object_group(schema: Any) -> bool:
    return (
        isinstance(schema, dict)
        and schema.get("type") == "object"
        and isinstance(schema.get("properties"), dict)
    )


def _compute_move(tool: Tool, arguments: dict) -> dict | None:
    """Move top-level keys that belong to a missing nested group (e.g. an
    OpenAPI `path`/`query`/`body` group) under that group, when every
    stray key maps to exactly one missing group's properties. Does not
    check whether the result validates; the caller decides that, since
    a move alone may need a wrap on top of it to fully validate.

    Refuses outright if the root schema does not say
    `additionalProperties: false`: when extra top-level keys are
    actually permitted, they already have a valid location (right where
    they are), so moving them would be a guess, not a correction.
    """
    schema = tool.parameters or {}
    if not _is_object_group(schema) or not _schema_is_simple(schema):
        return None
    if schema.get("additionalProperties") is not False:
        return None
    top_props: dict = schema["properties"]

    missing_groups = {
        name: set(sub["properties"])
        for name, sub in top_props.items()
        if name not in arguments and _is_object_group(sub)
    }
    if not missing_groups:
        return None

    loose_keys = [key for key in arguments if key not in top_props]
    if not loose_keys:
        return None

    assignment: dict[str, str] = {}
    for key in loose_keys:
        targets = [group for group, props in missing_groups.items() if key in props]
        if len(targets) != 1:
            return None  # unmapped or ambiguous: refuse the whole suggestion
        assignment[key] = targets[0]

    candidate = {k: v for k, v in arguments.items() if k not in assignment}
    for group in dict.fromkeys(assignment.values()):
        candidate[group] = {k: arguments[k] for k in loose_keys if assignment[k] == group}
    return {"moved": assignment, "candidate_arguments": candidate}


def _compute_wrap(tool: Tool, arguments: dict) -> dict | None:
    """Wrap a top-level scalar value in the single-property object its
    group schema actually requires (e.g. a `body` string where the
    schema wants `{"body": {"body": <string>}}`). Does not check
    validity; see `_compute_move`.
    """
    schema = tool.parameters or {}
    if not _is_object_group(schema) or not _schema_is_simple(schema):
        return None
    top_props: dict = schema["properties"]

    candidate = dict(arguments)
    wrapped: dict[str, str] = {}
    for name, value in arguments.items():
        if isinstance(value, dict):
            continue  # already object-shaped; nothing to wrap
        sub = top_props.get(name)
        if not _is_object_group(sub) or len(sub["properties"]) != 1:
            continue
        (inner_name,) = sub["properties"].keys()
        candidate[name] = {inner_name: value}
        wrapped[name] = inner_name

    if not wrapped:
        return None
    return {"wrapped": wrapped, "candidate_arguments": candidate}


def build_shape_hint(tool: Tool, arguments: dict) -> dict | None:
    """Try a move, then a wrap, then both together, in that order,
    keeping the first combination whose candidate fully validates
    against the tool's schema. Never invents or drops a value, and
    returns nothing rather than assert an unconfirmed fix.
    """
    if not isinstance(arguments, dict):
        return None

    move = _compute_move(tool, arguments)
    if move and _validates(tool, move["candidate_arguments"]):
        return {
            "kind": "nested_move",
            "moved": move["moved"],
            "candidate_arguments": move["candidate_arguments"],
            "advisory": _ADVISORY,
        }

    wrap = _compute_wrap(tool, arguments)
    if wrap and _validates(tool, wrap["candidate_arguments"]):
        return {
            "kind": "scalar_wrap",
            "wrapped": wrap["wrapped"],
            "candidate_arguments": wrap["candidate_arguments"],
            "advisory": _ADVISORY,
        }

    if move:
        combined = _compute_wrap(tool, move["candidate_arguments"])
        if combined and _validates(tool, combined["candidate_arguments"]):
            return {
                "kind": "nested_move+scalar_wrap",
                "moved": move["moved"],
                "wrapped": combined["wrapped"],
                "candidate_arguments": combined["candidate_arguments"],
                "advisory": _ADVISORY,
            }
    return None


# ------------------------------------------------------------ case report


def classify_case(task: Task, bundle: Bundle | None, result: TaskResult) -> list[str]:
    """Diagnostic categories for one failing case, derived only from
    recorded fields (never by re-parsing `result.failures`), and only as
    far as the real scorer's own control flow would have gone: a request
    error or an unparsed call stops there because nothing past it was
    actually evaluated.
    """
    categories: list[str] = []
    if result.error:
        categories.append("request_error")
        return categories

    if task.expect.type == "no_call":
        if result.truncated:
            categories.append("truncated")
        if result.called is not None or result.calls:
            categories.append("unexpected_call")
        return categories

    if result.called is None and not result.calls:
        if result.truncated:
            categories.append("truncated")
        categories.append("no_call")
        return categories

    if len(result.calls) > 1:
        categories.append("multiple_calls")
    if result.truncated:
        categories.append("truncated")

    parse_error = None
    tool_resolved = None  # None: unknown (legacy record, no structured calls)
    if result.calls:
        chosen = pick_call(result.calls, task.expect.tool)
        parse_error = chosen.parse_error if chosen else None
        if chosen is not None and bundle is not None:
            tool_resolved = bundle.by_name(chosen.name) is not None

    if not result.selection_ok:
        categories.append("wrong_tool")
    if parse_error:
        categories.append("malformed_arguments")
        return categories
    if tool_resolved is False:
        return categories

    if not result.schema_ok:
        categories.append("schema")
    if not result.args_ok:
        categories.append("argument_value")
    return categories


def _hint_eligible(task: Task, result: TaskResult, chosen) -> bool:
    """A shape hint is only ever offered for the cleanest possible
    failure: one call, to a tool the model was right to pick, that
    parsed, with no request error and no truncation muddying the
    evidence. Multiple calls, an unexpected call, a malformed call, or
    an abstention task never get a hint, no matter how the individual
    flags look.
    """
    return (
        task.expect.type == "call"
        and not result.error
        and not result.truncated
        and len(result.calls) == 1
        and chosen is not None
        and not chosen.parse_error
        and result.selection_ok
    )


def _argument_assertions(task: Task, arguments: dict) -> list[dict]:
    """Expected-vs-actual detail for the task's own assertions, kept
    separate from any shape hint: these are the task author's claims
    about a correct call, not a fabricated gold response. Every entry
    shares the same shape, whether it came from `expect.args` or
    `expect.arg_checks`, so rendering never has to special-case one.
    """
    assertions = []
    for path, expected_value in task.expect.args.items():
        actual = resolve(arguments, path)
        present = actual is not MISSING
        shown = repr(actual) if present else "missing"
        assertions.append({
            "path": path,
            "op": "eq",
            "expected": expected_value,
            "actual": actual if present else None,
            "present": present,
            "note": None,
            "ok": actual == expected_value,
            "detail": f"{path} expected {expected_value!r}, got {shown}",
        })
    for check in task.expect.arg_checks:
        ok, detail = apply_check(arguments, check)
        actual = resolve(arguments, check.path)
        present = actual is not MISSING
        assertions.append({
            "path": check.path,
            "op": check.op,
            "expected": check.value,
            "actual": actual if present else None,
            "present": present,
            "note": check.note,
            "ok": ok,
            "detail": detail,
        })
    return assertions


def _case_report(task: Task, bundle: Bundle | None, result: TaskResult) -> dict:
    case: dict[str, Any] = {
        "task_id": task.id,
        "category": task.category,
        "pad": result.pad,
        "repeat": result.repeat,
        "prompts": [m.get("content") for m in task.messages if m.get("role") == "user"],
        "expected": {
            "type": task.expect.type,
            "tool": task.expect.tool,
            "also_acceptable": list(task.expect.also_acceptable),
            "args": task.expect.args,
            "arg_checks": [c.model_dump() for c in task.expect.arg_checks],
        },
        "called": result.called,
        "truncated": result.truncated,
        "error": result.error,
        "reasons": list(result.failures),
        "diagnostics": classify_case(task, bundle, result),
    }

    if result.response_text and result.called is None:
        case["response_text"] = result.response_text

    if result.error:
        case["call_evidence"] = "none"
        case["calls"] = []
        return case

    if result.calls:
        case["call_evidence"] = "full"
        case["calls"] = [c.model_dump() for c in result.calls]
    elif result.called is not None:
        case["call_evidence"] = "legacy"
        case["calls"] = None
        case["legacy_note"] = (
            "full call evidence is unavailable for this record (it predates "
            "structured call evidence); only the recorded tool name is "
            "known, so no parsed arguments or shape hints are shown"
        )
    else:
        case["call_evidence"] = "none"
        case["calls"] = []

    if not result.calls:
        return case

    chosen = pick_call(result.calls, task.expect.tool)
    if chosen is None or chosen.parse_error:
        return case

    if task.expect.type == "call" and (task.expect.args or task.expect.arg_checks):
        case["argument_assertions"] = _argument_assertions(task, chosen.arguments)

    tool = bundle.by_name(chosen.name) if bundle else None
    if tool is None or result.schema_ok:
        return case

    if not _schema_is_simple(tool.parameters or {}):
        case["schema_diagnostics_limited"] = (
            "the tool schema uses $ref, a combinator, or another construct "
            "explain does not validate offline; only the recorded failure "
            "reasons above are available"
        )
        return case

    errors = _schema_error_detail(tool, chosen.arguments)
    if errors is None:
        case["schema_diagnostics_limited"] = (
            "the tool schema could not be safely validated offline; only "
            "the recorded failure reasons above are available"
        )
        return case
    case["schema_errors"] = errors

    if _hint_eligible(task, result, chosen):
        hint = build_shape_hint(tool, chosen.arguments)
        if hint is not None:
            case["shape_hint"] = hint
    return case


# ------------------------------------------------------------------- run


def check_suite_matches(run: Run, suite: Suite) -> None:
    run_hash = run.config.suite_hash
    if not run_hash:
        raise ValueError(
            "this results file has no recorded suite hash; rerun it against "
            "this suite before explaining its failures"
        )
    if run_hash != suite.hash:
        raise ValueError(
            f"suite hash mismatch: the run recorded {run_hash!r}, the loaded "
            f"suite is {suite.hash!r}; explain requires the exact suite the "
            "run was scored against"
        )


def explain_run(run: Run, suite: Suite, *, task_id: str | None = None) -> dict:
    """Build the structured diagnostics report for a run.

    Raises ValueError for a missing/mismatched suite hash, a result that
    names a task id the suite does not define (a matching suite hash
    should make this impossible; if it happens anyway, the results file
    is not trustworthy enough to summarize silently), or an unknown
    `task_id` filter, so the caller can surface a clear, non-zero-exit
    error instead of a partial or misleading report.
    """
    check_suite_matches(run, suite)

    tasks_by_id = {t.id: t for t in suite.tasks}

    unknown_result_ids = sorted({r.task_id for r in run.results if r.task_id not in tasks_by_id})
    if unknown_result_ids:
        raise ValueError(
            "results file references task id(s) not defined in this suite: "
            f"{', '.join(unknown_result_ids)}; a matching suite hash should "
            "make this impossible, treat this results file as untrustworthy"
        )

    if task_id is not None and task_id not in tasks_by_id:
        raise ValueError(f"unknown task: {task_id!r} is not defined in this suite")

    results = run.results
    if task_id is not None:
        results = [r for r in results if r.task_id == task_id]

    request_errors = sum(1 for r in results if r.error)
    failing = [r for r in results if not r.success]
    cases = [
        _case_report(tasks_by_id[r.task_id], suite.bundles.get(tasks_by_id[r.task_id].bundle), r)
        for r in failing
    ]

    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        for category in case["diagnostics"]:
            counts[category] += 1
    diagnostic_counts = {c: counts[c] for c in CATEGORY_ORDER if counts.get(c)}

    report: dict[str, Any] = {
        "suite": {"name": suite.name, "version": suite.version, "hash": suite.hash},
        "run": {
            "model": run.config.model,
            "suite": run.config.suite,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "task_filter": task_id,
        # total_cases: every (task, pad, repeat) record in scope, including
        # request errors. scored_cases excludes those, matching the
        # convention `report.summarize` uses: a request error is a fact
        # about the endpoint, not something to count as a model failure.
        # failed_cases is every non-success record, request errors included,
        # since those are still shown (with a request_error diagnostic).
        "total_cases": len(results),
        "scored_cases": len(results) - request_errors,
        "request_errors": request_errors,
        "failed_cases": len(cases),
        "diagnostic_counts": diagnostic_counts,
        "cases": cases,
    }
    if task_id is not None:
        report["task_has_results"] = len(results) > 0
        report["task_passed"] = len(results) > 0 and len(cases) == 0
    return report


# ------------------------------------------------------------------ text


def render_explain_text(report: dict) -> str:
    lines = [
        f"suite            {report['suite']['name']} v{report['suite']['version']} "
        f"({report['suite']['hash']})",
        f"model            {report['run']['model']}",
        f"cases            {report['total_cases']}   scored: {report['scored_cases']}"
        + (f"   request errors: {report['request_errors']}" if report["request_errors"] else "")
        + f"   failed: {report['failed_cases']}",
    ]
    task_filter = report["task_filter"]
    if task_filter is not None:
        lines.append(f"task filter      {task_filter}")
        if not report["task_has_results"]:
            lines.append("")
            lines.append(f"task {task_filter!r} has no recorded results in this run")
            return "\n".join(lines)
        if report["task_passed"]:
            lines.append("")
            lines.append(
                f"task {task_filter!r} passed: no failures across "
                f"{report['total_cases']} recorded case(s)"
            )
            return "\n".join(lines)
    else:
        if report["total_cases"] == 0:
            lines.append("")
            lines.append("no recorded results in this run")
            return "\n".join(lines)
        if report["failed_cases"] == 0:
            lines.append("")
            lines.append(f"no failures: all {report['total_cases']} case(s) passed")
            return "\n".join(lines)

    lines.append("")
    lines.append("diagnostic counts (cases; a case may carry more than one category)")
    for category, count in report["diagnostic_counts"].items():
        lines.append(f"  {category:<20} {count:>4}   {CATEGORY_LABELS[category]}")

    lines.append("")
    lines.append("failed cases")
    for case in report["cases"]:
        lines.append("")
        lines.append(f"[{case['task_id']} pad={case['pad']} repeat={case['repeat']}] "
                      f"category={case['category']}  diagnostics={', '.join(case['diagnostics'])}")
        for prompt in case["prompts"]:
            lines.append(f"  prompt: {prompt}")
        expected = case["expected"]
        if expected["type"] == "no_call":
            lines.append("  expected: no call")
        else:
            lines.append(f"  expected: call {expected['tool']}"
                          + (f" (also acceptable: {', '.join(expected['also_acceptable'])})"
                             if expected["also_acceptable"] else ""))
            if expected["args"]:
                lines.append(f"    args {expected['args']}")
            for check in expected["arg_checks"]:
                lines.append(f"    check {check['path']} {check['op']} {check['value']!r}")
        lines.append(f"  called: {case['called']}")
        for reason in case["reasons"]:
            lines.append(f"  reason: {reason}")

        if case["call_evidence"] == "legacy":
            lines.append(f"  calls: {case['legacy_note']}")
        elif case["call_evidence"] == "none":
            if case.get("response_text"):
                said = case["response_text"].replace("\n", " ")[:160]
                lines.append(f"  said: {said}")
        else:
            for call in case["calls"]:
                if call["parse_error"]:
                    lines.append(f"  call: {call['name']} parse_error={call['parse_error']!r} "
                                  f"raw={call['raw_arguments']!r}")
                else:
                    lines.append(f"  call: {call['name']} arguments={call['arguments']}")

        for assertion in case.get("argument_assertions", []):
            mark = "ok" if assertion["ok"] else "FAIL"
            note = f" ({assertion['note']})" if assertion.get("note") else ""
            lines.append(f"    assertion [{mark}] {assertion['detail']}{note}")

        if case.get("schema_diagnostics_limited"):
            lines.append(f"    schema diagnostics limited: {case['schema_diagnostics_limited']}")

        for error in case.get("schema_errors", []):
            type_note = f" (expected type: {error['expected_type']})" if error["expected_type"] else ""
            lines.append(f"    schema error at {error['path']}: {error['message']}{type_note}")

        hint = case.get("shape_hint")
        if hint is not None:
            lines.append(f"  shape hint [{hint['kind']}] {hint['advisory']}")
            if "moved" in hint:
                lines.append(f"    moved: {hint['moved']}")
            if "wrapped" in hint:
                lines.append(f"    wrapped: {hint['wrapped']}")
            lines.append(f"    proposed arguments: {hint['candidate_arguments']}")

    return "\n".join(lines)
