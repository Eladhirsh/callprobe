import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_ci_pilot_suite.py"


@pytest.mark.parametrize("absolute", [False, True])
def test_pilot_results_stay_under_requested_output_from_another_directory(tmp_path, monkeypatch, absolute):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "results" / "pilot"
    argument = str(output) if absolute else "results/pilot"
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--base-url", "http://unused.invalid/v1", "--out", argument]
    )
    outputs = []

    def fake_run(command, *, cwd):
        destination = Path(cwd) / command[command.index("--out") + 1]
        outputs.append(destination)
        assert destination.parent == output
        destination.mkdir()
        (destination / "report.md").write_text("Synthetic offline result")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert runpy.run_path(str(SCRIPT))["main"]() == 0
    assert outputs == [output / name for name in ("screen", "development", "validation")]
    assert all((destination / "report.md").is_file() for destination in outputs)
