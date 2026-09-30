"""Self-test orchestration checks use fake subprocesses, never sockets or network."""

import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "selftest_agent.py"


def test_selftest_detects_false_backing(tmp_path):
    harness = runpy.run_path(str(SCRIPT))
    case = next(c for c in harness["scenarios"]() if c["id"] == "failed-success-flag")
    wrong = subprocess.CompletedProcess([], 0, '{"findings": [{"verdict": "backed"}]}', "")
    with patch("subprocess.run", return_value=wrong):
        row = harness["run_cli"](case, tmp_path, "http://localhost/v1", "synthetic-extractor", llm=True)
    assert not row["passed"]
    assert row["got"] == ["backed"]


def test_selftest_invalid_input_needs_error_evidence(tmp_path):
    harness = runpy.run_path(str(SCRIPT))
    case = next(c for c in harness["scenarios"]() if c["id"] == "unknown-outcome")
    unrelated = subprocess.CompletedProcess([], 2, "", "bad API credentials")
    with patch("subprocess.run", return_value=unrelated):
        row = harness["run_cli"](case, tmp_path, "http://localhost/v1", "synthetic-extractor", llm=True)
    assert not row["passed"]


def test_synthetic_run_drops_credentials_and_live_run_does_not_save_provider_output(tmp_path, monkeypatch):
    harness = runpy.run_path(str(SCRIPT))
    case = harness["scenarios"]()[0]
    monkeypatch.setenv("DYR_API_KEY", "fake-secret")
    response = subprocess.CompletedProcess([], 0, '{"findings": [{"verdict": "backed"}]}', "")
    with patch("subprocess.run", return_value=response) as run:
        row = harness["run_cli"](case, tmp_path / "synthetic", "http://localhost/v1", "m", llm=True)
        assert row["passed"]
        assert "DYR_API_KEY" not in run.call_args.kwargs["env"]
    with patch("subprocess.run", return_value=response):
        harness["run_cli"](case, tmp_path / "live", "http://localhost/v1", "m", llm=True, live=True)
    assert not (tmp_path / "live" / "stdout.txt").exists()
