"""Offline, informational comparison of explicitly different tool contracts.

Recorded scores are never recomputed. Matching prompts and provenance do not
prove that two sets of argument assertions express equivalent requirements.
"""
from __future__ import annotations

from .compare import _escape_md
from .models import Run, Suite

CAUTION = (
    "Informational contract comparison, not a CI gate. Semantic equivalence of "
    "changed assertions is not proven; review both suites. Recorded scores are not rescored."
)


def _index(run: Run, suite: Suite) -> dict:
    config = run.config
    if not suite.hash or config.suite_hash != suite.hash:
        raise ValueError("run suite hash does not match its supplied suite")
    if config.selected_task_ids is not None:
        raise ValueError("contract comparison requires full coverage, not targeted runs")
    tasks = {task.id: task for task in suite.tasks}
    if not tasks or len(tasks) != len(suite.tasks):
        raise ValueError("suite must have nonempty, unique task IDs")
    if (not config.task_ids or len(config.task_ids) != len(set(config.task_ids))
            or set(config.task_ids) != set(tasks)):
        raise ValueError("planned task IDs must exactly match the supplied suite")
    pads = config.pads
    if (not pads or len(pads) != len(set(pads)) or any(p < 0 for p in pads)
            or config.repeats < 1):
        raise ValueError("pads must be unique and nonnegative; repeats must be positive")
    for task in suite.tasks:
        if task.bundle not in suite.bundles:
            raise ValueError(f"missing bundle for {task.id}")
        blocked = {t.name for t in suite.bundles[task.bundle].tools} | set(task.exclude_distractors)
        eligible = [t for t in suite.distractors if t.name not in blocked]
        if max(pads) > len(eligible):
            raise ValueError(f"impossible padding for {task.id}")
    indexed = {}
    for result in run.results:
        key = (result.task_id, result.pad, result.repeat)
        if (result.task_id not in tasks or result.pad not in pads
                or not 0 <= result.repeat < config.repeats):
            raise ValueError(f"unexpected observation: {key}")
        if key in indexed:
            raise ValueError(f"duplicate observation: {key}")
        if result.model != config.model or result.category != tasks[result.task_id].category:
            raise ValueError(f"observation model/category mismatch: {key}")
        indexed[key] = result
    if len(indexed) != len(tasks) * len(pads) * config.repeats:
        raise ValueError("missing observations: complete planned coverage is required")
    return indexed


def _metrics(pairs: list) -> dict:
    count = len(pairs)
    passed_a = sum(a.success for a, b in pairs)
    passed_b = sum(b.success for a, b in pairs)
    return dict(scored_pairs=count, passed_a=passed_a, passed_b=passed_b,
                success_a=passed_a / count if count else None,
                success_b=passed_b / count if count else None,
                delta=(passed_b - passed_a) / count if count else None)


def _coverage(run: Run) -> dict:
    scored = [r for r in run.results if r.error is None]
    passed = sum(r.success for r in scored)
    return dict(recorded=len(run.results), scored=len(scored),
                errors=len(run.results) - len(scored),
                truncations=sum(r.truncated for r in run.results), passed=passed,
                success=passed / len(scored) if scored else None)


