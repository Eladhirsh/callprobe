"""Exercise real process output and exit codes without a model endpoint."""
import os
from pathlib import Path
import subprocess
import sys

from callprobe import __version__


def invoke(tmp_path, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "callprobe", *map(str, args)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )


def test_module_version_and_help_from_outside_checkout(tmp_path):
    version = invoke(tmp_path, "--version")
    assert version.returncode == 0
    assert version.stdout.strip() == f"callprobe {__version__}"
    assert not version.stderr
    help_result = invoke(tmp_path, "--help")
    assert help_result.returncode == 0
    assert "usage: callprobe" in help_result.stdout
    assert "replay" in help_result.stdout


def test_module_preserves_usage_error_status(tmp_path):
    result = invoke(tmp_path, "not-a-command")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert "Traceback" not in result.stderr


def test_module_preserves_offline_regression_gate_status(tmp_path):
    demo = tmp_path / "demo"
    result = invoke(tmp_path, "demo", "--out", demo)
    assert result.returncode == 0, result.stderr
    compare = invoke(tmp_path, "compare", demo / "baseline.json",
                     demo / "candidate.json", "--fail-on-regression")
    assert compare.returncode == 1
    assert "CI gate: FAIL" in compare.stdout
    assert "Traceback" not in compare.stderr
