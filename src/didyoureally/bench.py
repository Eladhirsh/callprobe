"""Run the seeded benchmark: traces with planted lies and known answers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import load_trace
from .extract import Extractor, GivenClaims
from .matcher import PROBLEM_VERDICTS, Verdict, check
from .schema import load_json


@dataclass
class CaseResult:
    case_id: str
    description: str
    expected: Counter
    got: Counter

    @property
    def passed(self) -> bool:
        return self.expected == self.got


@dataclass
class BenchResult:
    cases: list[CaseResult] = field(default_factory=list)

    def _problems(self, c: Counter) -> Counter:
        return Counter({k: n for k, n in c.items() if Verdict(k[0]) in PROBLEM_VERDICTS})

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.cases)

    def detection(self) -> tuple[int, int, int]:
        """(true positives, false positives, false negatives) over problem findings."""
        tp = fp = fn = 0
        for c in self.cases:
            e, g = self._problems(c.expected), self._problems(c.got)
            hit = sum((e & g).values())
            tp += hit
            fp += sum(g.values()) - hit
            fn += sum(e.values()) - hit
        return tp, fp, fn


def _signature(verdict: str, tool: str | None) -> tuple[str, str]:
    return (verdict, tool or "-")


def run_case(case: dict[str, Any], extractor: Extractor | None) -> CaseResult:
    trace = load_trace(case["trace"], case.get("id", "case"))
    ext = extractor or GivenClaims(case.get("claims", []))
    findings = check(trace, ext.extract(trace))
    got = Counter(_signature(f.verdict.value, (f.claim.tool if f.claim else f.call.tool)) for f in findings)
    expected = Counter(_signature(e["verdict"], e.get("tool")) for e in case["expected"])
    return CaseResult(case.get("id", "case"), case.get("description", ""), expected, got)


def default_cases_dir() -> Path:
    return Path(__file__).parent / "benchmark"


def run(cases_dir: Path | None = None, extractor: Extractor | None = None) -> BenchResult:
    folder = cases_dir or default_cases_dir()
    result = BenchResult()
    for path in sorted(folder.glob("*.json")):
        result.cases.append(run_case(load_json(path), extractor))
    return result


def render(result: BenchResult) -> str:
    lines = []
    for c in result.cases:
        mark = "pass" if c.passed else "FAIL"
        lines.append(f"{mark:4}  {c.case_id}  {c.description}")
        if not c.passed:
            missing = c.expected - c.got
            extra = c.got - c.expected
            if missing:
                lines.append(f"      missed: {sorted(missing.elements())}")
            if extra:
                lines.append(f"      extra:  {sorted(extra.elements())}")
    tp, fp, fn = result.detection()
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    lines.append("")
    lines.append(
        f"{result.passed}/{len(result.cases)} cases exact. "
        f"Problem detection: precision {precision:.0%}, recall {recall:.0%} "
        f"({tp} caught, {fp} false alarms, {fn} missed)."
    )
    return "\n".join(lines)
