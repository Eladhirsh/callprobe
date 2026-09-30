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
