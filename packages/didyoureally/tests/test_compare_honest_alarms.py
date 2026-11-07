"""Optional honest-control gating separates new alarms from extraction errors."""

import copy
import json
import runpy
from collections import Counter
from pathlib import Path

import pytest

HELPERS = runpy.run_path(str(Path(__file__).with_name("test_compare_llm_runs.py")))
SCRIPT = HELPERS["SCRIPT"]
write_run, save = HELPERS["write_run"], HELPERS["save"]
ALARMS = ["phantom", "contradicted", "masked_failure", "unmentioned"]


def outcomes(verdicts):
    return [{"tool": "send", "verdict": verdict} for verdict in verdicts]


def set_case(row, *, expected=("backed",), got=("backed",), error=False):
    row["expected"] = outcomes(expected)
    row["got"] = outcomes(got)
    row.pop("error", None)
    if error:
        row["error"] = "PRIVATE_PROVIDER_ERROR"
    row["passed"] = not error and Counter(got) == Counter(expected)


def pair(tmp_path, *, expected=("backed",), before=(), after=("phantom",), baseline_error=False):
    a, b = tmp_path / "a", tmp_path / "b"
    for folder, got, error in [(a, before, baseline_error), (b, after, False)]:
        meta, rows = write_run(folder)
        set_case(rows[0], expected=expected, got=got, error=error)
        save(folder, meta, rows)
    return a, b


@pytest.mark.parametrize("verdict", ALARMS)
@pytest.mark.parametrize("expected", [(), ("backed", "backed")])
def test_error_to_honest_alarm_is_reported_and_optionally_gated(tmp_path, verdict, expected):
    a, b = pair(tmp_path, expected=expected, after=(verdict,), baseline_error=True)
    ordinary = SCRIPT["compare"](a, b)
    strict = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert ordinary["gate_passed"] and not ordinary["fail_on_new_honest_alarms"]
    assert not strict["gate_passed"] and strict["fail_on_new_honest_alarms"]
    assert (
        strict["new_honest_alarms"]
        == ordinary["new_honest_alarms"]
        == [
            {"model": "local", "case": "a", "repeat_index": 1, "baseline_extraction_error": True},
        ]
    )
    assert strict["candidate_errors"] == strict["regressions"] == []
    assert "baseline extraction errors are not clean observations" in strict["scope"]


def test_completed_mismatch_without_alarm_can_gain_an_alarm(tmp_path):
    a, b = pair(tmp_path, before=(), after=("unmentioned",))
    ordinary = SCRIPT["compare"](a, b)
    strict = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert ordinary["gate_passed"] and not strict["gate_passed"]
    assert strict["baseline_exact"] == strict["candidate_exact"] == 1
    assert strict["regressions"] == []
    assert strict["new_honest_alarms"] == [
        {"model": "local", "case": "a", "repeat_index": 1, "baseline_extraction_error": False},
    ]


def test_previously_correct_case_keeps_the_existing_regression_gate(tmp_path):
    a, b = pair(tmp_path, before=("backed",), after=("phantom",))
    for enabled in (False, True):
        report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=enabled)
        assert not report["gate_passed"]
        assert report["regressions"] == [{"model": "local", "case": "a", "repeat_index": 1}]
        assert report["new_honest_alarms"][0]["baseline_extraction_error"] is False


@pytest.mark.parametrize("baseline_error", [False, True])
@pytest.mark.parametrize("expected", [(), ("backed",)])
def test_clean_candidate_has_no_new_alarm(tmp_path, baseline_error, expected):
    a, b = pair(tmp_path, expected=expected, before=expected, after=expected, baseline_error=baseline_error)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert report["gate_passed"] and report["new_honest_alarms"] == []
    assert len(report["improvements"]) == int(baseline_error)


@pytest.mark.parametrize("after", [("phantom",), ("contradicted",), ("phantom", "phantom")])
def test_existing_alarm_is_not_a_newly_alarming_observation(tmp_path, after):
    a, b = pair(tmp_path, before=("phantom",), after=after)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert report["gate_passed"] and report["new_honest_alarms"] == []
    assert report["candidate_mismatches"] == 1


