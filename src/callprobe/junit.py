"""Offline JUnit XML exporter for a callprobe Run.

Converts recorded observations into a `<testsuites>/<testsuite>/<testcase>`
tree. Scoring is read as recorded; this module never recomputes a result,
contacts the network, or embeds raw evidence that could carry secrets
(endpoint, notes, response text, raw arguments, error strings, failure
strings). Validation guards against observations the run cannot support
(wrong model, duplicates, out-of-plan triples, invalid pads/repeats or
selected IDs). Planned coverage is checked by bounds and count, so a
config describing an arbitrarily large sweep never allocates its full
Cartesian product.
"""

from __future__ import annotations

import math
import re
from typing import Iterable
from xml.etree import ElementTree as ET

from .models import Run, RunConfig, TaskResult


_INVALID_XML = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]"
)


def _sanitize(text: object) -> str:
    """Strip XML 1.0 forbidden controls and lone surrogates; keep Unicode."""
    if text is None:
        return ""
    return _INVALID_XML.sub("", str(text))


def _latency_seconds(latency_ms: object) -> float:
    """Non-finite or negative latencies clamp to zero."""
    try:
        value = float(latency_ms) / 1000.0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value < 0.0:
        return 0.0
    return value


def _format_time(seconds: float) -> str:
    return f"{seconds:.6f}"


def _case_name(task_id: str, pad: int, repeat: int) -> str:
    return f"{_sanitize(task_id)}[pad={pad},repeat={repeat}]"


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _validate_plan(cfg: RunConfig) -> tuple[list[int], int, list[str] | None, list[str] | None]:
    """Return (pads, repeats, task_ids, selected_task_ids) after shape checks."""
    pads = cfg.pads
    if not isinstance(pads, list) or not pads:
        raise ValueError("pads must be a nonempty list of non-negative integers")
    seen_pads: set[int] = set()
    for pad in pads:
        if _is_bool(pad) or not isinstance(pad, int) or pad < 0:
            raise ValueError(f"invalid pad {pad!r}: must be a non-negative integer")
        if pad in seen_pads:
            raise ValueError(f"invalid pads: duplicate pad {pad!r}")
        seen_pads.add(pad)

    repeats = cfg.repeats
    if _is_bool(repeats) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError(f"invalid repeats {repeats!r}: must be a positive integer")

    task_ids = cfg.task_ids
    if task_ids is not None:
        if not isinstance(task_ids, list):
            raise ValueError("task_ids must be a list of strings")
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("invalid task_ids: duplicate entries")

    selected = cfg.selected_task_ids
    if selected is not None:
        if not isinstance(selected, list) or not selected:
            raise ValueError("selected_task_ids must be a non-empty list of ids")
        if len(set(selected)) != len(selected):
            raise ValueError("invalid selected_task_ids: duplicate entries")
        if task_ids is not None:
            known_ids = set(task_ids)
            unknown = [sid for sid in selected if sid not in known_ids]
            if unknown:
                raise ValueError(
                    f"invalid selected_task_ids: not in task_ids: {sorted(set(unknown))}"
                )

    return list(pads), repeats, task_ids, selected


def _validate_observations(
    results: Iterable[TaskResult],
    *,
    model: str,
    pads: list[int],
    repeats: int,
    allowed_tasks: set[str] | None,
    scope_label: str,
) -> None:
    pad_set = set(pads)
    seen: set[tuple[str, int, int]] = set()
    for r in results:
        if r.model != model:
            raise ValueError(
                "observation model does not match config model"
            )
        if _is_bool(r.pad) or not isinstance(r.pad, int) or r.pad not in pad_set:
            raise ValueError(f"out-of-plan observation: pad {r.pad!r}")
        if _is_bool(r.repeat) or not isinstance(r.repeat, int) or r.repeat < 0 or r.repeat >= repeats:
            raise ValueError(f"out-of-plan observation: repeat {r.repeat!r}")
        if allowed_tasks is not None and r.task_id not in allowed_tasks:
            raise ValueError(
                f"out-of-plan observation: task_id {r.task_id!r} outside {scope_label}"
            )
        key = (r.task_id, r.pad, r.repeat)
        if key in seen:
            raise ValueError(f"duplicate observation {key!r}")
        seen.add(key)


def _failure_reasons(r: TaskResult) -> list[str]:
    """Boolean-only, no secrets: which strict flags fired, plus truncation."""
    reasons: list[str] = []
    if r.truncated:
        reasons.append("truncated")
    if not r.selection_ok:
        reasons.append("selection")
    if not r.schema_ok:
        reasons.append("schema")
    if not r.args_ok:
        reasons.append("args")
    if not r.call_count_ok:
        reasons.append("call_count")
    if not reasons and not r.success:
        reasons.append("strict")
    return reasons


def _failure_type_and_message(r: TaskResult) -> tuple[str, str]:
    reasons = _failure_reasons(r) or ["strict"]
    primary = reasons[0]
    parts = []
    for name in reasons:
        if name == "truncated":
            parts.append("response was truncated before completion")
        elif name == "selection":
            parts.append("selection check failed")
        elif name == "schema":
            parts.append("schema check failed")
        elif name == "args":
            parts.append("args check failed")
        elif name == "call_count":
            parts.append("call count check failed")
        else:
            parts.append("strict check failed")
    return primary, "; ".join(parts)


