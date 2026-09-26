"""Human-readable and JSON reports."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from .matcher import Finding, Verdict
from .schema import Trace

LABELS = {
    Verdict.BACKED: "Backed",
    Verdict.CONTRADICTED: "Contradicted",
    Verdict.PHANTOM: "Phantom",
    Verdict.MASKED_FAILURE: "Masked failure",
    Verdict.UNMENTIONED: "Unmentioned",
}
COLORS = {
    Verdict.BACKED: "32",
    Verdict.CONTRADICTED: "31",
    Verdict.PHANTOM: "31",
    Verdict.MASKED_FAILURE: "31",
    Verdict.UNMENTIONED: "33",
}
ORDER = [Verdict.CONTRADICTED, Verdict.PHANTOM, Verdict.MASKED_FAILURE, Verdict.UNMENTIONED, Verdict.BACKED]


def _color(text: str, code: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def render_text(trace: Trace, findings: list[Finding], color: bool = False) -> str:
    lines = [
        f"Trace {trace.id}: {len(trace.calls)} tool calls, {len(trace.assistant_messages())} agent messages"
    ]
    counts = {v: 0 for v in Verdict}
    for f in findings:
        counts[f.verdict] += 1
    lines.append("  ".join(f"{LABELS[v]} {counts[v]}" for v in ORDER))
    lines.append("")
    for f in sorted(findings, key=lambda f: ORDER.index(f.verdict)):
        tag = _color(f"[{LABELS[f.verdict]}]", COLORS[f.verdict], color)
        if f.claim is not None:
            lines.append(f'{tag} "{f.claim.text}"')
        else:
            lines.append(f"{tag} {f.call.tool}({json.dumps(f.call.args)})")
        lines.append(f"    {f.explanation}")
        if f.call is not None and f.claim is not None:
            lines.append(f"    Call {f.call.id}: {f.call.tool}({json.dumps(f.call.args)}) -> {f.call.status}")
        if f.unchecked:
            lines.append(f"    Could not verify: {', '.join(f.unchecked)}")
    return "\n".join(lines)


def render_json(trace: Trace, findings: list[Finding]) -> str:
    out: dict[str, Any] = {
        "trace_id": trace.id,
        "summary": {v.value: sum(1 for f in findings if f.verdict == v) for v in Verdict},
        "findings": [f.to_dict() for f in findings],
    }
    return json.dumps(out, indent=2, default=str)
