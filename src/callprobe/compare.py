"""Diff two runs: per-category rate deltas and which tasks flipped."""

from __future__ import annotations

from collections import defaultdict

from .models import Run, TaskResult


def _rate(results: list[TaskResult], field: str) -> float:
    scored = [r for r in results if not r.error]
    if not scored:
        return 0.0
    return sum(1 for r in scored if getattr(r, field)) / len(scored)


def _group_by_category(results: list[TaskResult]) -> dict[str, list[TaskResult]]:
    grouped: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        grouped[r.category].append(r)
    return grouped


def category_deltas(a: Run, b: Run) -> dict[str, dict[str, float]]:
    by_cat_a = _group_by_category(a.results)
    by_cat_b = _group_by_category(b.results)
    out: dict[str, dict[str, float]] = {}
    for category in sorted(set(by_cat_a) | set(by_cat_b)):
        ra, rb = by_cat_a.get(category, []), by_cat_b.get(category, [])
        success_a, success_b = _rate(ra, "success"), _rate(rb, "success")
        lenient_a, lenient_b = _rate(ra, "success_lenient"), _rate(rb, "success_lenient")
        out[category] = {
            "success_a": success_a,
            "success_b": success_b,
            "success_delta": success_b - success_a,
            "lenient_a": lenient_a,
            "lenient_b": lenient_b,
            "lenient_delta": lenient_b - lenient_a,
        }
    return out


def _task_verdicts(results: list[TaskResult]) -> dict[str, bool]:
    """One id per task, aggregated across every pad and repeat it ran at.

    A task counts as a pass for a run only if it succeeded every time it
    was tried; errored instances are excluded rather than counted as fails.
    """
    grouped: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        if r.error:
            continue
        grouped[r.task_id].append(r)
    return {task_id: all(r.success for r in rs) for task_id, rs in grouped.items() if rs}


def flipped_tasks(a: Run, b: Run) -> tuple[list[str], list[str]]:
    """(pass_to_fail, fail_to_pass) task ids, aggregated across pads/repeats.

    Only task ids present in both runs are compared.
    """
    va, vb = _task_verdicts(a.results), _task_verdicts(b.results)
    common = sorted(set(va) & set(vb))
    pass_to_fail = [t for t in common if va[t] and not vb[t]]
    fail_to_pass = [t for t in common if not va[t] and vb[t]]
    return pass_to_fail, fail_to_pass


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta(value: float) -> str:
    return f"{value * 100:+.1f}%"


def render_compare(a: Run, b: Run) -> str:
    scored_a = [r for r in a.results if not r.error]
    scored_b = [r for r in b.results if not r.error]
    lines = [
        f"{a.config.model}  ->  {b.config.model}",
        f"scored observations: {len(scored_a)} -> {len(scored_b)}",
        f"request errors: {len(a.results) - len(scored_a)} -> {len(b.results) - len(scored_b)}",
        "",
    ]
    categories_a = _group_by_category(scored_a)
    categories_b = _group_by_category(scored_b)
    header = f"{'category':<10} {'success a':>10} {'success b':>10} {'delta':>8}   {'lenient a':>10} {'lenient b':>10} {'delta':>8}"
    lines.append(header)
    for category, d in category_deltas(a, b).items():
        has_a, has_b = bool(categories_a.get(category)), bool(categories_b.get(category))
        success_a = _pct(d["success_a"]) if has_a else "n/a"
        success_b = _pct(d["success_b"]) if has_b else "n/a"
        success_delta = _delta(d["success_delta"]) if has_a and has_b else "n/a"
        lenient_a = _pct(d["lenient_a"]) if has_a else "n/a"
        lenient_b = _pct(d["lenient_b"]) if has_b else "n/a"
        lenient_delta = _delta(d["lenient_delta"]) if has_a and has_b else "n/a"
        lines.append(
            f"{category:<10} {success_a:>10} {success_b:>10} "
            f"{success_delta:>8}   {lenient_a:>10} "
            f"{lenient_b:>10} {lenient_delta:>8}"
        )

    pass_to_fail, fail_to_pass = flipped_tasks(a, b)
    lines.append("")
    lines.append(f"pass -> fail ({len(pass_to_fail)}):")
    lines += [f"  {t}" for t in pass_to_fail] or ["  none"]
    lines.append("")
    lines.append(f"fail -> pass ({len(fail_to_pass)}):")
    lines += [f"  {t}" for t in fail_to_pass] or ["  none"]
    return "\n".join(lines)


