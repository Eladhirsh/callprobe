"""Offline regression replay of saved extractor replies, never a fresh model score."""

import argparse
import json
import re
from pathlib import Path

from run_llm_bench import evaluate, request_digest

from didyoureally.extract import SOURCE_REPAIR_PROMPT
from didyoureally.strict_json import loads


class NeedsRecovery(RuntimeError):
    pass


class MissingReply(RuntimeError):
    pass


class RequestMismatch(RuntimeError):
    pass


class ReplayInputError(ValueError):
    """Fixed diagnostics that do not include source contents."""


def validate_saved(saved):
    if not isinstance(saved, dict):
        raise ReplayInputError("Saved records must be objects")
    mode = saved.get("extraction_mode", "default")
    if mode not in ("default", "staged"):
        raise ReplayInputError("Unknown saved extraction mode")
    if "error" in saved:
        raise ReplayInputError("Incomplete baseline extraction cannot pass replay")
    replies, metadata = saved.get("raw_responses"), saved.get("responses")
    if not isinstance(replies, list) or not isinstance(metadata, list) or len(replies) != len(metadata):
        raise ReplayInputError("Saved replies and response metadata must be equal-length arrays")
    if not all(isinstance(reply, str) for reply in replies) or not all(
        isinstance(item, dict) for item in metadata
    ):
        raise ReplayInputError("Invalid saved reply or response metadata")
    if type(saved.get("json_mode", False)) is not bool:
        raise ReplayInputError("Saved JSON mode must be a boolean")
    hashes = [item.get("request_sha256") for item in metadata]
    if any("request_sha256" in item for item in metadata) and not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes
    ):
        raise ReplayInputError("Request hashes must be valid and present on every saved response")
    if mode == "staged" and (not hashes or any(value is None for value in hashes)):
        raise ReplayInputError("Staged replay requires request hashes on every saved response")
    if not isinstance(saved.get("model"), str) or not saved["model"].strip():
        raise ReplayInputError("Saved model must be a nonempty string")


def replay(case, saved):
    validate_saved(saved)
    replies = iter(zip(saved["raw_responses"], saved["responses"], strict=True))
    consumed = 0
    bound = bool(saved["responses"]) and "request_sha256" in saved["responses"][0]

    def transport(url, headers, body):
        nonlocal consumed
        # The baseline has no response to this new request. Never consume the
        # next assistant message's response in its place or fabricate a reply.
        if not bound and body["messages"][0]["content"] == SOURCE_REPAIR_PROMPT:
            raise NeedsRecovery
        try:
            content, metadata = next(replies)
        except StopIteration:
            raise MissingReply from None
        if bound and request_digest(body) != metadata["request_sha256"]:
            raise RequestMismatch
        consumed += 1
        return {
            "choices": [{"message": {"content": content}, "finish_reason": metadata.get("finish_reason")}]
        }

    result = {
        "case": case["id"],
        "model": saved["model"],
        "extraction_mode": saved.get("extraction_mode", "default"),
        "endpoint_id": saved.get("endpoint_id", "legacy"),
        "repeat_index": saved.get("repeat_index", 1),
        "request_identity": "incomplete" if bound else "legacy_unverified",
    }
    try:
        row = evaluate(
            case,
            "http://unused.invalid/v1",
            saved["model"],
            transport=transport,
            json_mode=saved.get("json_mode", False),
            extraction_mode=saved.get("extraction_mode", "default"),
        )
    except NeedsRecovery:
        result["outcome"] = "recovery_required"
    except MissingReply:
        result["outcome"] = "missing_saved_reply"
    except RequestMismatch:
        result["outcome"] = "request_mismatch"
        result["request_identity"] = "mismatch"
    else:
        same = "error" not in row and all(
            row.get(k) == saved.get(k) for k in ("got", "claims", "error_reason")
        )
        same = same and consumed == len(saved["raw_responses"])
        if bound and consumed == len(saved["raw_responses"]):
            result["request_identity"] = "verified"
        result["outcome"] = "unchanged" if same else "changed"
        if not same:
            result["current"] = row
    return result


def load_inputs(records_path, cases_path):
    cases = {}
    for path in sorted(cases_path.glob("*.json")):
        case = loads(path.read_text())
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip():
            raise ReplayInputError("Cases need nonempty string IDs")
        if case["id"] in cases:
            raise ReplayInputError("Duplicate case IDs")
        cases[case["id"]] = case
    saved = [loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    if not cases or not saved:
        raise ReplayInputError("Replay requires nonempty cases and saved records")
    seen = set()
    for record in saved:
        validate_saved(record)
        case_id = record.get("case")
        if not isinstance(case_id, str) or case_id not in cases:
            raise ReplayInputError("Saved record refers to an unknown case")
        endpoint, repeat = record.get("endpoint_id", "legacy"), record.get("repeat_index", 1)
        if not isinstance(endpoint, str) or not endpoint.strip() or type(repeat) is not int or repeat < 1:
            raise ReplayInputError("Invalid saved endpoint or repeat identity")
        key = (endpoint, record["model"], case_id, repeat)
        if key in seen:
            raise ReplayInputError("Duplicate saved record identity")
        seen.add(key)
        case = cases[case_id]
        if record.get("expected") != case.get("expected") or record.get("labeled_claims") != case.get(
            "claims"
        ):
            raise ReplayInputError("Saved labels differ from the supplied cases")
        if not all(
            isinstance(record.get(field), list) for field in ("expected", "labeled_claims", "got", "claims")
        ):
            raise ReplayInputError("Saved records require labels, claims, and verdict arrays")
    return cases, saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Output directory already exists; choose a new path")
    try:
        cases, saved = load_inputs(args.records, args.cases)
        rows = [replay(cases[record["case"]], record) for record in saved]
    except ReplayInputError as exc:
        parser.error(str(exc))
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        parser.error("Invalid replay input; check the saved JSON and case files")
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    lines = [
        "# Offline recorded-response regression",
        "",
        "These results reuse saved model replies. They are not fresh end-to-end accuracy.",
        f"Replayed {len(rows)} supplied records. This does not establish full planned-run coverage.",
        "",
        "| Model | Extraction mode | Unchanged | Changed | Needs live recovery | Missing saved reply | Request mismatch |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, mode in dict.fromkeys((r["model"], r["extraction_mode"]) for r in rows):
        selected = [r for r in rows if (r["model"], r["extraction_mode"]) == (model, mode)]
        counts = [
            sum(r["outcome"] == status for r in selected)
            for status in (
                "unchanged",
                "changed",
                "recovery_required",
                "missing_saved_reply",
                "request_mismatch",
            )
        ]
        lines.append(f"| {model} | {mode} | " + " | ".join(map(str, counts)) + " |")
    lines += [
        "",
        f"Baseline records: `{args.records}`. Cases: `{args.cases}`.",
        "No network calls are made. Hashed responses require matching request bodies, including recovery requests.",
        "Legacy responses have unverified request identity and stop at new recovery requests.",
    ]
    (args.out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return int(any(r["outcome"] != "unchanged" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
