"""Paired regression gates for completed joint agent runs, without model calls."""

from __future__ import annotations

import json
import math
from dataclasses import fields
from pathlib import Path

from .agent_io import read_agent_json
from .agent_session import load_agent_suite, require_auditor, run_episode, suite_hash
from .client import Completion
from .doctor import validate_endpoint
from .models import Call

AXES = ("decision_passed", "account_passed", "passed")


def _same(left, right):
    # JSON booleans are not interchangeable with integers in saved evidence.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_provenance(report):
    config = report.get("config")
    if not isinstance(config, dict):
        raise ValueError("agent report is missing comparison provenance")
    for key in (
        "agent_model",
        "extractor_model",
        "agent_endpoint",
        "extractor_endpoint",
    ):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError("agent report has invalid model or endpoint settings")
    for key in ("max_turns", "max_tokens", "agent_retries"):
        if type(config.get(key)) is not int or config[key] < (0 if key == "agent_retries" else 1):
            raise ValueError("agent report has invalid request settings")
    if config["max_turns"] > 100 or type(config.get("extractor_json_mode")) is not bool:
        raise ValueError("agent report has invalid request settings")
    for key in ("agent_timeout", "extractor_timeout", "temperature"):
        value = config.get(key)
        if not _finite_number(value) or value < 0:
            raise ValueError("agent report has invalid request settings")
        if key != "temperature" and value == 0:
            raise ValueError("agent report has invalid request settings")
    for prefix in ("agent", "extractor"):
        validate_endpoint(config[prefix + "_endpoint"], config[prefix + "_timeout"])
    sources = report.get("source_sha256")
    if not isinstance(sources, dict):
        raise ValueError("agent report is missing source hashes")
    required = {
        "callprobe": {
            "__init__.py",
            "agent_cli.py",
            "agent_session.py",
            "client.py",
            "scoring.py",
            "models.py",
            "coerce.py",
        },
        "didyoureally": {
            "__init__.py",
            "schema.py",
            "matcher.py",
            "extract.py",
            "adapters.py",
        },
    }
    for engine, names in required.items():
        hashes = sources.get(engine)
        if (
            not isinstance(hashes, dict)
            or not names <= hashes.keys()
            or any(
                not isinstance(name, str)
                or Path(name).name != name
                or not name.endswith(".py")
                or not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
                for name, value in hashes.items()
            )
        ):
            raise ValueError("agent report is missing source hashes")


def _completion(raw):
    if not isinstance(raw, dict) or set(raw) != {f.name for f in fields(Completion)}:
        raise ValueError("agent report has invalid completion evidence")
    for key in ("content", "reasoning", "finish_reason"):
        if not isinstance(raw[key], str):
            raise ValueError("agent report has invalid completion evidence")
    if raw["error"] is not None and raw["error"] != "request_error":
        raise ValueError("agent report has invalid completion error")
    if not isinstance(raw["raw"], dict) or not isinstance(raw["calls"], list):
        raise ValueError("agent report has invalid completion evidence")
    for key in ("prompt_tokens", "completion_tokens"):
        if type(raw[key]) is not int or raw[key] < 0:
            raise ValueError("agent report has invalid completion usage")
    if not _finite_number(raw["latency_ms"]) or raw["latency_ms"] < 0:
        raise ValueError("agent report has invalid completion latency")
    calls = []
    for call in raw["calls"]:
        if not isinstance(call, dict) or set(call) != set(Call.model_fields):
            raise ValueError("agent report has invalid tool call evidence")
        try:
            calls.append(Call.model_validate(call, strict=True))
        except ValueError:
            raise ValueError("agent report has invalid tool call evidence") from None
    return Completion(**{**raw, "calls": calls})