@pytest.mark.parametrize("expected_alarm", ALARMS)
def test_failure_labeled_controls_are_excluded(tmp_path, expected_alarm):
    a, b = pair(tmp_path, expected=("backed", expected_alarm), after=("phantom",), baseline_error=True)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert report["gate_passed"] and report["new_honest_alarms"] == []


@pytest.mark.parametrize("enabled", [False, True])
def test_candidate_error_fails_even_if_partial_findings_contain_an_alarm(tmp_path, enabled):
    a, b = pair(tmp_path, baseline_error=True)
    meta = json.loads((b / "metadata.json").read_text())
    rows = [json.loads(line) for line in (b / "records.jsonl").read_text().splitlines()]
    set_case(rows[0], got=("phantom",), error=True)
    save(b, meta, rows)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=enabled)
    assert not report["gate_passed"] and report["new_honest_alarms"] == []
    assert report["candidate_errors"] == [{"model": "local", "case": "a", "repeat_index": 1}]


def test_baseline_error_with_partial_alarms_remains_an_unknown_observation(tmp_path):
    a, b = pair(tmp_path, before=("phantom",), after=("phantom",), baseline_error=True)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert not report["gate_passed"]
    assert report["new_honest_alarms"][0]["baseline_extraction_error"] is True


def test_alarm_identity_is_per_model_case_repeat_and_not_per_finding(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for folder in (a, b):
        meta, templates = write_run(folder)
        meta.update(
            repeats=2,
            targets=[{"id": "one", "model": "local"}, {"id": "two", "model": "other"}],
            planned_records=8,
            completed_records=8,
        )
        rows = []
        for target in meta["targets"]:
            for repeat in (1, 2):
                for template in templates:
                    row = copy.deepcopy(template)
                    row.update(endpoint_id=target["id"], model=target["model"], repeat_index=repeat)
                    if row["case"] == "a":
                        selected = target["model"] == "other" and repeat == 2
                        set_case(
                            row,
                            expected=(),
                            got=("phantom", "phantom") if selected and folder == b else (),
                            error=selected and folder == a,
                        )
                    rows.append(row)
        save(folder, meta, list(reversed(rows)) if folder == b else rows)
    report = SCRIPT["compare"](a, b, fail_on_new_honest_alarms=True)
    assert not report["gate_passed"] and report["paired_attempts"] == 8
    assert report["new_honest_alarms"] == [
        {"model": "other", "case": "a", "repeat_index": 2, "baseline_extraction_error": True},
    ]


def test_cli_opt_in_changes_exit_code_without_exposing_record_payloads(tmp_path, capsys):
    a, b = pair(tmp_path, baseline_error=True)
    for folder in (a, b):
        meta = json.loads((folder / "metadata.json").read_text())
        rows = [json.loads(line) for line in (folder / "records.jsonl").read_text().splitlines()]
        rows[0]["labeled_claims"][0]["args"] = {"secret": "PRIVATE_LABEL_VALUE"}
        rows[0]["claims"] = [{"text": "PRIVATE_CLAIM_TEXT", "args": {"secret": "PRIVATE_ARGUMENT"}}]
        save(folder, meta, rows)
    assert SCRIPT["main"]([str(a), str(b)]) == 0
    ordinary = capsys.readouterr()
    assert SCRIPT["main"]([str(a), str(b), "--fail-on-new-honest-alarms"]) == 1
    strict = capsys.readouterr()
    before_report, after_report = json.loads(ordinary.out), json.loads(strict.out)
    assert before_report["gate_passed"] and not after_report["gate_passed"]
    assert before_report["new_honest_alarms"] == after_report["new_honest_alarms"]
    assert not before_report["fail_on_new_honest_alarms"] and after_report["fail_on_new_honest_alarms"]
    for output in (ordinary, strict):
        assert output.err == ""
        assert "PRIVATE" not in output.out and "private-reply-sentinel" not in output.out


def test_invalid_evidence_still_exits_two_with_the_optional_gate(tmp_path, capsys):
    a, b = pair(tmp_path)
    (b / "metadata.json").write_text('{"PRIVATE_BROKEN":')
    assert SCRIPT["main"]([str(a), str(b), "--fail-on-new-honest-alarms"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE" not in captured.err