def compare_contracts(a: Run, b: Run, suite_a: Suite, suite_b: Suite) -> dict:
    """Validate experimental controls and report paired recorded outcomes."""
    ia, ib = _index(a, suite_a), _index(b, suite_b)
    if not a.config.scoring_version or a.config.scoring_version != b.config.scoring_version:
        raise ValueError("matching recorded scoring versions are required")
    settings = ("model", "endpoint", "temperature", "max_tokens", "quantization",
                "server_name", "server_version", "repeats")
    for field in settings:
        if getattr(a.config, field) != getattr(b.config, field):
            raise ValueError(f"run setting differs: {field}")
    if set(a.config.pads) != set(b.config.pads):
        raise ValueError("run setting differs: pads")
    ta, tb = {t.id: t for t in suite_a.tasks}, {t.id: t for t in suite_b.tasks}
    if set(ta) != set(tb):
        raise ValueError("suite task IDs differ")
    if suite_a.distractors != suite_b.distractors:
        raise ValueError("distractor definitions or order differ")
    changed = []
    changed_tools = []
    for task_id, task_a in ta.items():
        task_b = tb[task_id]
        for field in ("messages", "category", "exclude_distractors"):
            if getattr(task_a, field) != getattr(task_b, field):
                raise ValueError(f"task {task_id}: {field} differs")
        for field in ("type", "tool", "also_acceptable"):
            if getattr(task_a.expect, field) != getattr(task_b.expect, field):
                raise ValueError(f"task {task_id}: expected {field} differs")
        names_a = [t.name for t in suite_a.bundles[task_a.bundle].tools]
        names_b = [t.name for t in suite_b.bundles[task_b.bundle].tools]
        if names_a != names_b:
            raise ValueError(f"task {task_id}: available tool names/order differ")
        tools_a = suite_a.bundles[task_a.bundle].tools
        tools_b = suite_b.bundles[task_b.bundle].tools
        for tool_a, tool_b in zip(tools_a, tools_b):
            if tool_a != tool_b:
                changed_tools.append(dict(task_id=task_id, tool=tool_a.name,
                                          description_changed=tool_a.description != tool_b.description,
                                          schema_changed=tool_a.parameters != tool_b.parameters))
        if task_a.expect != task_b.expect:
            changed.append(dict(task_id=task_id, a=task_a.expect.model_dump(),
                                b=task_b.expect.model_dump()))
    paired, improved, regressed, excluded = [], [], [], []
    for key in sorted(ia):
        left, right = ia[key], ib[key]
        entry = dict(task_id=key[0], pad=key[1], repeat=key[2])
        if left.error is not None or right.error is not None:
            excluded.append(dict(**entry, error_a=left.error, error_b=right.error))
            continue
        paired.append((left, right))
        if left.success and not right.success:
            regressed.append(entry)
        elif right.success and not left.success:
            improved.append(entry)
    warnings = [CAUTION]
    if a.config.request_timeout != b.config.request_timeout:
        warnings.append("Request timeouts differ; error coverage may be affected.")
    if a.config.server_version is None or a.config.quantization is None:
        warnings.append("Some server/model provenance is unknown; matching settings do not prove identical weights.")
    return dict(
        kind="contract-comparison", informational=True, warnings=warnings,
        suite_hash_a=suite_a.hash, suite_hash_b=suite_b.hash,
        settings={field: getattr(a.config, field) for field in settings},
        pads=sorted(a.config.pads), scoring_version=a.config.scoring_version,
        request_timeout_a=a.config.request_timeout, request_timeout_b=b.config.request_timeout,
        coverage_a=_coverage(a), coverage_b=_coverage(b), paired=_metrics(paired),
        improved=improved, regressed=regressed, excluded=excluded,
        changed_expectations=changed, changed_tools=changed_tools,
        by_pad={str(p): _metrics([(x, y) for x, y in paired if x.pad == p]) for p in sorted(a.config.pads)},
        by_category={c: _metrics([(x, y) for x, y in paired if x.category == c]) for c in sorted({t.category for t in ta.values()})},
    )


def render_contracts(report: dict, markdown: bool = False) -> str:
    """Render the same coverage, matched metrics and flips as the JSON report."""
    import json

    escape = _escape_md if markdown else str
    def percent(value):
        return "n/a" if value is None else f"{value * 100:.1f}%"
    lines = ["Contract comparison (informational)"]
    lines.extend(escape(w) for w in report["warnings"])
    for side in ("a", "b"):
        cov = report[f"coverage_{side}"]
        lines.append(f"{side}: hash {escape(report[f'suite_hash_{side}'])}; "
                     f"{cov['recorded']} recorded, {cov['scored']} scored, "
                     f"{cov['errors']} errors, {cov['truncations']} truncations; "
                     f"success {percent(cov['success'])}")
    lines.append(f"Scoring version: {report['scoring_version']}; pads: {report['pads']}")
    lines.append("Settings: " + escape(json.dumps(report["settings"], sort_keys=True)))
    lines.append(f"Request timeout a/b: {report['request_timeout_a']} / {report['request_timeout_b']} seconds (None = unknown)")
    for label, metric in [("paired", report["paired"])] + [
        (f"{group} {name}", value) for group in ("by_pad", "by_category")
        for name, value in report[group].items()
    ]:
        lines.append(f"{escape(label)}: {metric['scored_pairs']} pairs; "
                     f"{percent(metric['success_a'])} -> {percent(metric['success_b'])}; "
                     f"delta {percent(metric['delta'])}")
    for group in ("improved", "regressed", "excluded"):
        lines.append(f"{group} ({len(report[group])}):")
        lines.extend("- " + escape(json.dumps(entry, sort_keys=True)) for entry in report[group])
    lines.append(f"Changed tools ({len(report['changed_tools'])} task/tool pairs):")
    lines.extend("- " + escape(json.dumps(entry, sort_keys=True)) for entry in report["changed_tools"])
    lines.append(f"Changed expectations ({len(report['changed_expectations'])}); review semantic equivalence:")
    lines.extend("- " + escape(json.dumps(entry, sort_keys=True)) for entry in report["changed_expectations"])
    return ("\n\n" if markdown else "\n").join(lines)
