import copy
import json
from argparse import Namespace

import pytest

pytest.importorskip("didyoureally")
import didyoureally
from didyoureally import Claim
from didyoureally.extract import ExtractionError

import callprobe
from callprobe.agent_cli import _source_hashes
from callprobe.agent_compare import (
    agent_compare_main,
    compare_agent_runs,
    load_agent_run,
)
from callprobe.agent_pilot import pilot_suite
from callprobe.agent_session import load_agent_suite, run_episode, suite_hash
from callprobe.client import Completion
from callprobe.models import Call


class ScriptedClient:
    def __init__(self, replies):
        self.replies = iter(replies)

    def complete(self, *args, **kwargs):
        return next(self.replies)


class Labels:
    def __init__(self, claims=(), *, incomplete=False):
        self.claims = list(claims)
        self.incomplete = incomplete

    def extract(self, trace):
        if self.incomplete:
            raise ExtractionError(2, "source_mismatch")
        return self.claims


def episode(*, decision_failure=False, account_failure=False, incomplete=False):
    suite = load_agent_suite(pilot_suite())
    case = next(c for c in suite.cases if c.id == "offer-only")
    text = "I sent the receipt." if account_failure else "I can help later."
    replies = [Completion(content=text, finish_reason="stop")]
    if decision_failure:
        replies.insert(0, Completion(calls=[Call(name="unknown")], finish_reason="tool_calls"))
    labels = [Claim(text, "send_email", message_index=2)] if account_failure else []
    row = run_episode(case, ScriptedClient(replies), Labels(labels, incomplete=incomplete), model="a")
    row["extraction_requests"] = []
    return row


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
        "source_sha256": {
            "callprobe": _source_hashes(callprobe),
            "didyoureally": _source_hashes(didyoureally),
        },
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
        "episodes": [episode()],
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
    a["episodes"] = [episode(decision_failure=True)]
    b["episodes"] = [episode(account_failure=True)]
    result = compare_agent_runs(save(a_path, a), save(b_path, b))
    assert result["axes"]["decision_passed"]["improved"] == ["offer-only"]
    assert result["axes"]["account_passed"]["regressed"] == ["offer-only"]
    assert result["axes"]["passed"]["regressed"] == []
    assert not result["gate_passed"]
    args = Namespace(
        baseline=str(a_path),
        candidate=str(b_path),
        format="json",
        fail_on_regression=True,
    )
    assert agent_compare_main(args) == 1


def test_incomplete_audit_is_excluded_and_blocks_gate(tmp_path):
    a_path, a = evidence(tmp_path, "a")
    b_path, b = evidence(tmp_path, "b")
    b["episodes"] = [episode(incomplete=True)]
    result = compare_agent_runs(save(a_path, a), save(b_path, b))
    assert result["paired_complete_cases"] == 0
    assert result["incomplete_cases"] == ["offer-only"]
    assert not result["gate_passed"]
    args = Namespace(
        baseline=str(a_path),
        candidate=str(b_path),
        format="markdown",
        fail_on_regression=True,
    )
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


