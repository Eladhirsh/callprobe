"""Offline regression replay of saved extractor replies, never a fresh model score."""

import argparse
import json
from pathlib import Path

from run_llm_bench import evaluate

from didyoureally.extract import SOURCE_REPAIR_PROMPT


class NeedsRecovery(RuntimeError):
    pass


class MissingReply(RuntimeError):
    pass


def replay(case, saved):
    replies = iter(zip(saved["raw_responses"], saved["responses"], strict=True))
    consumed = 0

    def transport(url, headers, body):
        nonlocal consumed
        # The baseline has no response to this new request. Never consume the
        # next assistant message's response in its place or fabricate a reply.
        if body["messages"][0]["content"] == SOURCE_REPAIR_PROMPT:
            raise NeedsRecovery
        try:
            content, metadata = next(replies)
        except StopIteration:
            raise MissingReply from None
        consumed += 1
        return {
            "choices": [{"message": {"content": content}, "finish_reason": metadata.get("finish_reason")}]
        }

    result = {"case": case["id"], "model": saved["model"]}
    try:
        row = evaluate(case, "http://unused.invalid/v1", saved["model"], transport=transport)
    except NeedsRecovery:
        result["outcome"] = "recovery_required"
    except MissingReply:
        result["outcome"] = "missing_saved_reply"
    else:
        same = all(row.get(k) == saved.get(k) for k in ("got", "claims", "error_reason"))
        same = same and consumed == len(saved["raw_responses"])
        result["outcome"] = "unchanged" if same else "changed"
        if not same:
            result["current"] = row
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = {c["id"]: c for p in args.cases.glob("*.json") if (c := json.loads(p.read_text()))}
    saved = [json.loads(line) for line in args.records.read_text().splitlines()]
    rows = []
    for record in saved:
        case = cases[record["case"]]
        if record["expected"] != case["expected"] or record["labeled_claims"] != case["claims"]:
            parser.error("Saved labels differ from the supplied cases")
        rows.append(replay(case, record))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    lines = [
        "# Offline recorded-response regression",
        "",
        "These results reuse saved model replies. They are not fresh end-to-end accuracy.",
        "",
        "| Model | Unchanged | Changed | Needs live recovery | Missing saved reply |",
        "|---|---|---|---|---|",
    ]
    for model in dict.fromkeys(r["model"] for r in rows):
        selected = [r for r in rows if r["model"] == model]
        counts = [
            sum(r["outcome"] == status for r in selected)
            for status in ("unchanged", "changed", "recovery_required", "missing_saved_reply")
        ]
        lines.append(f"| {model} | " + " | ".join(map(str, counts)) + " |")
    lines += [
        "",
        f"Baseline records: `{args.records}`. Cases: `{args.cases}`.",
        "No network calls are made. A new recovery request stops replay and requires a live evaluation.",
    ]
    (args.out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return int(any(r["outcome"] != "unchanged" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
