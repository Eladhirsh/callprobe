import json
import runpy
from pathlib import Path

import pytest

RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "run_llm_bench.py"))


def record(index=1, *, passed=True, claim_to="Dana", case="a"):
    return {
        "case": case,
        "model": "local",
        "domain": "email",
        "repeat_index": index,
        "expected": [{"tool": "send_email", "verdict": "backed"}],
        "got": [{"tool": "send_email", "verdict": "backed" if passed else "phantom"}],
        "claims": [{"text": "Sent.", "tool": "send_email", "args": {"to": claim_to}, "message_index": 1}],
        "passed": passed,
    }


def test_complete_stable_repeats_count_one_unique_case():
    summary = RUNNER["repeat_summary"]([record(1), record(2)], ["a"], 2)
    assert summary["unique_cases"] == summary["all_exact_cases"] == summary["complete_cases"] == 1
    assert summary["planned_attempts"] == summary["observed_attempts"] == 2
    assert (
        summary["missing_attempts"] == summary["changed_outcome_cases"] == summary["changed_claim_cases"] == 0
    )


def test_same_verdicts_can_hide_changed_claim_arguments():
    summary = RUNNER["repeat_summary"]([record(1), record(2, claim_to="Lee")], ["a"], 2)
    assert summary["all_exact_cases"] == 1
    assert summary["changed_claim_cases"] == 1
    assert summary["changed_outcome_cases"] == summary["mixed_exactness_cases"] == 0


def test_claim_comparison_ignores_order_but_preserves_multiplicity():
    first, second = record(1), record(2)
    first["claims"].append({"tool": "archive_file", "args": {}})
    second["claims"] = first["claims"][::-1]
    assert RUNNER["repeat_summary"]([first, second], ["a"], 2)["changed_claim_cases"] == 0
    second["claims"] = first["claims"] * 2
    assert RUNNER["repeat_summary"]([first, second], ["a"], 2)["changed_claim_cases"] == 1


def test_consistently_wrong_is_not_all_exact():
    summary = RUNNER["repeat_summary"]([record(1, passed=False), record(2, passed=False)], ["a"], 2)
    assert summary["complete_cases"] == 1
    assert (
        summary["all_exact_cases"]
        == summary["mixed_exactness_cases"]
        == summary["changed_outcome_cases"]
        == 0
    )


def test_error_and_missing_cases_cannot_be_hidden_by_successful_attempts():
    error = {**record(2, passed=False), "error": "ExtractionError", "error_reason": "provider_error"}
    error.pop("claims")
    summary = RUNNER["repeat_summary"]([record(1), error], ["a", "never-started"], 3)
    assert summary["planned_attempts"] == 6 and summary["observed_attempts"] == 2
    assert summary["missing_attempts"] == 4
    assert summary["all_exact_cases"] == summary["complete_cases"] == 0
    assert summary["mixed_exactness_cases"] == summary["changed_outcome_cases"] == 1
    assert summary["cases"][1]["missing_attempts"] == 3
    assert summary["cases"][0]["error_attempts"] == 1


@pytest.mark.parametrize("index", [0, 3, True, "1"])
def test_invalid_repeat_indices_are_not_counted(index):
    with pytest.raises(ValueError, match="unexpected case or repeat index"):
        RUNNER["repeat_summary"]([record(index)], ["a"], 2)


def test_duplicate_and_unknown_records_do_not_inflate_coverage():
    with pytest.raises(ValueError, match="Duplicate case and repeat"):
        RUNNER["repeat_summary"]([record(), record()], ["a"], 2)
    with pytest.raises(ValueError, match="unexpected case"):
        RUNNER["repeat_summary"]([record(case="other")], ["a"], 2)
    with pytest.raises(ValueError, match="Duplicate planned case"):
        RUNNER["repeat_summary"]([], ["a", "a"], 2)


def test_unstarted_target_report_shows_missing_coverage():
    report = RUNNER["markdown"](
        [], case_ids=["a"], repeats=3, targets=[{"id": "endpoint-1", "model": "local"}]
    )
    assert "| local [endpoint-1] | 0/1 | 0 | 0 | 0 | 0 | 3 |" in report
    assert "not independent new cases" in report


@pytest.mark.parametrize("value", ["0", "-1", "101", "1.5"])
def test_invalid_repeats_fail_before_creating_output_or_calling_models(tmp_path, monkeypatch, value):
    main = RUNNER["main"]
    monkeypatch.setitem(main.__globals__, "evaluate", lambda *args, **kwargs: pytest.fail("No model calls"))
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        main(["--endpoint", "http://unused", "local", "--out", str(out), "--repeats", value])
    assert exc.value.code == 2 and not out.exists()