_MD_ESCAPE_CHARS = "\\`*_[]()#|"


def _escape_md(value) -> str:
    """Neutralize a user-controlled value so it cannot inject Markdown/HTML
    structure (tables, headings, links, emphasis) into an exported report.
    """
    text = "" if value is None else str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for ch in _MD_ESCAPE_CHARS:
        text = text.replace(ch, "\\" + ch)
    return text


def render_compare_markdown(a: Run, b: Run, gate: dict | None = None) -> str:
    """Markdown rendering of the same comparison, safe to paste into a PR or
    CI summary. All values that originate from suite/results content
    (model labels, task ids, hashes, gate failure text) are escaped so they
    cannot inject Markdown/HTML structure; no raw prompts or arguments are
    included.
    """
    scored_a = [r for r in a.results if not r.error]
    scored_b = [r for r in b.results if not r.error]

    lines = [
        "## Comparison",
        "",
        f"**Baseline model:** {_escape_md(a.config.model)}  ",
        f"**Candidate model:** {_escape_md(b.config.model)}",
        "",
        f"- Scored observations: {len(scored_a)} -> {len(scored_b)}",
        f"- Request errors: {len(a.results) - len(scored_a)} -> {len(b.results) - len(scored_b)}",
        "",
    ]

    warnings: list[str] = []
    if a.config.selected_task_ids is not None or b.config.selected_task_ids is not None:
        warnings.append("comparing targeted debug run(s), not full benchmark coverage")
    hash_a, hash_b = a.config.suite_hash, b.config.suite_hash
    if not hash_a or not hash_b or hash_a != hash_b:
        warnings.append(
            f"suite hashes differ or are missing (a={_escape_md(hash_a or 'missing')}, "
            f"b={_escape_md(hash_b or 'missing')}); some of this delta may be the suite "
            "changing, not the model"
        )
    if (a.config.scoring_version is None or b.config.scoring_version is None
            or a.config.scoring_version != b.config.scoring_version):
        warnings.append(
            f"scoring versions differ or are missing (a={_escape_md(a.config.scoring_version)}, "
            f"b={_escape_md(b.config.scoring_version)}); scores are not directly comparable"
        )
    if warnings:
        lines.append("> **Warning**")
        lines += [f"> - {w}" for w in warnings]
        lines.append("")

    categories_a = _group_by_category(scored_a)
    categories_b = _group_by_category(scored_b)
    lines.append("| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for category, d in category_deltas(a, b).items():
        has_a, has_b = bool(categories_a.get(category)), bool(categories_b.get(category))
        success_a = _pct(d["success_a"]) if has_a else "n/a"
        success_b = _pct(d["success_b"]) if has_b else "n/a"
        success_delta = _delta(d["success_delta"]) if has_a and has_b else "n/a"
        lenient_a = _pct(d["lenient_a"]) if has_a else "n/a"
        lenient_b = _pct(d["lenient_b"]) if has_b else "n/a"
        lenient_delta = _delta(d["lenient_delta"]) if has_a and has_b else "n/a"
        lines.append(
            f"| {_escape_md(category)} | {success_a} | {success_b} | {success_delta} | "
            f"{lenient_a} | {lenient_b} | {lenient_delta} |"
        )
    lines.append("")

    pass_to_fail, fail_to_pass = flipped_tasks(a, b)
    lines.extend([f"**Pass -> fail ({len(pass_to_fail)}):**", ""])
    lines += [f"- {_escape_md(t)}" for t in pass_to_fail] or ["- none"]
    lines.append("")
    lines.extend([f"**Fail -> pass ({len(fail_to_pass)}):**", ""])
    lines += [f"- {_escape_md(t)}" for t in fail_to_pass] or ["- none"]
    lines.append("")

    if gate is None:
        lines.append("**CI gate:** not requested")
    else:
        lines.append(f"**CI gate:** {'PASS' if gate['passed'] else 'FAIL'}")
        if gate["failures"]:
            lines.append("")
            lines.extend(["Gate failure reasons:", ""])
            lines += [f"- {_escape_md(f)}" for f in gate["failures"]]
        if gate["regressions"]:
            lines.append("")
            lines.extend(["Regressed observations:", ""])
            lines += [
                f"- {_escape_md(r['task_id'])} pad={_escape_md(r['pad'])} repeat={_escape_md(r['repeat'])}"
                for r in gate["regressions"]
            ]

    return "\n".join(lines)
