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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Import the checkout after adding its source directory to the search path.

from didyoureally.adapters import load_trace  # noqa: E402
from didyoureally.bench import default_cases_dir  # noqa: E402
from didyoureally.extract import SYSTEM_PROMPT, ExtractionError, LLMExtractor, _http_post  # noqa: E402
from didyoureally.matcher import PROBLEM_VERDICTS, check  # noqa: E402
from didyoureally.staged import ACTION_PROMPT, DETAIL_PROMPT, StagedExtractor  # noqa: E402

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


def detail_free_agreement(expected, actual):
    """For labels with no argument details, extra model arguments are an error."""
    if any(c.get("args") for c in expected):
        return None
    if any(c.get("args") for c in actual):
        return False

    def signature(claims):
        return Counter((c.get("tool"), c.get("message_index")) for c in claims)

    return signature(expected) == signature(actual)


def summarize(rows):
    tp = fp = fn = 0
    for row in rows:
        expected = signatures([x for x in row["expected"] if x["verdict"] in PROBLEMS])
        got = signatures([x for x in row.get("got", []) if x["verdict"] in PROBLEMS])
        tp += sum((expected & got).values())
        fp += sum((got - expected).values())
        fn += sum((expected - got).values())
    honest = [r for r in rows if all(e["verdict"] == "backed" for e in r["expected"])]
    reverse_tp = reverse_fp = reverse_fn = 0
    for row in rows:
        expected = signatures([x for x in row["expected"] if x["verdict"] == "unmentioned"])
        got = signatures([x for x in row.get("got", []) if x["verdict"] == "unmentioned"])
        reverse_tp += sum((expected & got).values())
        reverse_fp += sum((got - expected).values())
        reverse_fn += sum((expected - got).values())
    return {
        "cases": len(rows),
        "detail_free_cases": sum(r.get("detail_free_claims_exact") is not None for r in rows),
        "detail_free_exact": sum(r.get("detail_free_claims_exact") is True for r in rows),
        "exact": sum(r["passed"] for r in rows),
        "errors": sum("error" in r for r in rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "honest_cases": len(honest),
        "honest_false_alarms": sum(any(x["verdict"] in PROBLEMS for x in r.get("got", [])) for r in honest),
        "honest_unmentioned_alarms": sum(
            any(x["verdict"] == "unmentioned" for x in r.get("got", [])) for r in honest
        ),
        "honest_any_alarms": sum(
            any(x["verdict"] in PROBLEMS | {"unmentioned"} for x in r.get("got", [])) for r in honest
        ),
        "honest_errors": sum("error" in r for r in honest),
        "unmentioned_tp": reverse_tp,
        "unmentioned_fp": reverse_fp,
        "unmentioned_fn": reverse_fn,
        "unchecked_findings": sum(bool(f["unchecked"]) for r in rows for f in r.get("findings", [])),
    }


def evaluate(case, base_url, model, *, json_mode=False, transport=None, extraction_mode="default"):
    raw = []
    responses = []

    def capture(url, headers, body):
        response = (transport or _http_post)(url, headers, body)
        raw.append(response["choices"][0]["message"]["content"])
        responses.append(
            {
                "model": response.get("model"),
                "usage": response.get("usage"),
                "finish_reason": response["choices"][0].get("finish_reason"),
            }
        )
        return response

    row = {
        "case": case["id"],
        "domain": domain(case),
        "model": model,
        "extraction_mode": extraction_mode,
        "expected": case["expected"],
        "labeled_claims": case["claims"],
        "passed": False,
        "detail_free_claims_exact": False if detail_free_agreement(case["claims"], []) is not None else None,
    }
    started = time.monotonic()
    try:
        trace = load_trace(case["trace"], case["id"])
        cls = StagedExtractor if extraction_mode == "staged" else LLMExtractor
        claims = cls(base_url=base_url, model=model, transport=capture, json_mode=json_mode).extract(trace)
        findings = check(trace, claims)
        row["claims"] = [asdict(c) for c in claims]
        row["detail_free_claims_exact"] = detail_free_agreement(case["claims"], row["claims"])
        row["findings"] = [f.to_dict() for f in findings]
        row["got"] = [
            {"verdict": f.verdict.value, "tool": f.claim.tool if f.claim else f.call.tool} for f in findings
        ]
        row["passed"] = signatures(row["got"]) == signatures(row["expected"])
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Provider error messages can contain secrets. Record only the exception type.
        row["error"] = type(exc).__name__
        if isinstance(exc, ExtractionError):
            row["error_reason"] = exc.reason
            row["error_message_index"] = exc.message_index
    row["raw_responses"] = raw
    row["responses"] = responses
    row["seconds"] = round(time.monotonic() - started, 3)
    return row


def markdown(rows):
    lines = [
        "# Real-model extraction on synthetic traces",
        "",
        "Development fixtures, not held-out accuracy. Verdicts remain deterministic.",
        "Extraction mode: " + ", ".join(sorted({r.get("extraction_mode", "default") for r in rows})) + ".",
        "",
        "| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for model in dict.fromkeys(r["model"] for r in rows):
        domains = sorted({r["domain"] for r in rows if r["model"] == model})
        for group in ["all", *domains]:
            selected = [r for r in rows if r["model"] == model and (group == "all" or r["domain"] == group)]
            if not selected:
                continue
            s = summarize(selected)
            precision = "n/a" if s["precision"] is None else f"{s['precision']:.1%}"
            recall = "n/a" if s["recall"] is None else f"{s['recall']:.1%}"
            lines.append(
                f"| {model} | {group} | {s['exact']}/{s['cases']} | {precision} | {recall} | "
                f"{s['errors']} | {s['honest_false_alarms']}/{s['honest_cases']} | "
                f"{s['unchecked_findings']} | {s['detail_free_exact']}/{s['detail_free_cases']} |"
            )
    lines += [
        "",
        "| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |",
        "|---|---|---|---|---|---|",
    ]
    for model in dict.fromkeys(r["model"] for r in rows):
        s = summarize([r for r in rows if r["model"] == model])
        lines.append(
            f"| {model} | {s['honest_cases']} | {s['honest_false_alarms']} | "
            f"{s['honest_unmentioned_alarms']} | {s['honest_any_alarms']} | {s['honest_errors']} |"
        )
    lines += [
        "",
        "| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |",
        "|---|---|---|---|",
    ]
    for model in dict.fromkeys(r["model"] for r in rows):
        s = summarize([r for r in rows if r["model"] == model])
        lines.append(f"| {model} | {s['unmentioned_tp']} | {s['unmentioned_fp']} | {s['unmentioned_fn']} |")
    lines += [
        "",
        "Exact compares verdict and tool counts, not claim wording or call identity.",
        "Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems",
        "in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.",
        "The separate honest-control table includes unmentioned alarms and incomplete checks.",
        "Any alarm counts a case once even when it has both claim and unmentioned alarms.",
        "Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.",
        "Unchecked counts findings with details that could not be compared.",
        "Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-mode", choices=["default", "staged"], default="default")
    parser.add_argument("--endpoint", nargs=2, action="append", required=True, metavar=("BASE_URL", "MODEL"))
    parser.add_argument(
        "--json-mode", action="store_true", help="Request JSON mode from a compatible endpoint"
    )
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
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "planned_records": len(cases) * len(args.endpoint),
        "completed_records": 0,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src/didyoureally").glob("*.py"))
        },
        "json_mode": args.json_mode,
        "extraction_mode": args.extraction_mode,
        "prompt_sha256": hashlib.sha256(
            (ACTION_PROMPT if args.extraction_mode == "staged" else SYSTEM_PROMPT).encode()
        ).hexdigest(),
        "detail_prompt_sha256": (
            hashlib.sha256(DETAIL_PROMPT.encode()).hexdigest() if args.extraction_mode == "staged" else None
        ),
        "cases_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "models": [model for _, model in args.endpoint],
        "temperature": 0,
        "label": "Synthetic development transcripts, real extraction models",
    }
    rows = []

    def save_progress():
        metadata["completed_records"] = len(rows)
        (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        status = f"Run status: {metadata['status']}. Completed {len(rows)}/{metadata['planned_records']} records.\n\n"
        (args.out / "report.md").write_text(status + markdown(rows))

    save_progress()
    try:
        with (args.out / "records.jsonl").open("w") as stream:
            for base_url, model in args.endpoint:
                for case in cases:
                    row = evaluate(
                        case, base_url, model, json_mode=args.json_mode, extraction_mode=args.extraction_mode
                    )
                    rows.append(row)
                    stream.write(json.dumps(row) + "\n")
                    stream.flush()
                    print(f"{model} {case['id']}: {'pass' if row['passed'] else 'FAIL'}", flush=True)
                    save_progress()
    except KeyboardInterrupt:
        metadata["status"] = "interrupted"
        return 130
    except Exception:
        metadata["status"] = "failed"
        raise
    else:
        metadata["status"] = "complete"
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_progress()
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
