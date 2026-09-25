"""Deterministic CI policies over complete, matched benchmark runs."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .models import Category, Run

Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class GatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    fail_on_regression: bool = True
    critical_tasks: list[str] = Field(default_factory=list)
    min_success: Fraction | None = None
    min_category_success: dict[Category, Fraction] = Field(default_factory=dict)
    max_success_drop: Fraction | None = None
    max_error_rate: Fraction = 0.0


def load_policy(path: str | None) -> GatePolicy:
    if path is None:
        return GatePolicy()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("policy must be a YAML mapping")
    return GatePolicy.model_validate(data)


def _index(run: Run, label: str):
    config = run.config
    if not config.task_ids or not config.pads or config.repeats < 1:
        raise ValueError(f"{label}: missing planned coverage; create a new run")
    if (len(set(config.task_ids)) != len(config.task_ids)
            or len(set(config.pads)) != len(config.pads)
            or any(p < 0 for p in config.pads)):
        raise ValueError(f"{label}: invalid planned coverage")
    expected = {(task, pad, repeat) for task in config.task_ids
                for pad in config.pads for repeat in range(config.repeats)}
    indexed = {}
    for result in run.results:
        key = (result.task_id, result.pad, result.repeat)
        if key in indexed:
            raise ValueError(f"{label}: duplicate result {key}")
        if result.model != config.model:
            raise ValueError(f"{label}: result model differs from run configuration")
        indexed[key] = result
    if set(indexed) != expected:
        raise ValueError(
            f"{label}: incomplete or unexpected coverage "
            f"({len(expected - set(indexed))} missing, {len(set(indexed) - expected)} unexpected)"
        )
    return indexed


def evaluate_gate(baseline: Run, candidate: Run, policy: GatePolicy) -> dict:
    """Invalid comparisons raise; valid comparisons return policy violations.

    Accuracy deltas use only keys scored in BOTH runs. Request errors are
    checked separately in each run so they cannot disappear from a CI gate.
    """
    for label, run in (("baseline", baseline), ("candidate", candidate)):
        if run.config.selected_task_ids is not None:
            raise ValueError(
                f"{label} is a targeted debug run (selected task ids only): "
                "targeted runs are for debugging; rerun full suite for CI"
            )
    for name in ("suite_hash", "scoring_version"):
        a, b = getattr(baseline.config, name), getattr(candidate.config, name)
        if a is None or b is None or a == "" or b == "" or a != b:
            raise ValueError(f"baseline and candidate need matching {name}; create new baselines for old runs")
    before, after = _index(baseline, "baseline"), _index(candidate, "candidate")
    if before.keys() != after.keys():
        raise ValueError("baseline and candidate must cover the same tasks, pads, and repeats")
    if any(before[key].category != after[key].category for key in before):
        raise ValueError("baseline and candidate task categories differ")
    unknown = set(policy.critical_tasks) - set(candidate.config.task_ids or [])
    if unknown:
        raise ValueError("unknown critical tasks: " + ", ".join(sorted(unknown)))
    categories = {r.category for r in after.values()}
    if set(policy.min_category_success) - categories:
        raise ValueError("policy names categories absent from the run")

    failures = []
    for label, indexed in (("baseline", before), ("candidate", after)):
        error_rate = sum(r.error is not None for r in indexed.values()) / len(indexed)
        if error_rate > policy.max_error_rate:
            failures.append(f"{label} error rate {error_rate:.1%} exceeds {policy.max_error_rate:.1%}")

    pairs = [(before[key], after[key]) for key in sorted(before)
             if not before[key].error and not after[key].error]
    regressions = [
        {"task_id": b.task_id, "pad": b.pad, "repeat": b.repeat}
        for a, b in pairs if a.success and not b.success
    ]
    critical = set(policy.critical_tasks)
    if policy.fail_on_regression and regressions:
        failures.append(f"{len(regressions)} previously passing case(s) regressed")
    failed_critical = sorted({r.task_id for r in after.values()
                              if r.task_id in critical and (r.error or not r.success)})
    if failed_critical:
        failures.append("critical tasks failed: " + ", ".join(failed_critical))

    delta = None
    if not pairs:
        failures.append("no matched scored cases")
    else:
        delta = sum(int(b.success) - int(a.success) for a, b in pairs) / len(pairs)
        if policy.max_success_drop is not None and delta < -policy.max_success_drop:
            failures.append(f"success dropped {-delta:.1%}; maximum is {policy.max_success_drop:.1%}")

    scored = [r for r in after.values() if not r.error]
    if policy.min_success is not None:
        rate = sum(r.success for r in scored) / len(scored) if scored else 0.0
        if not scored or rate < policy.min_success:
            failures.append(f"candidate success {rate:.1%} below {policy.min_success:.1%}")
    for category, threshold in policy.min_category_success.items():
        group = [r for r in scored if r.category == category]
        rate = sum(r.success for r in group) / len(group) if group else 0.0
        if not group or rate < threshold:
            failures.append(f"{category} success {rate:.1%} below {threshold:.1%}")

    return {
        "passed": not failures,
        "failures": failures,
        "matched_cases": len(pairs),
        "success_delta": delta,
        "regressions": regressions,
    }


def render_gate(gate: dict) -> str:
    lines = ["CI gate: " + ("PASS" if gate["passed"] else "FAIL")]
    lines.extend("  " + failure for failure in gate["failures"])
    lines.extend(f"  regressed: {r['task_id']} pad={r['pad']} repeat={r['repeat']}"
                 for r in gate["regressions"])
    return "\n".join(lines)
