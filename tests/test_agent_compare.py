import copy
import json
from argparse import Namespace

import pytest
from callprobe.agent_compare import agent_compare_main, compare_agent_runs, load_agent_run
from callprobe.agent_pilot import pilot_suite
from callprobe.agent_session import load_agent_suite, suite_hash


def evidence(tmp_path, name="run"):
    raw = pilot_suite()
    raw["cases"] = [raw["cases"][7]]
    suite = load_agent_suite(raw)
    report = {
        "format_version": 1,
        "status": "complete",
        "execution": "declarative_mocks",
        "suite_hash": suite_hash(suite),
        "planned_cases": 1,
        "source_sha256": {"callprobe": {"runner.py": "a" * 64}, "didyoureally": {"matcher.py": "b" * 64}},
        "config": {
            "agent_model": "a",
            "agent_endpoint": "http://localhost:1/v1",
            "extractor_model": "x",
            "extractor_endpoint": "http://localhost:2/v1",
            "max_turns": 8,
            "max_tokens": 2048,
            "agent_timeout": 120,
            "extractor_timeout": 120,
            "extractor_json_mode": True,
            "temperature": 0,
            "agent_retries": 0,
        },
        "episodes": [
            {
                "case_id": "offer-only",
                "status": "complete",
                "agent_status": "complete",
                "decision_passed": True,
                "account_passed": True,
                "passed": True,
                "missing_decision_turns": [],
                "decisions": [{"success": True}],
                "audit": {"status": "complete", "findings": []},
            }
        ],
    }
    folder = tmp_path / name
    folder.mkdir()
    (folder / "suite.json").write_text(json.dumps(raw))
    return folder / "report.json", report


def save(path, report):
    path.write_text(json.dumps(report))
    return load_agent_run(str(path))


def test_separate_axes_capture_regression_even_when_another_improves(tmp_path):
    a_path, a = evidence(tmp_path, "a")
    b_path, b = evidence(tmp_path, "b")
    a_row, b_row = a["episodes"][0], b["episodes"][0]
    a_row.update(decision_passed=False, passed=False, decisions=[{"success": False}])
    b_row.update(account_passed=False, passed=False)
    b_row["audit"]["findings"] = [{"verdict": "phantom", "unchecked": []}]
    result = compare_agent_runs(save(a_path, a), save(b_path, b))
    assert result["axes"]["decision_passed"]["improved"] == ["offer-only"]
    assert result["axes"]["account_passed"]["regressed"] == ["offer-only"]
    assert result["axes"]["passed"]["regressed"] == []
    assert not result["gate_passed"]
    args = Namespace(baseline=str(a_path), candidate=str(b_path), format="json", fail_on_regression=True)
    assert agent_compare_main(args) == 1


def test_incomplete_audit_is_excluded_and_blocks_gate(tmp_path):
    a_path, a = evidence(tmp_path, "a")
    b_path, b = evidence(tmp_path, "b")
    b["episodes"][0].update(
        status="incomplete", account_passed=None, passed=False, audit={"status": "incomplete", "findings": []}
    )
    result = compare_agent_runs(save(a_path, a), save(b_path, b))
    assert result["paired_complete_cases"] == 0
    assert result["incomplete_cases"] == ["offer-only"]
    assert not result["gate_passed"]
    args = Namespace(baseline=str(a_path), candidate=str(b_path), format="markdown", fail_on_regression=True)
    assert agent_compare_main(args) == 3
    args.fail_on_regression = False
    assert agent_compare_main(args) == 0


@pytest.mark.parametrize(
    "corruption",
    [
        "partial",
        "duplicate",
        "missing",
        "unknown",
        "suite_hash",
        "suite_edit",
        "flags",
        "bool_string",
        "source_hash",
        "config",
        "missing_turns",
        "empty_decisions",
        "invalid_findings",
    ],
)
def test_invalid_evidence_rejected_before_comparison(tmp_path, corruption):
    path, report = evidence(tmp_path)
    row = report["episodes"][0]
    if corruption == "partial":
        report["status"] = "running"
    elif corruption == "duplicate":
        report["episodes"].append(copy.deepcopy(row))
    elif corruption == "missing":
        report["episodes"] = []
    elif corruption == "unknown":
        row["case_id"] = "missing"
    elif corruption == "suite_hash":
        report["suite_hash"] = "different"
    elif corruption == "suite_edit":
        raw = json.loads((path.parent / "suite.json").read_text())
        raw["cases"][0]["prompt"] = "changed"
        (path.parent / "suite.json").write_text(json.dumps(raw))
    elif corruption == "flags":
        row["passed"] = False
    elif corruption == "bool_string":
        row["decision_passed"] = "false"
    elif corruption == "source_hash":
        report["source_sha256"]["callprobe"] = {}
    elif corruption == "config":
        report["config"].pop("extractor_model")
    elif corruption == "missing_turns":
        row["missing_decision_turns"] = [0]
    elif corruption == "empty_decisions":
        row["decisions"] = []
    else:
        row["audit"]["findings"] = [{"verdict": "good"}]
    with pytest.raises(ValueError):
        save(path, report)


@pytest.mark.parametrize("change", ["source", "extractor", "settings", "suite"])
def test_incompatible_runs_cannot_produce_a_gate(tmp_path, change):
    path, left = evidence(tmp_path)
    left = save(path, left)
    right = copy.deepcopy(left)
    if change == "source":
        right["source_sha256"]["callprobe"]["runner.py"] = "c" * 64
    elif change == "extractor":
        right["config"]["extractor_model"] = "different"
    elif change == "settings":
        right["config"]["max_tokens"] = 4096
    else:
        right["suite_hash"] = "different"
    with pytest.raises(ValueError):
        compare_agent_runs(left, right)


def test_model_change_and_identical_passes_are_compatible(tmp_path):
    path, left = evidence(tmp_path)
    left = save(path, left)
    right = copy.deepcopy(left)
    right["config"]["agent_model"] = "b"
    right["config"]["agent_endpoint"] = "http://localhost:3/v1"
    assert compare_agent_runs(left, right)["gate_passed"]
