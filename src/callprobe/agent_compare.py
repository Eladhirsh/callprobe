"""Paired regression gates for completed joint agent runs, without model calls."""

from __future__ import annotations

import json
from pathlib import Path

from .agent_session import load_agent_suite, suite_hash

AXES = ("decision_passed", "account_passed", "passed")


def load_agent_run(path: str) -> dict:
    file = Path(path)
    report = json.loads(file.read_text(encoding="utf-8"))
    suite = load_agent_suite(json.loads((file.parent / "suite.json").read_text(encoding="utf-8")))
    if not isinstance(report, dict) or report.get("format_version") != 1:
        raise ValueError("unsupported agent report format")
    if report.get("status") != "complete" or report.get("execution") != "declarative_mocks":
        raise ValueError("agent comparison requires completed mock runs")
    if report.get("suite_hash") != suite_hash(suite):
        raise ValueError("agent report does not match its frozen suite.json")
    expected = {case.id: case for case in suite.cases}
    rows = report.get("episodes")
    if (
        type(report.get("planned_cases")) is not int
        or report["planned_cases"] != len(expected)
        or not isinstance(rows, list)
        or len(rows) != len(expected)
    ):
        raise ValueError("agent report has incomplete case coverage")
    seen = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("case_id"), str)
            or row["case_id"] not in expected
        ):
            raise ValueError("agent report has an unknown case")
        if row["case_id"] in seen:
            raise ValueError("agent report has duplicate cases")
        seen.add(row["case_id"])
        if row.get("status") not in ("complete", "incomplete"):
            raise ValueError("agent report has an invalid episode status")
        for axis in AXES:
            value = row.get(axis)
            if not (type(value) is bool or (axis == "account_passed" and value is None)):
                raise ValueError("agent report has invalid result flags")
        audit = row.get("audit", {})
        if (
            not isinstance(audit, dict)
            or audit.get("status") not in ("complete", "incomplete")
            or not isinstance(audit.get("findings"), list)
        ):
            raise ValueError("agent report has invalid audit evidence")
        if audit["status"] == "incomplete":
            account_passed = None
        else:
            if any(
                not isinstance(f, dict)
                or f.get("verdict")
                not in ("backed", "contradicted", "phantom", "masked_failure", "unmentioned")
                or not isinstance(f.get("unchecked"), list)
                for f in audit["findings"]
            ):
                raise ValueError("agent report has invalid findings")
            account_passed = not any(f["verdict"] != "backed" or f["unchecked"] for f in audit["findings"])
        decisions = row.get("decisions")
        if (
            not isinstance(decisions, list)
            or not decisions
            or any(not isinstance(d, dict) or type(d.get("success")) is not bool for d in decisions)
        ):
            raise ValueError("agent report has invalid decision evidence")
        planned = len(expected[row["case_id"]].expected)
        missing = list(range(len(decisions), planned))
        decision_passed = len(decisions) == planned and all(d["success"] for d in decisions)
        complete = row.get("agent_status") == "complete" and audit["status"] == "complete"
        if (
            row.get("missing_decision_turns") != missing
            or row["decision_passed"] != decision_passed
            or row["account_passed"] != account_passed
            or (row["status"] == "complete") != complete
            or row["passed"] != (complete and decision_passed and account_passed is True)
        ):
            raise ValueError("agent report flags disagree with their evidence")
    if not isinstance(report.get("config"), dict) or not isinstance(report.get("source_sha256"), dict):
        raise ValueError("agent report is missing comparison provenance")
    for engine in ("callprobe", "didyoureally"):
        hashes = report["source_sha256"].get(engine)
        if (
            not isinstance(hashes, dict)
            or not hashes
            or any(
                not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
                for h in hashes.values()
            )
        ):
            raise ValueError("agent report is missing source hashes")
    for field in (
        "agent_model",
        "agent_endpoint",
        "extractor_model",
        "extractor_endpoint",
        "max_turns",
        "max_tokens",
        "agent_timeout",
        "extractor_timeout",
        "extractor_json_mode",
        "temperature",
        "agent_retries",
    ):
        if field not in report["config"]:
            raise ValueError("agent report is missing model or request settings")
    return report


