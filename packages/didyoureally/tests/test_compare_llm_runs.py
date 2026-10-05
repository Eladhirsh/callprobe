import copy
import json
import runpy
from pathlib import Path

import pytest

SCRIPT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "compare_llm_runs.py"))


def write_run(folder, *, passed=(True, True), error=False, reverse=False):
    folder.mkdir()
    meta = {
        "status": "complete",
        "case_ids": ["a", "b"],
        "targets": [{"id": "endpoint-2" if reverse else "endpoint-1", "model": "local"}],
        "repeats": 1,
        "planned_records": 2,
        "completed_records": 2,
        "cases_sha256": "a" * 64,
        "runner_sha256": "b" * 64,
        "json_mode": True,
        "temperature": 0,
        "extraction_mode": "default",
    }
    rows = []
    for case, exact in zip(meta["case_ids"], passed, strict=True):
        row = {
            "case": case,
            "model": "local",
            "endpoint_id": meta["targets"][0]["id"],
            "repeat_index": 1,
            "extraction_mode": "default",
            "passed": exact,
            "expected": [{"tool": "send", "verdict": "backed"}],
            "got": [{"tool": "send", "verdict": "backed" if exact else "phantom"}],
            "claims": [],
            "labeled_claims": [{"tool": "send", "args": {}, "message_index": 1}],
            "raw_responses": ["private-reply-sentinel"],
        }
        if error and case == "a":
            row.update(error="PrivateProviderError", passed=False)
            row.pop("got")
        rows.append(row)
    if reverse:
        rows.reverse()
    save(folder, meta, rows)
    return meta, rows


def save(folder, meta, rows):
    (folder / "metadata.json").write_text(json.dumps(meta))
    (folder / "records.jsonl").write_text("\n".join(json.dumps(row) for row in rows))


def test_improvement_does_not_cancel_individual_regression(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a, passed=(True, False))
    write_run(b, passed=(False, True), reverse=True)
    report = SCRIPT["compare"](a, b)
    assert report["baseline_exact"] == report["candidate_exact"] == 1
    assert not report["gate_passed"]
    assert report["regressions"] == [{"model": "local", "case": "a", "repeat_index": 1}]
    assert report["improvements"] == [{"model": "local", "case": "b", "repeat_index": 1}]
    assert "private-reply-sentinel" not in json.dumps(report)


def test_unchanged_mismatches_are_explicit_but_not_regressions(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a, passed=(False, False))
    write_run(b, passed=(True, False))
    report = SCRIPT["compare"](a, b)
    assert report["gate_passed"] and report["candidate_mismatches"] == 1
    assert report["paired_attempts"] == 2


def test_existing_extraction_error_cannot_pass(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a, error=True)
    write_run(b, error=True)
    report = SCRIPT["compare"](a, b)
    assert not report["gate_passed"]
    assert not report["regressions"] and len(report["candidate_errors"]) == 1
    assert "PrivateProviderError" not in json.dumps(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "running"),
        ("status", "interrupted"),
        ("case_ids", []),
        ("case_ids", ["a", "a"]),
        ("repeats", True),
        ("repeats", 0),
        ("completed_records", 1),
        ("planned_records", True),
        ("targets", []),
        ("targets", [{"id": "e1", "model": "local"}, {"id": "e2", "model": "local"}]),
        ("targets", [{"id": "e1", "model": "m1"}, {"id": "e1", "model": "m2"}]),
        ("cases_sha256", "missing"),
        ("json_mode", 1),
        ("temperature", True),
        ("extraction_mode", "unknown"),
    ],
)
def test_rejects_incomplete_or_invalid_metadata(tmp_path, field, value):
    meta, rows = write_run(tmp_path / "run")
    meta[field] = value
    save(tmp_path / "run", meta, rows)
    with pytest.raises(ValueError):
        SCRIPT["read_run"](tmp_path / "run")


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "duplicate",
        "unknown_case",
        "wrong_target",
        "wrong_model",
        "bool_repeat",
        "wrong_mode",
        "forged_pass",
        "bad_verdict",
        "bad_expected",
        "missing_got",
        "missing_labels",
        "nonboolean_pass",
    ],
)
def test_rejects_invalid_or_uncovered_slots(tmp_path, change):
    folder = tmp_path / "run"
    meta, rows = write_run(folder)
    if change == "missing":
        rows.pop()
    elif change == "extra":
        rows.append(copy.deepcopy(rows[0]))
    elif change == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    else:
        changes = {
            "unknown_case": ("case", "c"),
            "wrong_target": ("endpoint_id", "unknown"),
            "wrong_model": ("model", "other"),
            "bool_repeat": ("repeat_index", True),
            "wrong_mode": ("extraction_mode", "staged"),
            "forged_pass": ("passed", False),
            "bad_verdict": ("got", [{"tool": "send", "verdict": "unknown"}]),
            "bad_expected": ("expected", {}),
            "missing_got": ("got", None),
            "missing_labels": ("labeled_claims", None),
            "nonboolean_pass": ("passed", 1),
        }
        field, value = changes[change]
        rows[0][field] = value
    save(folder, meta, rows)
    with pytest.raises(ValueError):
        SCRIPT["read_run"](folder)


