"""Exercise the composite action's shell without a network or model server."""

import os
import re
import tempfile
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
    assert (tmp_path / "callprobe-comparison.md").read_text().strip() == "{}"
    # Both compare invocations read the same saved baseline/results files.
    assert args.count("baseline.json") == 2
    assert args.count("--format") == 2 + 1  # run + json compare + markdown compare
    assert "markdown" in args and "json" in args


def test_action_rejects_baseline_output_collision(tmp_path):
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Run callprobe")
    baseline = tmp_path / "callprobe-results.json"
    baseline.write_text("baseline evidence")
    env = {**os.environ, "CALLPROBE_BASELINE": str(baseline), "CALLPROBE_POLICY": ""}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 2
    assert baseline.read_text() == "baseline evidence"


@pytest.mark.parametrize("run_exit,gate_exit,baseline,expected,compared,md_compared", [
    (1, 0, True, 1, True, True),
    (1, 1, True, 1, True, True),
    # A fatal compare error (exit > 1) skips the redundant Markdown re-render;
    # the JSON comparison evidence from that same fatal attempt is still kept.
    (1, 2, True, 2, True, False),
    (2, 0, True, 2, False, False),
    (1, 0, False, 1, False, False),
    (0, 0, False, 0, False, False),
])
def test_action_keeps_comparison_after_threshold_failure(
    tmp_path, run_exit, gate_exit, baseline, expected, compared, md_compared
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
    assert (tmp_path / "callprobe-comparison.md").exists() == md_compared


@pytest.mark.parametrize(
    "failed_output",
    ["callprobe-summary.json", "callprobe-comparison.json", "callprobe-comparison.md"],
)
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
    assert ("compare" in calls) == (failed_output != "callprobe-summary.json")
    if failed_output == "callprobe-comparison.md":
        # The JSON comparison from the same, successful compare call is kept;
        # only the Markdown re-render's own write failure is fatal.
        assert (tmp_path / "callprobe-comparison.json").read_text().strip() == "{}"
    else:
        assert not (tmp_path / "callprobe-comparison.md").exists()


def test_action_clears_stale_reports_without_touching_inputs(tmp_path):
    script = next(s["run"] for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
                  if s["name"] == "Run callprobe")
    executable = tmp_path / "callprobe"
    executable.write_text(
        '#!/bin/bash\necho "$1" >> "$ARGS_FILE"\necho "{}"\nexit "$GATE_EXIT"\n'
    )
    executable.chmod(0o755)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("baseline evidence")
    base_env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
                "ARGS_FILE": str(tmp_path / "args"), "CALLPROBE_MODEL": "stub",
                "CALLPROBE_ENDPOINT": "http://unused", "CALLPROBE_SUITE": "",
                "CALLPROBE_FAIL_UNDER": "", "CALLPROBE_PAD": "0",
                "CALLPROBE_REPEATS": "1", "CALLPROBE_MAX_TOKENS": "2048",
                "CALLPROBE_BASELINE": "baseline.json"}

    # First invocation succeeds and leaves reports (and results) behind.
    first_env = {**base_env, "GATE_EXIT": "0", "CALLPROBE_POLICY": ""}
    first = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=first_env, capture_output=True)
    assert first.returncode == 0, first.stderr
    assert (tmp_path / "callprobe-comparison.json").exists()
    assert (tmp_path / "callprobe-comparison.md").exists()

    # A prior run's results file is a real input to compare, not one of this
    # step's own generated reports; it must never be cleared either.
    prior_results = tmp_path / "callprobe-results.json"
    prior_results.write_text("prior results evidence")

    # Second invocation fails validation before ever reaching compare (a
    # policy without a baseline). Its own stale reports must not survive,
    # but the baseline and results inputs must be untouched.
    second_env = {**base_env, "GATE_EXIT": "0", "CALLPROBE_POLICY": "policy.yaml",
                  "CALLPROBE_BASELINE": ""}
    second = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=second_env, capture_output=True)
    assert second.returncode == 2, second.stderr
    assert not (tmp_path / "callprobe-comparison.json").exists()
    assert not (tmp_path / "callprobe-comparison.md").exists()
    assert not (tmp_path / "callprobe-summary.json").exists()
    assert baseline.read_text() == "baseline evidence"
    assert prior_results.read_text() == "prior results evidence"


