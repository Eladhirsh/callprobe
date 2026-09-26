"""Exercise the composite action's shell without a network or model server."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ACTION = Path(__file__).resolve().parents[1] / "action.yml"


@pytest.mark.parametrize("policy,gate_exit", [("", 0), ("policy.yaml", 0), ("", 1)])
def test_action_passes_arguments_and_propagates_gate_failure(tmp_path, policy, gate_exit):
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Run callprobe")
    executable = tmp_path / "callprobe"
    executable.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$@" >> "$ARGS_FILE"\n'
        'echo "{}"\n'
        'if [ "$1" = compare ]; then exit "$GATE_EXIT"; fi\n'
    )
    executable.chmod(0o755)
    (tmp_path / "baseline.json").write_text("{}")
    model = 'model; $(touch injected)'
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "ARGS_FILE": str(tmp_path / "args"), "GATE_EXIT": str(gate_exit),
           "CALLPROBE_MODEL": model, "CALLPROBE_ENDPOINT": "http://localhost:1234/v1",
           "CALLPROBE_SUITE": "suite with spaces", "CALLPROBE_FAIL_UNDER": "",
           "CALLPROBE_PAD": "0,8", "CALLPROBE_REPEATS": "2", "CALLPROBE_MAX_TOKENS": "4096",
           "CALLPROBE_BASELINE": "baseline.json", "CALLPROBE_POLICY": policy}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == gate_exit, completed.stderr
    args = (tmp_path / "args").read_text().splitlines()
    assert model in args
    assert "suite with spaces" in args
    assert "--policy" in args if policy else "--fail-on-regression" in args
    assert not (tmp_path / "injected").exists()
    assert (tmp_path / "callprobe-comparison.json").read_text().strip() == "{}"


def test_action_rejects_baseline_output_collision(tmp_path):
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Run callprobe")
    baseline = tmp_path / "callprobe-results.json"
    baseline.write_text("baseline evidence")
    env = {**os.environ, "CALLPROBE_BASELINE": str(baseline), "CALLPROBE_POLICY": ""}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 2
    assert baseline.read_text() == "baseline evidence"


@pytest.mark.parametrize("run_exit,gate_exit,baseline,expected,compared", [
    (1, 0, True, 1, True),
    (1, 1, True, 1, True),
    (1, 2, True, 2, True),
    (2, 0, True, 2, False),
    (1, 0, False, 1, False),
    (0, 0, False, 0, False),
])
def test_action_keeps_comparison_after_threshold_failure(
    tmp_path, run_exit, gate_exit, baseline, expected, compared
):
    script = next(s["run"] for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
                  if s["name"] == "Run callprobe")
    executable = tmp_path / "callprobe"
    executable.write_text(
        '#!/bin/bash\n'
        'echo "$1" >> "$ARGS_FILE"\n'
        'echo "{}"\n'
        'if [ "$1" = run ]; then exit "$RUN_EXIT"; fi\n'
        'exit "$GATE_EXIT"\n'
    )
    executable.chmod(0o755)
    (tmp_path / "baseline.json").write_text("{}")
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "ARGS_FILE": str(tmp_path / "args"), "RUN_EXIT": str(run_exit),
           "GATE_EXIT": str(gate_exit), "CALLPROBE_MODEL": "stub",
           "CALLPROBE_ENDPOINT": "http://unused", "CALLPROBE_SUITE": "",
           "CALLPROBE_FAIL_UNDER": "0.9", "CALLPROBE_PAD": "0",
           "CALLPROBE_REPEATS": "1", "CALLPROBE_MAX_TOKENS": "2048",
           "CALLPROBE_BASELINE": "baseline.json" if baseline else "",
           "CALLPROBE_POLICY": ""}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == expected, completed.stderr
    assert ("compare" in (tmp_path / "args").read_text().splitlines()) == compared
    assert (tmp_path / "callprobe-comparison.json").exists() == compared


@pytest.mark.parametrize("failed_output", ["callprobe-summary.json", "callprobe-comparison.json"])
def test_action_does_not_hide_report_write_failures(tmp_path, failed_output):
    script = next(s["run"] for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
                  if s["name"] == "Run callprobe")
    for name, text in {
        "callprobe": '#!/bin/bash\necho "$1" >> "$ARGS_FILE"\necho "{}"\n',
        "tee": '#!/bin/bash\nif [ "$1" = "$FAILED_OUTPUT" ]; then cat >/dev/null; exit 7; fi\nexec /usr/bin/tee "$@"\n',
    }.items():
        executable = tmp_path / name
        executable.write_text(text)
        executable.chmod(0o755)
    (tmp_path / "baseline.json").write_text("{}")
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "ARGS_FILE": str(tmp_path / "args"), "FAILED_OUTPUT": failed_output,
           "CALLPROBE_MODEL": "stub", "CALLPROBE_ENDPOINT": "http://unused",
           "CALLPROBE_SUITE": "", "CALLPROBE_FAIL_UNDER": "",
           "CALLPROBE_PAD": "0", "CALLPROBE_REPEATS": "1",
           "CALLPROBE_MAX_TOKENS": "2048", "CALLPROBE_BASELINE": "baseline.json",
           "CALLPROBE_POLICY": ""}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 7, completed.stderr
    calls = (tmp_path / "args").read_text().splitlines()
    assert ("compare" in calls) == (failed_output == "callprobe-comparison.json")