@pytest.mark.parametrize(
    "field,value",
    [("cases_sha256", "c" * 64), ("runner_sha256", "c" * 64), ("json_mode", False), ("temperature", 1)],
)
def test_rejects_incompatible_runs(tmp_path, field, value):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    meta, rows = write_run(b)
    meta[field] = value
    save(b, meta, rows)
    with pytest.raises(ValueError):
        SCRIPT["compare"](a, b)


def test_cannot_change_labels_while_retaining_suite_hash(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    meta, rows = write_run(b)
    rows[0]["labeled_claims"][0]["args"] = {"to": "other"}
    save(b, meta, rows)
    with pytest.raises(ValueError, match="labels differ"):
        SCRIPT["compare"](a, b)


@pytest.mark.parametrize(
    "payload", ['{"secret":1,"secret":2}', '{"secret":NaN}', '{"secret":1e999}', "{bad-private-payload", "[]"]
)
def test_invalid_json_has_safe_cli_error(tmp_path, capsys, payload):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    write_run(b)
    (b / "metadata.json").write_text(payload)
    assert SCRIPT["main"]([str(a), str(b)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Cannot compare:" in captured.err
    assert "secret" not in captured.err and "private" not in captured.err


@pytest.mark.parametrize("passed,code", [((True, True), 0), ((False, True), 1)])
def test_cli_emits_sanitized_json_and_gate_exit(tmp_path, capsys, passed, code):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    write_run(b, passed=passed)
    assert SCRIPT["main"]([str(a), str(b)]) == code
    report = json.loads(capsys.readouterr().out)
    assert report["gate_passed"] is (code == 0)


def test_missing_successful_claims_cannot_pass(tmp_path):
    folder = tmp_path / "run"
    meta, rows = write_run(folder)
    rows[0].pop("claims")
    save(folder, meta, rows)
    with pytest.raises(ValueError, match="Missing successful extraction claims"):
        SCRIPT["read_run"](folder)


def test_changed_model_coverage_is_rejected(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    meta, rows = write_run(b)
    meta["targets"][0]["model"] = "different"
    for row in rows:
        row["model"] = "different"
    save(b, meta, rows)
    with pytest.raises(ValueError, match="coverage differs"):
        SCRIPT["compare"](a, b)


def test_extraction_modes_can_be_compared_explicitly(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    meta, rows = write_run(b)
    meta["extraction_mode"] = "staged"
    for row in rows:
        row["extraction_mode"] = "staged"
    save(b, meta, rows)
    report = SCRIPT["compare"](a, b)
    assert report["gate_passed"]
    assert report["baseline_extraction_mode"] == "default"
    assert report["candidate_extraction_mode"] == "staged"


def test_cli_explains_incomplete_coverage_without_source_text(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a)
    meta, rows = write_run(b)
    rows.pop()
    save(b, meta, rows)
    assert SCRIPT["main"]([str(a), str(b)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Cannot compare: Missing or extra records.\n"
