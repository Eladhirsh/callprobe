import runpy
from pathlib import Path

RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "run_llm_bench.py"))


def test_errors_are_not_perfect_empty_results():
    row = {"expected": [{"verdict": "phantom", "tool": "send_email"}], "passed": False, "error": "ValueError"}
    summary = RUNNER["summarize"]([row])
    assert summary["exact"] == 0
    assert summary["errors"] == 1
    assert summary["fn"] == 1
    assert summary["recall"] == 0
    assert summary["precision"] is None


def test_honest_false_alarm_and_unchecked_are_visible():
    row = {
        "expected": [{"verdict": "backed", "tool": "send_email"}],
        "passed": False,
        "got": [{"verdict": "phantom", "tool": "send_email"}],
        "findings": [{"unchecked": ["to"]}],
    }
    summary = RUNNER["summarize"]([row])
    assert summary["honest_false_alarms"] == 1
    assert summary["honest_cases"] == 1
    assert summary["unchecked_findings"] == 1


def test_balanced_challenge_cases_pass_labeled_and_match_source():
    import json

    from didyoureally import bench

    root = Path(__file__).resolve().parents[1]
    source = runpy.run_path(str(root / "scripts" / "build_reliability_challenge.py"))
    cases = list(source["cases"]())
    assert len(cases) == 24
    for group in ("email", "support", "files", "scheduling"):
        selected = [c for c in cases if c["domain"] == group]
        assert len(selected) == 6
        assert sum(all(e["verdict"] == "backed" for e in c["expected"]) for c in selected) == 3
    for case in cases:
        assert bench.run_case(case, None).passed
        assert json.loads((source["OUT"] / f"{case['id']}.json").read_text()) == case


def test_fresh_validation_cases_are_balanced_and_pass_labeled():
    import json

    from didyoureally import bench

    root = Path(__file__).resolve().parents[1]
    source = runpy.run_path(str(root / "scripts" / "build_model_validation.py"))
    cases = list(source["cases"]())
    assert len(cases) == 24
    for group in ("email", "support", "files", "scheduling"):
        selected = [c for c in cases if c["domain"] == group]
        assert len(selected) == 6
        assert sum(all(e["verdict"] == "backed" for e in c["expected"]) for c in selected) == 3
    for case in cases:
        assert bench.run_case(case, None).passed
        assert json.loads((source["OUT"] / f"{case['id']}.json").read_text()) == case


def test_detail_free_metric_rejects_invented_arguments_and_missing_claims():
    expected = [{"tool": "issue_refund", "message_index": 2, "args": {}}]
    compare = RUNNER["detail_free_agreement"]
    assert compare(expected, expected) is True
    assert compare(expected, []) is False
    assert compare(expected, [{**expected[0], "args": {"amount": 65}}]) is False
    assert compare(expected, [{**expected[0], "message_index": 3}]) is False
    assert compare([{**expected[0], "args": {"amount": 65}}], []) is None


def test_detail_free_metric_counts_only_eligible_cases():
    summary = RUNNER["summarize"](
        [
            {"expected": [], "passed": True, "detail_free_claims_exact": True},
            {"expected": [], "passed": False, "detail_free_claims_exact": False},
            {"expected": [], "passed": True, "detail_free_claims_exact": None},
        ]
    )
    assert summary["detail_free_cases"] == 2
    assert summary["detail_free_exact"] == 1


def test_reverse_direction_alarms_and_incomplete_controls_are_visible():
    rows = [
        {
            "expected": [{"verdict": "backed", "tool": "send"}],
            "passed": False,
            "got": [{"verdict": "unmentioned", "tool": "send"}, {"verdict": "phantom", "tool": "send"}],
        },
        {"expected": [], "passed": False, "error": "incomplete"},
        {
            "expected": [{"verdict": "unmentioned", "tool": "charge"}],
            "passed": True,
            "got": [{"verdict": "unmentioned", "tool": "charge"}],
        },
        {"expected": [{"verdict": "unmentioned", "tool": "delete"}], "passed": False, "got": []},
    ]
    summary = RUNNER["summarize"](rows)
    assert summary["honest_cases"] == 2
    assert summary["honest_false_alarms"] == 1
    assert summary["honest_unmentioned_alarms"] == 1
    assert summary["honest_any_alarms"] == 1
    assert summary["honest_errors"] == 1
    assert summary["unmentioned_tp"] == summary["unmentioned_fp"] == summary["unmentioned_fn"] == 1


def test_report_includes_new_domains_and_reverse_metrics():
    row = {"model": "local", "domain": "deployment", "expected": [], "passed": True}
    output = RUNNER["markdown"]([row])
    assert "| local | deployment |" in output
    assert "Unmentioned alarms" in output
    assert "Incomplete honest checks" in output


def test_interrupted_run_preserves_partial_evidence_and_planned_count(tmp_path, monkeypatch):
    import json

    main = RUNNER["main"]
    calls = []

    def evaluate(case, base_url, model, **kwargs):
        calls.append(case)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return {"case": case["id"], "model": model, "domain": "deployment", "expected": [], "passed": True}

    monkeypatch.setitem(main.__globals__, "evaluate", evaluate)
    cases = tmp_path / "cases"
    cases.mkdir()
    for index in range(2):
        (cases / f"{index}.json").write_text(json.dumps({"id": str(index)}))
    out = tmp_path / "evidence"
    assert main(["--endpoint", "http://unused", "fake", "--cases", str(cases), "--out", str(out)]) == 130
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["status"] == "interrupted"
    assert metadata["planned_records"] == 2
    assert metadata["completed_records"] == 1
    assert len((out / "records.jsonl").read_text().splitlines()) == 1
    assert "interrupted. Completed 1/2 records" in (out / "report.md").read_text()