def test_action_renders_markdown_from_same_saved_run_and_gate_args(tmp_path):
    script = next(s["run"] for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
                  if s["name"] == "Run callprobe")
    executable = tmp_path / "callprobe"
    executable.write_text(
        '#!/bin/bash\n'
        'echo "$*" >> "$ARGS_FILE"\n'
        'if [ "$1" = compare ]; then\n'
        '  fmt="${@: -1}"\n'
        '  if [ "$fmt" = markdown ]; then echo "## Comparison (markdown)"; else echo "{\\"json\\":true}"; fi\n'
        '  exit 0\n'
        'fi\n'
        'echo "{}"\n'
    )
    executable.chmod(0o755)
    (tmp_path / "baseline.json").write_text("{}")
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "ARGS_FILE": str(tmp_path / "args"), "CALLPROBE_MODEL": "stub",
           "CALLPROBE_ENDPOINT": "http://unused", "CALLPROBE_SUITE": "",
           "CALLPROBE_FAIL_UNDER": "", "CALLPROBE_PAD": "0",
           "CALLPROBE_REPEATS": "1", "CALLPROBE_MAX_TOKENS": "2048",
           "CALLPROBE_BASELINE": "baseline.json", "CALLPROBE_POLICY": "", "GITHUB_OUTPUT": str(tmp_path / "outputs")}
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "callprobe-comparison.json").read_text().strip() == '{"json":true}'
    assert (tmp_path / "callprobe-comparison.md").read_text().strip() == "## Comparison (markdown)"
    assert (tmp_path / "outputs").read_text().splitlines() == ["summary_ready=true", "comparison_ready=true"]
    calls = (tmp_path / "args").read_text().splitlines()
    compare_calls = [c for c in calls if c.startswith("compare ")]
    assert len(compare_calls) == 2
    for call in compare_calls:
        assert "baseline.json callprobe-results.json" in call
        assert "--fail-on-regression" in call
    # No extra model request: only the pre-existing "run" call touches the
    # model endpoint; both compare calls just re-read the saved run files.
    assert sum(1 for c in calls if c.startswith("run ")) == 1


def _write_summary_script_env(tmp_path, model, extra_env=None):
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Write step summary")
    env = {**os.environ, "CALLPROBE_MODEL": model,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
           "CALLPROBE_SUMMARY_READY": "true", "CALLPROBE_COMPARISON_READY": "true"}
    if extra_env:
        env.update(extra_env)
    return script, env


def test_action_summary_renders_markdown_comparison_not_raw_json(tmp_path):
    (tmp_path / "callprobe-summary.json").write_text('{"overall": {"success": 0.5}}')
    (tmp_path / "callprobe-comparison.md").write_text("## Comparison\n\nsome rendered markdown\n")
    script, env = _write_summary_script_env(tmp_path, "my-model")
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    summary = (tmp_path / "summary.md").read_text()
    assert "## callprobe: my-model" in summary
    assert "## Comparison" in summary
    assert "some rendered markdown" in summary
    # The raw run JSON is retained, but only inside a fenced code block.
    assert '"overall"' in summary
    assert "<details>" in summary and "</details>" in summary


def test_action_summary_has_no_comparison_section_without_baseline(tmp_path):
    (tmp_path / "callprobe-summary.json").write_text('{"overall": {"success": 1.0}}')
    script, env = _write_summary_script_env(tmp_path, "my-model")
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    summary = (tmp_path / "summary.md").read_text()
    assert "Comparison" not in summary


def test_action_summary_escapes_hostile_model_label():
    hostile_model = "evil\n# Injected heading\n```\n<script>alert(1)</script>"
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Write step summary")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "CALLPROBE_MODEL": hostile_model,
               "GITHUB_STEP_SUMMARY": f"{tmp}/summary.md"}
        completed = subprocess.run(["bash", "-c", script], cwd=tmp, env=env, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        summary = open(f"{tmp}/summary.md", encoding="utf-8").read()
        heading = summary.splitlines()[0]
        assert heading.startswith("## callprobe: ")
        # The hostile label is confined to a single, escaped heading line: no
        # injected heading, fence, or raw HTML tag reaches the summary.
        assert summary.count("\n# Injected heading") == 0
        assert "```" not in heading
        assert "<script>" not in summary


def test_action_summary_fences_survive_hostile_raw_output(tmp_path):
    hostile_raw = '```json\n{"payload": "```\\n## Injected heading\\n"}\n```'
    (tmp_path / "callprobe-summary.json").write_text(hostile_raw)
    script, env = _write_summary_script_env(tmp_path, "stub")
    completed = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    summary = (tmp_path / "summary.md").read_text()
    # The fence used to wrap the raw output must be longer than any run of
    # backticks already present in that output, so it cannot be closed early.
    longest_run_in_raw = max((len(r) for r in re.findall(r"`+", hostile_raw)), default=0)
    fence = "`" * (longest_run_in_raw + 1)
    lines = summary.splitlines()
    assert f"{fence}json" in lines
    assert fence in lines
    assert hostile_raw in summary


@pytest.mark.parametrize("input_name", ["CALLPROBE_BASELINE", "CALLPROBE_POLICY"])
@pytest.mark.parametrize("report", ["callprobe-results.json", "callprobe-summary.json", "callprobe-comparison.json", "callprobe-comparison.md"])
def test_action_never_removes_or_overwrites_aliased_inputs(tmp_path, input_name, report):
    source = tmp_path / report
    source.write_text("preserve evidence")
    alias = tmp_path / "input-alias"
    alias.symlink_to(source)
    script = next(s["run"] for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
                  if s["name"] == "Run callprobe")
    env = {**os.environ, "CALLPROBE_BASELINE": "", "CALLPROBE_POLICY": "",
           input_name: str(alias)}
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode == 2
    assert source.read_text() == "preserve evidence"


def test_summary_ignores_reports_without_current_step_readiness(tmp_path):
    (tmp_path / "callprobe-summary.json").write_text("STALE RAW")
    (tmp_path / "callprobe-comparison.md").write_text("STALE COMPARISON")
    script, env = _write_summary_script_env(tmp_path, "stub", {
        "CALLPROBE_SUMMARY_READY": "", "CALLPROBE_COMPARISON_READY": ""})
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode == 0
    assert "STALE" not in (tmp_path / "summary.md").read_text()