def test_duplicate_endpoint_pair_requires_explicit_repeats(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        RUNNER["main"](
            [
                "--endpoint",
                "http://unused",
                "local",
                "--endpoint",
                "http://unused",
                "local",
                "--out",
                str(out),
            ]
        )
    assert exc.value.code == 2 and not out.exists()


def cases_folder(tmp_path, count=1):
    folder = tmp_path / "cases"
    folder.mkdir()
    for index in range(count):
        (folder / f"{index}.json").write_text(
            json.dumps({"id": str(index), "trace": {"events": []}, "claims": [], "expected": []})
        )
    return folder


def test_repeated_same_named_targets_keep_separate_reports(tmp_path, monkeypatch):
    main = RUNNER["main"]
    calls = []

    def evaluate(case, base_url, model, **kwargs):
        calls.append((case["id"], base_url))
        return {**record(case=case["id"], passed=base_url == "https://one.invalid"), "model": model}

    monkeypatch.setitem(main.__globals__, "evaluate", evaluate)
    out = tmp_path / "out"
    assert (
        main(
            [
                "--endpoint",
                "https://one.invalid",
                "same",
                "--endpoint",
                "https://two.invalid",
                "same",
                "--cases",
                str(cases_folder(tmp_path)),
                "--out",
                str(out),
                "--repeats",
                "2",
            ]
        )
        == 1
    )
    assert len(calls) == 4
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["planned_records"] == metadata["completed_records"] == 4
    assert metadata["repeats"] == 2
    records = [json.loads(line) for line in (out / "records.jsonl").read_text().splitlines()]
    assert [(r["endpoint_id"], r["repeat_index"]) for r in records] == [
        ("endpoint-1", 1),
        ("endpoint-1", 2),
        ("endpoint-2", 1),
        ("endpoint-2", 2),
    ]
    summaries = json.loads((out / "repeat_summary.json").read_text())
    assert [s["all_exact_cases"] for s in summaries] == [1, 0]
    assert [s["unique_cases"] for s in summaries] == [1, 1]
    report = (out / "report.md").read_text()
    assert "same [endpoint-1]" in report and "same [endpoint-2]" in report
    assert all("https://" not in p.read_text() for p in out.iterdir())


def test_interruption_keeps_missing_repeat_slots_and_never_marks_case_all_exact(tmp_path, monkeypatch):
    main = RUNNER["main"]
    calls = []

    def evaluate(case, base_url, model, **kwargs):
        calls.append(case["id"])
        if len(calls) == 4:
            raise KeyboardInterrupt
        return record(case=case["id"])

    monkeypatch.setitem(main.__globals__, "evaluate", evaluate)
    out = tmp_path / "out"
    assert (
        main(
            [
                "--endpoint",
                "http://unused",
                "local",
                "--cases",
                str(cases_folder(tmp_path, 2)),
                "--out",
                str(out),
                "--repeats",
                "3",
            ]
        )
        == 130
    )
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["status"] == "interrupted" and metadata["planned_records"] == 6
    assert metadata["completed_records"] == 3
    [summary] = json.loads((out / "repeat_summary.json").read_text())
    assert summary["missing_attempts"] == 3
    assert summary["complete_cases"] == summary["all_exact_cases"] == 0


def test_default_is_one_attempt_and_one_repeat_slot(tmp_path, monkeypatch):
    main = RUNNER["main"]
    monkeypatch.setitem(main.__globals__, "evaluate", lambda case, *args, **kwargs: record(case=case["id"]))
    out = tmp_path / "out"
    assert (
        main(
            [
                "--endpoint",
                "http://unused",
                "local",
                "--cases",
                str(cases_folder(tmp_path)),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["repeats"] == metadata["completed_records"] == metadata["planned_records"] == 1


@pytest.mark.parametrize("scope", [False, True])
def test_fresh_repeat_cases_are_paired_and_match_the_frozen_generator(scope):
    from didyoureally import bench

    source = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "build_repeat_validation.py")
    )
    cases = list(source["cases"](source["SCOPE_SPECS"], "scope") if scope else source["cases"]())
    out = source["OUT"].with_name("mixed-scope-validation") if scope else source["OUT"]
    assert len(cases) == 8
    for domain in ("email", "files", "support", "scheduling"):
        selected = [c for c in cases if c["domain"] == domain]
        assert len(selected) == 2
        assert sum(all(e["verdict"] == "backed" for e in c["expected"]) for c in selected) == 1
    assert {e["verdict"] for c in cases for e in c["expected"]} == {
        "backed",
        "phantom",
        "masked_failure",
        "contradicted",
        "unmentioned",
    }
    for case in cases:
        assert bench.run_case(case, None).passed
        assert json.loads((out / f"{case['id']}.json").read_text()) == case
