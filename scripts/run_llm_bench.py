"""Evaluate real extraction across the bundled synthetic domains, saving diagnostic evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from didyoureally.adapters import load_trace
from didyoureally.bench import default_cases_dir
from didyoureally.extract import SYSTEM_PROMPT, LLMExtractor, _http_post
from didyoureally.matcher import PROBLEM_VERDICTS, check

PROBLEMS = {v.value for v in PROBLEM_VERDICTS}


def domain(case):
    if case.get("domain") in {"email", "support", "files", "scheduling"}:
        return case["domain"]
    names = {e.get("tool") for e in case["expected"]}
    names |= {c.get("tool") for c in case["claims"]}
    if names & {"delete_file", "read_file"} or "read_is_not_delete" in case["id"]:
        return "files"
    if names & {"book_meeting", "update_event", "invite"}:
        return "scheduling"
    if names & {"issue_refund", "cancel_subscription", "apply_credit"}:
        return "support"
    if "cancel" in case["id"] or "refund" in case["id"]:
        return "support"
    return "email"


def signatures(items):
    return Counter((item["verdict"], item.get("tool")) for item in items)


def summarize(rows):
    tp = fp = fn = 0
    for row in rows:
        expected = signatures([x for x in row["expected"] if x["verdict"] in PROBLEMS])
        got = signatures([x for x in row.get("got", []) if x["verdict"] in PROBLEMS])
        tp += sum((expected & got).values())
        fp += sum((got - expected).values())
        fn += sum((expected - got).values())
    honest = [r for r in rows if all(e["verdict"] == "backed" for e in r["expected"])]
    return {
        "cases": len(rows),
        "exact": sum(r["passed"] for r in rows),
        "errors": sum("error" in r for r in rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "honest_cases": len(honest),
        "honest_false_alarms": sum(any(x["verdict"] in PROBLEMS for x in r.get("got", [])) for r in honest),
        "unchecked_findings": sum(bool(f["unchecked"]) for r in rows for f in r.get("findings", [])),
    }


def evaluate(case, base_url, model):
    raw = []

    def capture(url, headers, body):
        response = _http_post(url, headers, body)
        raw.append(response["choices"][0]["message"]["content"])
        return response

    row = {
        "case": case["id"],
        "domain": domain(case),
        "model": model,
        "expected": case["expected"],
        "labeled_claims": case["claims"],
        "passed": False,
    }
    started = time.monotonic()
    try:
        trace = load_trace(case["trace"], case["id"])
        claims = LLMExtractor(base_url=base_url, model=model, transport=capture).extract(trace)
        findings = check(trace, claims)
        row["claims"] = [asdict(c) for c in claims]
        row["findings"] = [f.to_dict() for f in findings]
        row["got"] = [
            {"verdict": f.verdict.value, "tool": f.claim.tool if f.claim else f.call.tool} for f in findings
        ]
        row["passed"] = signatures(row["got"]) == signatures(row["expected"])
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Provider error messages can contain secrets. Record only the exception type.
        row["error"] = type(exc).__name__
    row["raw_responses"] = raw
    row["seconds"] = round(time.monotonic() - started, 3)
    return row


def markdown(rows):
    lines = [
        "# Real-model extraction on synthetic traces",
        "",
        "Development fixtures, not held-out accuracy. Verdicts remain deterministic.",
        "",
        "| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model in dict.fromkeys(r["model"] for r in rows):
        for group in ["all", "email", "support", "files", "scheduling"]:
            selected = [r for r in rows if r["model"] == model and (group == "all" or r["domain"] == group)]
            if not selected:
                continue
            s = summarize(selected)
            precision = "n/a" if s["precision"] is None else f"{s['precision']:.1%}"
            recall = "n/a" if s["recall"] is None else f"{s['recall']:.1%}"
            lines.append(
                f"| {model} | {group} | {s['exact']}/{s['cases']} | {precision} | {recall} | "
                f"{s['errors']} | {s['honest_false_alarms']}/{s['honest_cases']} | "
                f"{s['unchecked_findings']} |"
            )
    lines += [
        "",
        "Exact compares verdict and tool counts, not claim wording or call identity.",
        "Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems",
        "in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.",
        "Unchecked counts findings with details that could not be compared.",
        "Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", nargs=2, action="append", required=True, metavar=("BASE_URL", "MODEL"))
    parser.add_argument("--out", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--cases", type=Path, default=default_cases_dir(), help="Synthetic case directory")
    parser.add_argument("--case", action="append", help="Only these case IDs (repeatable)")
    args = parser.parse_args(argv)
    cases = [json.loads(p.read_text()) for p in sorted(args.cases.glob("*.json"))]
    if not cases:
        parser.error("No benchmark cases found")
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        parser.error("Duplicate benchmark IDs detected; remove duplicate exports before measuring accuracy")
    if args.case:
        if set(args.case) - set(ids):
            parser.error("Unknown case IDs")
        cases = [c for c in cases if c["id"] in args.case]
    args.out.mkdir(parents=True, exist_ok=False)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    metadata = {
        "revision": revision.stdout.strip(),
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "cases_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "models": [model for _, model in args.endpoint],
        "temperature": 0,
        "label": "Synthetic development transcripts, real extraction models",
    }
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows = []
    with (args.out / "records.jsonl").open("w") as stream:
        for base_url, model in args.endpoint:
            for case in cases:
                row = evaluate(case, base_url, model)
                rows.append(row)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
                print(f"{model} {case['id']}: {'pass' if row['passed'] else 'FAIL'}", flush=True)
                (args.out / "report.md").write_text(markdown(rows))
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
