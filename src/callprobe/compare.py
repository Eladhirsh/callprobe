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
