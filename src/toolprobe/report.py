"""Turn a Run into something a human can act on.

The headline number is cost per success, not latency. Tokens spent divided
by calls that were actually correct is what decides whether a local model is
viable for an agent loop.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from .models import Run, TaskResult


def _rate(results: list[TaskResult], field: str) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if getattr(r, field)) / len(results)


def summarize(run: Run) -> dict:
    results = run.results
    by_pad: dict[int, list[TaskResult]] = defaultdict(list)
    by_category: dict[str, list[TaskResult]] = defaultdict(list)
    by_depth_bucket: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        by_pad[r.pad].append(r)
        by_category[r.category].append(r)

    successes = sum(1 for r in results if r.success)
    tokens = sum(r.total_tokens for r in results)
    wall_ms = sum(r.latency_ms for r in results)

    # Variance across repeats: per pad level, the spread of run-level pass rates.
    spread: dict[int, float] = {}
    for pad, group in by_pad.items():
        per_repeat: dict[int, list[TaskResult]] = defaultdict(list)
        for r in group:
            per_repeat[r.repeat].append(r)
        rates = [_rate(v, "success") for v in per_repeat.values()]
        spread[pad] = statistics.pstdev(rates) if len(rates) > 1 else 0.0

    return {
        "model": run.config.model,
        "quantization": run.config.quantization,
        "endpoint": run.config.endpoint,
        "n": len(results),
        "overall": {
            "selection": _rate(results, "selection_ok"),
            "schema": _rate(results, "schema_ok"),
            "args": _rate(results, "args_ok"),
            "success": _rate(results, "success"),
        },
        "by_pad": {
            pad: {
                "success": _rate(group, "success"),
                "selection": _rate(group, "selection_ok"),
                "stdev": spread[pad],
                "n": len(group),
            }
            for pad, group in sorted(by_pad.items())
        },
        "by_category": {
            name: {"success": _rate(group, "success"), "n": len(group)}
            for name, group in sorted(by_category.items())
        },
        "cost": {
            "tokens_per_success": (tokens / successes) if successes else float("inf"),
            "seconds_per_success": (
                (wall_ms / 1000) / successes if successes else float("inf")
            ),
            "total_tokens": tokens,
            "successes": successes,
        },
        "errors": sum(1 for r in results if r.error),
        "truncated": sum(1 for r in results if r.truncated),
    }


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def render_text(run: Run) -> str:
    s = summarize(run)
    lines = [
        f"model            {s['model']}"
        + (f"  ({s['quantization']})" if s["quantization"] else ""),
        f"endpoint         {s['endpoint']}",
        f"tasks scored     {s['n']}"
        + (f"   errors: {s['errors']}" if s["errors"] else "")
        + (f"   truncated: {s['truncated']}" if s["truncated"] else ""),
        "",
        "                 selection   schema     args      success",
        "  overall        "
        + "  ".join(
            _pct(s["overall"][k]) for k in ("selection", "schema", "args", "success")
        ),
        "",
        "  tool count sweep",
    ]
    for pad, row in s["by_pad"].items():
        lines.append(
            f"    +{pad:<3} distractors   success {_pct(row['success'])}"
            f"   selection {_pct(row['selection'])}"
            f"   sd {row['stdev'] * 100:4.1f}"
        )
    lines.append("")
    lines.append("  by category")
    for name, row in s["by_category"].items():
        lines.append(f"    {name:<10} {_pct(row['success'])}  (n={row['n']})")
    lines.append("")
    cost = s["cost"]
    if cost["successes"]:
        lines.append(
            f"  cost per success   {cost['tokens_per_success']:.0f} tokens"
            f"   {cost['seconds_per_success']:.2f} s"
        )
    else:
        lines.append("  cost per success   no successful calls")
    return "\n".join(lines)


def render_markdown(runs: list[Run]) -> str:
    """Leaderboard table across models. This is the artifact people link to."""
    header = (
        "| model | quant | success | selection | schema | args | "
        "success @ +16 tools | tokens per success |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for run in runs:
        s = summarize(run)
        padded = s["by_pad"].get(16) or s["by_pad"].get(max(s["by_pad"], default=0))
        tps = s["cost"]["tokens_per_success"]
        rows.append(
            "| {model} | {quant} | {success} | {selection} | {schema} | {args} | "
            "{padded} | {tps} |".format(
                model=s["model"],
                quant=s["quantization"] or "-",
                success=_pct(s["overall"]["success"]).strip(),
                selection=_pct(s["overall"]["selection"]).strip(),
                schema=_pct(s["overall"]["schema"]).strip(),
                args=_pct(s["overall"]["args"]).strip(),
                padded=_pct(padded["success"]).strip() if padded else "-",
                tps=f"{tps:.0f}" if tps != float("inf") else "-",
            )
        )
    return "\n".join([header, *rows])


def failure_digest(run: Run, limit: int = 15) -> str:
    """The part that turns a benchmark into a bug report."""
    lines = ["failures worth reading:"]
    shown = 0
    for r in run.results:
        if r.success or not r.failures:
            continue
        lines.append(f"  [{r.task_id} pad={r.pad}] " + "; ".join(r.failures[:2]))
        if r.called is None and r.response_text:
            said = r.response_text.replace("\n", " ")[:160]
            lines.append(f"      said: {said}")
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        lines.append("  none")
    return "\n".join(lines)
