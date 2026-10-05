"""Compare complete saved model runs offline without letting gains cancel regressions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from didyoureally.strict_json import loads  # noqa: E402

VERDICTS = {"backed", "contradicted", "phantom", "masked_failure", "unmentioned"}


class InvalidRun(ValueError):
    """A fixed diagnostic that contains no source or provider text."""


def require(condition, message):
    if not condition:
        raise InvalidRun(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def signature(items):
    require(isinstance(items, list), "Verdict lists are required")
    result = Counter()
    for item in items:
        require(isinstance(item, dict), "Invalid verdict entry")
        tool, verdict = item.get("tool"), item.get("verdict")
        require(isinstance(verdict, str) and verdict in VERDICTS, "Unknown verdict")
        require(tool is None or nonempty(tool), "Invalid verdict tool")
        result[(tool, verdict)] += 1
    return result


def read_run(folder):
    """Validate every planned slot before returning normalized comparison records."""
    metadata_bytes = (folder / "metadata.json").read_bytes()
    record_bytes = (folder / "records.jsonl").read_bytes()
    meta = loads(metadata_bytes.decode("utf-8"))
    rows = [loads(line) for line in record_bytes.decode("utf-8").splitlines() if line.strip()]
    require(isinstance(meta, dict) and meta.get("status") == "complete", "Run is not complete")
    cases, targets, repeats = meta.get("case_ids"), meta.get("targets"), meta.get("repeats")
    require(isinstance(cases, list) and cases and all(map(nonempty, cases)), "Invalid planned cases")
    require(len(set(cases)) == len(cases), "Duplicate planned cases")
    require(type(repeats) is int and 1 <= repeats <= 100, "Invalid repeat count")
    require(isinstance(targets, list) and targets, "Missing planned targets")
    target_models = {}
    for target in targets:
        require(isinstance(target, dict), "Invalid planned target")
        endpoint, model = target.get("id"), target.get("model")
        require(nonempty(endpoint) and nonempty(model), "Invalid target identity")
        require(endpoint not in target_models, "Duplicate target ID")
        require(model not in target_models.values(), "Repeated model names need separate comparison runs")
        target_models[endpoint] = model
    planned = len(cases) * len(targets) * repeats
    for name in ("planned_records", "completed_records"):
        require(type(meta.get(name)) is int and meta[name] == planned, "Run coverage metadata differs")
    require(len(rows) == planned, "Missing or extra records")
    for name in ("cases_sha256", "runner_sha256"):
        require(
            isinstance(meta.get(name), str) and re.fullmatch(r"[0-9a-f]{64}", meta[name]),
            "Missing or invalid provenance hash",
        )
    require(type(meta.get("json_mode")) is bool, "Missing JSON mode")
    require(type(meta.get("temperature")) in (int, float), "Missing temperature")
    require(meta.get("extraction_mode") in ("default", "staged"), "Invalid extraction mode")
    recorded_json_mode = any(isinstance(row, dict) and "json_mode" in row for row in rows)
    indexed = {}
    for row in rows:
        require(isinstance(row, dict), "Invalid record")
        endpoint, model = row.get("endpoint_id"), row.get("model")
        require(nonempty(endpoint) and target_models.get(endpoint) == model, "Unplanned record target")
        case, repeat = row.get("case"), row.get("repeat_index")
        require(nonempty(case) and case in cases, "Unplanned record case")
        require(type(repeat) is int and 1 <= repeat <= repeats, "Unplanned repeat index")
        require(row.get("extraction_mode") == meta["extraction_mode"], "Record extraction mode differs")
        if recorded_json_mode:
            require(type(row.get("json_mode")) is bool, "Every record must contain boolean JSON mode")
            require(row["json_mode"] == meta["json_mode"], "Record JSON mode differs from run metadata")
        key = (model, case, repeat)
        require(key not in indexed, "Duplicate record slot")
        expected = signature(row.get("expected"))
        error = "error" in row
        require(not error or nonempty(row["error"]), "Invalid extraction error")
        require(error or isinstance(row.get("claims"), list), "Missing successful extraction claims")
        got = signature(row.get("got", []) if error else row.get("got"))
        passed = not error and got == expected
        require(type(row.get("passed")) is bool and row["passed"] == passed, "Saved pass flag disagrees")
        require(isinstance(row.get("labeled_claims"), list), "Missing labeled claims")
        indexed[key] = {
            "passed": passed,
            "error": error,
            "expected": expected,
            "labels": row["labeled_claims"],
        }
    return (
        meta,
        indexed,
        {
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "records_sha256": hashlib.sha256(record_bytes).hexdigest(),
            "record_json_mode": "verified" if recorded_json_mode else "legacy_unverified",
        },
    )


def compare(baseline, candidate):
    before_meta, before, before_hashes = read_run(baseline)
    after_meta, after, after_hashes = read_run(candidate)
    for name in ("cases_sha256", "runner_sha256", "repeats", "json_mode", "temperature"):
        require(before_meta[name] == after_meta[name], "Run configuration or suite differs")
    require(before.keys() == after.keys(), "Compared model and case coverage differs")
    improvements, regressions, errors = [], [], []
    for key, old in before.items():
        new = after[key]
        require(old["expected"] == new["expected"] and old["labels"] == new["labels"], "Case labels differ")
        identity = dict(zip(("model", "case", "repeat_index"), key, strict=True))
        if old["passed"] and not new["passed"]:
            regressions.append(identity)
        elif not old["passed"] and new["passed"]:
            improvements.append(identity)
        if new["error"]:
            errors.append(identity)
    return {
        "gate_passed": not regressions and not errors,
        "paired_attempts": len(before),
        "baseline_exact": sum(row["passed"] for row in before.values()),
        "candidate_exact": sum(row["passed"] for row in after.values()),
        "candidate_mismatches": sum(not row["passed"] for row in after.values()),
        "improvements": improvements,
        "regressions": regressions,
        "candidate_errors": errors,
        "baseline_evidence": before_hashes,
        "candidate_evidence": after_hashes,
        "baseline_extraction_mode": before_meta["extraction_mode"],
        "candidate_extraction_mode": after_meta["extraction_mode"],
        "scope": "Verdict and tool counts only. Unchanged mismatches can pass a regression gate. This is not argument accuracy or proof of model identity.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="Complete run_llm_bench.py output directory")
    parser.add_argument("candidate", type=Path, help="Complete run with matching cases and models")
    args = parser.parse_args(argv)
    try:
        report = compare(args.baseline, args.candidate)
    except InvalidRun as exc:
        print(f"Cannot compare: {exc}.", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Do not echo private model replies, labels, paths, or provider diagnostics.
        print("Cannot compare: run evidence is incomplete, invalid, or incompatible.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