@pytest.mark.parametrize(
    "corruption",
    [
        "truncated_final",
        "request_error",
        "missing_completions",
        "extra_completion",
        "missing_trace",
        "trace_message",
        "trace_outcome",
        "missing_claims",
        "missing_extraction",
        "inner_audit_flag",
        "decision_detail",
        "format_boolean",
        "config_boolean",
        "missing_source_file",
        "missing_versions",
        "bad_claim_index",
        "deleted_findings",
        "error_on_complete_audit",
        "missing_conversation",
        "bad_call_shape",
    ],
)
def test_corrupted_saved_evidence_cannot_produce_clean_cli_gate(tmp_path, capsys, corruption):
    from callprobe.cli import main

    base_path, base = evidence(tmp_path, "baseline")
    save(base_path, base)
    path, report = evidence(tmp_path, "candidate")
    row = report["episodes"][0]
    if corruption == "truncated_final":
        row["completions"][-1]["finish_reason"] = "length"
    elif corruption == "request_error":
        row["completions"][-1]["error"] = "request_error"
    elif corruption == "missing_completions":
        row.pop("completions")
    elif corruption == "extra_completion":
        row["completions"].append(copy.deepcopy(row["completions"][0]))
    elif corruption == "missing_trace":
        row.pop("trace")
    elif corruption == "trace_message":
        row["trace"]["events"][-1]["content"] = "Sent!"
    elif corruption == "trace_outcome":
        row["executions"] = [{"tool": "send_email", "status": "ok"}]
    elif corruption == "missing_claims":
        row["audit"].pop("claims")
    elif corruption == "missing_extraction":
        row.pop("extraction_requests")
    elif corruption == "inner_audit_flag":
        row["audit"]["passed"] = False
    elif corruption == "decision_detail":
        row["decisions"][0].update(schema_ok=False, failures=["invalid arguments"])
    elif corruption == "format_boolean":
        report["format_version"] = True
    elif corruption == "config_boolean":
        report["config"]["extractor_json_mode"] = 1
    elif corruption == "missing_source_file":
        report["source_sha256"]["callprobe"].pop("scoring.py")
    elif corruption == "missing_versions":
        row.pop("versions")
    elif corruption == "bad_claim_index":
        row["audit"]["claims"] = [Claim("I can help later.", "send_email", message_index=True).__dict__]
    elif corruption == "deleted_findings":
        row["audit"]["claims"] = [Claim("I can help later.", "send_email", message_index=2).__dict__]
    elif corruption == "error_on_complete_audit":
        row["audit"]["error"] = {"reason": "source_mismatch", "message_index": 2}
    elif corruption == "missing_conversation":
        row.pop("conversation")
    else:
        row["completions"][0]["calls"] = [{"name": "send_email", "arguments": []}]
    path.write_text(json.dumps(report))
    assert main(["agent", "compare", str(base_path), str(path), "--fail-on-regression"]) == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "field,value",
    [
        ("agent_model", None),
        ("extractor_model", []),
        ("extractor_model", ""),
        ("extractor_endpoint", "file:///tmp/model"),
        ("max_turns", True),
        ("max_turns", 101),
        ("max_tokens", 0),
        ("agent_timeout", 0),
        ("extractor_timeout", -1),
        ("agent_retries", False),
        ("temperature", "0"),
        ("agent_timeout", 10**400),
    ],
)
def test_invalid_request_provenance_is_rejected(tmp_path, field, value):
    path, report = evidence(tmp_path)
    report["config"][field] = value
    with pytest.raises(ValueError):
        save(path, report)


@pytest.mark.parametrize("raw_value", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize("target", ["report", "suite"])
def test_nonfinite_json_rejected_with_setup_exit(tmp_path, capsys, raw_value, target):
    from callprobe.cli import main

    path, report = evidence(tmp_path)
    path.write_text(json.dumps(report))
    file = path if target == "report" else path.parent / "suite.json"
    file.write_text(file.read_text()[:-1] + ',"invalid_number":' + raw_value + "}")
    assert main(["agent", "compare", str(path), str(path), "--fail-on-regression"]) == 2
    assert "nonfinite" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["report", "suite"])
def test_duplicate_json_keys_rejected_with_setup_exit(tmp_path, capsys, target):
    from callprobe.cli import main

    path, report = evidence(tmp_path)
    path.write_text(json.dumps(report))
    file = path if target == "report" else path.parent / "suite.json"
    key = "status" if target == "report" else "version"
    file.write_text(file.read_text()[:-1] + "," + json.dumps(key) + ":null}")
    assert main(["agent", "compare", str(path), str(path), "--fail-on-regression"]) == 2
    assert "duplicate JSON keys" in capsys.readouterr().err


@pytest.mark.parametrize("model", ["qwen25", "llama31"])
def test_archived_live_reports_still_replay_without_model_requests(model, monkeypatch):
    from pathlib import Path

    from didyoureally.extract import LLMExtractor

    from callprobe.client import ChatClient

    def forbidden(*args, **kwargs):
        raise AssertionError("offline comparison must not contact a model")

    monkeypatch.setattr(ChatClient, "complete", forbidden)
    monkeypatch.setattr(LLMExtractor, "extract", forbidden)
    path = Path(__file__).parents[1] / "results/2026-10-04-joint-agent-pilot" / model / "report.json"
    report = load_agent_run(str(path))
    assert len(report["episodes"]) == 12
    assert compare_agent_runs(report, report)["cases"] == 12