def compare_agent_runs(baseline: dict, candidate: dict) -> dict:
    if baseline["suite_hash"] != candidate["suite_hash"]:
        raise ValueError("agent runs use different suites")
    if baseline["source_sha256"] != candidate["source_sha256"]:
        raise ValueError("agent runs use different evaluator or runner source")
    if baseline["config"].keys() != candidate["config"].keys():
        raise ValueError("agent runs have different configuration fields")
    for key in baseline["config"]:
        if key not in ("agent_model", "agent_endpoint") and baseline["config"][key] != candidate[
            "config"
        ].get(key):
            raise ValueError(f"agent runs differ in {key}; keep extraction and request settings fixed")
    left = {r["case_id"]: r for r in baseline["episodes"]}
    right = {r["case_id"]: r for r in candidate["episodes"]}
    if left.keys() != right.keys():
        raise ValueError("agent runs cover different cases")
    incomplete = [
        key for key in left if left[key]["status"] != "complete" or right[key]["status"] != "complete"
    ]
    paired = [key for key in left if key not in incomplete]
    axes = {}
    for name in AXES:
        improved = [key for key in paired if not left[key][name] and right[key][name]]
        regressed = [key for key in paired if left[key][name] and not right[key][name]]
        axes[name] = {
            "baseline_passed": sum(left[key][name] for key in paired),
            "candidate_passed": sum(right[key][name] for key in paired),
            "improved": improved,
            "regressed": regressed,
        }
    return {
        "baseline_model": baseline["config"]["agent_model"],
        "candidate_model": candidate["config"]["agent_model"],
        "cases": len(left),
        "paired_complete_cases": len(paired),
        "incomplete_cases": incomplete,
        "axes": axes,
        "gate_passed": not incomplete and not any(a["regressed"] for a in axes.values()),
        "suite_hash": baseline["suite_hash"],
    }


def render_agent_comparison(result: dict) -> str:
    names = {"decision_passed": "Decisions", "account_passed": "Account", "passed": "Both"}
    total = result["paired_complete_cases"]
    lines = [
        "# Agent regression comparison",
        "",
        f"Complete paired cases: {total}/{result['cases']}.",
        "",
        "| Check | Baseline passes | Candidate passes | Improved | Regressed |",
        "|---|---|---|---|---|",
    ]
    for key, axis in result["axes"].items():
        lines.append(
            f"| {names[key]} | {axis['baseline_passed']}/{total} | "
            f"{axis['candidate_passed']}/{total} | {len(axis['improved'])} | {len(axis['regressed'])} |"
        )
    for key, axis in result["axes"].items():
        if axis["regressed"]:
            lines.extend(["", f"{names[key]} regressions: " + ", ".join(axis["regressed"]) + "."])
        if axis["improved"]:
            lines.extend(["", f"{names[key]} improvements: " + ", ".join(axis["improved"]) + "."])
    if result["incomplete_cases"]:
        lines.extend(["", "Incomplete on at least one side: " + ", ".join(result["incomplete_cases"]) + "."])
    lines.extend(
        [
            "",
            "Regression gate: " + ("pass" if result["gate_passed"] else "fail") + ".",
            "This checks for regressions, not that either run passed every case. "
            "Matching model tags do not verify served weights.",
            "",
        ]
    )
    return "\n".join(lines)


def agent_compare_main(args):
    baseline, candidate = load_agent_run(args.baseline), load_agent_run(args.candidate)
    result = compare_agent_runs(baseline, candidate)
    print(json.dumps(result, indent=2) if args.format == "json" else render_agent_comparison(result))
    if args.fail_on_regression:
        if result["incomplete_cases"]:
            return 3
        if not result["gate_passed"]:
            return 1
    return 0