def _replay_episode(row, case, config):
    dyr = require_auditor()
    from didyoureally.extract import ExtractionError

    raw = row.get("completions")
    if not isinstance(raw, list) or not 1 <= len(raw) <= config["max_turns"]:
        raise ValueError("agent report has invalid completion coverage")
    completions = [_completion(c) for c in raw]
    audit = row.get("audit")
    if not isinstance(audit, dict) or audit.get("status") not in (
        "complete",
        "incomplete",
    ):
        raise ValueError("agent report has invalid audit evidence")
    claims = audit.get("claims")
    if not isinstance(claims, list):
        raise ValueError("agent report has invalid claim evidence")
    parsed = []
    for claim in claims:
        if (
            not isinstance(claim, dict)
            or set(claim) != {f.name for f in fields(dyr.Claim)}
            or not isinstance(claim["text"], str)
            or not isinstance(claim["args"], dict)
            or (claim["tool"] is not None and not isinstance(claim["tool"], str))
            or (claim["group_id"] is not None and not isinstance(claim["group_id"], str))
            or type(claim["message_index"]) is not int
            or claim["message_index"] < 0
        ):
            raise ValueError("agent report has invalid claim evidence")
        parsed.append(dyr.Claim(**claim))
    requests = row.get("extraction_requests")
    if not isinstance(requests, list) or any(
        not isinstance(item, dict)
        or set(item) != {"request", "response"}
        or not isinstance(item["request"], dict)
        or not isinstance(item["response"], dict)
        for item in requests
    ):
        raise ValueError("agent report has invalid extraction evidence")
    error = audit.get("error")
    if audit["status"] == "incomplete" and (
        not isinstance(error, dict)
        or set(error) != {"message_index", "reason"}
        or not isinstance(error["reason"], str)
        or not error["reason"]
        or type(error["message_index"]) is not int
        or error["message_index"] < 0
    ):
        raise ValueError("agent report has invalid extraction error")

    class RecordedClient:
        used = 0

        def complete(self, *args, **kwargs):
            if self.used >= len(completions):
                raise ValueError("agent report is missing a completion")
            item = completions[self.used]
            self.used += 1
            return item

    class RecordedClaims:
        def extract(self, trace):
            messages = {m.index: m.content for m in trace.assistant_messages()}
            if audit["status"] == "incomplete":
                if error["message_index"] not in messages:
                    raise ValueError("extraction error does not identify an assistant message")
                raise ExtractionError(error["message_index"], error["reason"])
            if any(messages.get(c.message_index) != c.text for c in parsed):
                raise ValueError("saved claim does not identify its assistant message")
            return parsed

    client = RecordedClient()
    replay = run_episode(
        case,
        client,
        RecordedClaims(),
        model=config["agent_model"],
        max_turns=config["max_turns"],
        max_tokens=config["max_tokens"],
    )
    if client.used != len(completions):
        raise ValueError("agent report has completions after the episode ended")
    for key in (
        "status",
        "agent_status",
        "decision_passed",
        "account_passed",
        "passed",
        "missing_decision_turns",
        "decisions",
        "audit",
        "executions",
        "trace",
        "conversation",
    ):
        if key not in row or not _same(row[key], replay[key]):
            raise ValueError(
                f"agent report {key} does not reproduce from saved evidence; "
                "the evidence is inconsistent or the installed evaluator behavior changed"
            )
    versions = row.get("versions")
    if not isinstance(versions, dict) or not {"callprobe", "scoring", "didyoureally"} <= versions.keys():
        raise ValueError("agent report is missing episode versions")
    if type(versions["scoring"]) is not int or not all(
        isinstance(versions[name], str) and versions[name] for name in ("callprobe", "didyoureally")
    ):
        raise ValueError("agent report has invalid episode versions")


def load_agent_run(path: str) -> dict:
    file = Path(path)
    report = read_agent_json(file)
    suite = load_agent_suite(read_agent_json(file.parent / "suite.json"))
    if (
        not isinstance(report, dict)
        or type(report.get("format_version")) is not int
        or report["format_version"] != 1
    ):
        raise ValueError("unsupported agent report format")
    if report.get("status") != "complete" or report.get("execution") != "declarative_mocks":
        raise ValueError("agent comparison requires completed mock runs")
    if report.get("suite_hash") != suite_hash(suite):
        raise ValueError("agent report does not match its frozen suite.json")
    _validate_provenance(report)
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
        if len(expected[row["case_id"]].expected) > report["config"]["max_turns"]:
            raise ValueError("agent report has insufficient planned turns")
        try:
            _replay_episode(row, expected[row["case_id"]], report["config"])
        except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
            raise ValueError("agent report has malformed episode evidence") from exc
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
    names = {
        "decision_passed": "Decisions",
        "account_passed": "Account",
        "passed": "Both",
    }
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
        lines.extend(
            [
                "",
                "Incomplete on at least one side: " + ", ".join(result["incomplete_cases"]) + ".",
            ]
        )
    lines.extend(
        [
            "",
            "Regression gate: " + ("pass" if result["gate_passed"] else "fail") + ".",
            (
                "This checks for regressions, not that either run passed every case. "
                "Matching model tags do not verify served weights."
            ),
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