def _add_property(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, "property", {"name": name, "value": _sanitize(value)})


def render_junit(run: Run) -> str:
    """Serialize a Run as a JUnit XML string. See module docstring."""
    cfg = run.config
    pads, repeats, task_ids, selected = _validate_plan(cfg)

    targeted = selected is not None
    if targeted:
        allowed_tasks: set[str] | None = set(selected)  # type: ignore[arg-type]
        scope_label = "selected_task_ids"
    elif task_ids is not None:
        allowed_tasks = set(task_ids)
        scope_label = "task_ids"
    else:
        allowed_tasks = None
        scope_label = "(legacy, unknown)"

    _validate_observations(
        run.results,
        model=cfg.model,
        pads=pads,
        repeats=repeats,
        allowed_tasks=allowed_tasks,
        scope_label=scope_label,
    )

    recorded = len(run.results)
    if targeted:
        planned: int | None = len(selected) * len(pads) * repeats  # type: ignore[arg-type]
    elif task_ids is not None:
        planned = len(task_ids) * len(pads) * repeats
    else:
        planned = None

    testsuites = ET.Element("testsuites")
    suite_display = cfg.suite_name or "callprobe"
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        {"name": _sanitize(suite_display)},
    )

    properties = ET.SubElement(testsuite, "properties")
    _add_property(properties, "model", cfg.model)
    _add_property(
        properties,
        "suite_hash",
        cfg.suite_hash if cfg.suite_hash is not None else "unknown",
    )
    _add_property(
        properties,
        "scoring_version",
        str(cfg.scoring_version) if cfg.scoring_version is not None else "unknown",
    )
    _add_property(
        properties,
        "planned_coverage",
        str(planned) if planned is not None else "unknown",
    )
    _add_property(properties, "recorded_coverage", str(recorded))
    _add_property(properties, "targeted_scope", "true" if targeted else "false")

    tests = 0
    failures = 0
    errors = 0
    skipped = 0
    total_time = 0.0

    for r in run.results:
        tests += 1
        seconds = _latency_seconds(r.latency_ms)
        total_time += seconds
        case = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": _case_name(r.task_id, r.pad, r.repeat),
                "classname": _sanitize(r.category),
                "time": _format_time(seconds),
            },
        )
        if r.error is not None:
            errors += 1
            ET.SubElement(
                case,
                "error",
                {
                    "type": "request_error",
                    "message": "request error (details redacted)",
                },
            )
            continue

        # Preserve the recorded strict verdict. Sub-flags explain failures,
        # but never recompute historical success under a new policy.
        strict_pass = bool(r.success) and not r.truncated
        if strict_pass:
            continue

        failures += 1
        ftype, fmsg = _failure_type_and_message(r)
        ET.SubElement(
            case,
            "failure",
            {"type": ftype, "message": _sanitize(fmsg)},
        )

    if targeted:
        tests += 1
        skipped += 1
        case = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": "coverage.targeted_debug_notice",
                "classname": "coverage",
                "time": _format_time(0.0),
            },
        )
        ET.SubElement(
            case,
            "skipped",
            {
                "type": "targeted_debug",
                "message": (
                    "targeted debug coverage of selected task ids; "
                    "not a full benchmark"
                ),
            },
        )

    synthetic_coverage_error = False
    if task_ids is None:
        synthetic_coverage_error = True
        tests += 1
        errors += 1
        case = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": "coverage.unknown",
                "classname": "coverage",
                "time": _format_time(0.0),
            },
        )
        ET.SubElement(
            case,
            "error",
            {
                "type": "coverage_unknown",
                "message": (
                    "coverage cannot be verified: config.task_ids is missing"
                ),
            },
        )
    elif planned is not None and recorded < planned:
        synthetic_coverage_error = True
        missing = planned - recorded
        tests += 1
        errors += 1
        case = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": "coverage.partial",
                "classname": "coverage",
                "time": _format_time(0.0),
            },
        )
        ET.SubElement(
            case,
            "error",
            {
                "type": "coverage_partial",
                "message": (
                    f"partial run: {missing} of {planned} planned "
                    f"observations missing"
                ),
            },
        )

    if recorded == 0 and not synthetic_coverage_error:
        tests += 1
        errors += 1
        case = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": "coverage.empty",
                "classname": "coverage",
                "time": _format_time(0.0),
            },
        )
        ET.SubElement(
            case,
            "error",
            {
                "type": "coverage_empty",
                "message": "no observations recorded; empty report is not a pass",
            },
        )

    testsuite.set("tests", str(tests))
    testsuite.set("failures", str(failures))
    testsuite.set("errors", str(errors))
    testsuite.set("skipped", str(skipped))
    testsuite.set("time", _format_time(total_time))

    ET.indent(testsuites, space="  ")
    xml_bytes = ET.tostring(testsuites, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
