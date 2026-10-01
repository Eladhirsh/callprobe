"""model_sweep tests: subprocess is mocked, so no CLI, model, or network is touched."""

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from callprobe import cli, sweep


class Fake:
    """Stands in for subprocess.run; `fail` maps (model, step) to a failure kind."""

    def __init__(self, monkeypatch, fail=None):
        self.calls, self.fail = [], fail or {}
        monkeypatch.setattr(sweep.subprocess, "run", self)

    def __call__(self, command, **kw):
        self.calls.append((command, kw))
        model = next((a.split("=", 1)[1] for a in command if a.startswith("--model=")), None)
        sub = command[3]
        step = "dry-run" if "--dry-run" in command else sub
        kind = self.fail.get((model, step))
        if kind == "timeout":
            raise subprocess.TimeoutExpired(command, kw["timeout"], output=b"partial")
        if kind == "exit":
            return subprocess.CompletedProcess(command, 1, "", "boom")
        if step == "run":
            out = next(a.split("=", 1)[1] for a in command if a.startswith("--out="))
            if kind != "nofile":
                (Path(kw["cwd"]) / out).write_text("{}")
            return subprocess.CompletedProcess(command, 0, "done", "")
        stdout = json.dumps({"total_requests": 5}) if step == "dry-run" else "ok"
        return subprocess.CompletedProcess(command, 0, stdout, "")


def run(tmp_path, *extra, models=("a", "b")):
    out = tmp_path / "out"
    code = sweep.main(["--models", *models, "--out", str(out), *extra])
    manifest_path = out / "manifest.json"
    return code, out, json.loads(manifest_path.read_text()) if manifest_path.exists() else None


def test_dry_run_plans_all_and_executes_nothing(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    code, out, m = run(tmp_path, "--dry-run")
    assert code == 0 and m["total_planned_requests"] == 10
    assert len(fake.calls) == 2 and all("--dry-run" in c for c, _ in fake.calls)
    assert not list(out.glob("*result.json")) and not (out / "leaderboard.md").exists()


def test_dry_runs_precede_real_runs_with_safe_settings(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    monkeypatch.setenv("PYTHONPATH", "/x")
    monkeypatch.setenv("PYTHONHOME", "/y")
    code, out, m = run(tmp_path)
    kinds = ["dry" if "--dry-run" in c else c[3] for c, _ in fake.calls]
    assert kinds == ["dry", "dry", "run", "run", "leaderboard"] and code == 0
    for _, kw in fake.calls:
        assert "PYTHONPATH" not in kw["env"] and "PYTHONHOME" not in kw["env"]
        assert kw["shell"] is False and kw["timeout"] > 0
    assert {"--temperature=0", "--concurrency=1", "--retries=0", "--fail-under=0"} <= set(fake.calls[2][0])
    assert not any(a.startswith("--api-key") for c, _ in fake.calls for a in c)
    assert m["leaderboard"]["models"] == ["a", "b"]
    assert m["leaderboard"]["steps"][0]["returncode"] == 0


def test_failure_continues_and_excludes_failed_result(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, {("a", "run"): "exit"})
    code, out, m = run(tmp_path)
    assert code == 1
    assert [e["status"] for e in m["models"]] == ["failed", "ok"]
    board = next(c for c, _ in fake.calls if c[3] == "leaderboard")
    assert board[4:] == ["02-result.json"]


def test_timeout_and_missing_result_file_are_failures(tmp_path, monkeypatch):
    Fake(monkeypatch, {("a", "run"): "timeout", ("b", "run"): "nofile"})
    code, out, m = run(tmp_path)
    assert code == 1 and m["leaderboard"] is None
    assert m["models"][0]["steps"][-1]["status"] == "timeout"
    assert (out / "01-run.stdout.txt").read_text() == "partial"


def test_existing_output_untouched_and_no_stale_results(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    out = tmp_path / "old"
    out.mkdir()
    (out / "01-result.json").write_text("stale")
    assert sweep.main(["--models", "a", "--out", str(out)]) == 2
    assert (out / "01-result.json").read_text() == "stale" and not fake.calls
    Fake(monkeypatch, {("a", "run"): "exit"})
    code, fresh, m = run(tmp_path / "fresh", models=("a",))
    assert code == 1 and m["leaderboard"] is None
    assert not list(fresh.glob("*result.json"))


def test_explain_only_with_explicit_suite(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    run(tmp_path, models=("a",))
    assert not any(c[3] == "explain" for c, _ in fake.calls)
    fake.calls.clear()
    (tmp_path / "s").mkdir()
    sweep.main(["--models", "a", "--out", str(tmp_path / "o2"), "--suite", str(tmp_path / "s")])
    assert any(c[3] == "explain" for c, _ in fake.calls)


def test_filenames_independent_of_model_names(tmp_path, monkeypatch):
    Fake(monkeypatch)
    code, out, m = run(tmp_path, models=("../evil/x:1", "a b;rm"))
    assert code == 0
    assert all(p.parent == out for p in out.iterdir())
    assert (out / "01-result.json").exists() and (out / "02-result.json").exists()


@pytest.mark.parametrize("endpoint", [
    "http://user:pw@host/v1", "http://:pw@host/v1", "http://host/v1?key=1",
    "http://host/v1#f", "ftp://host", "nohost"])
def test_bad_endpoints_rejected(tmp_path, monkeypatch, endpoint):
    fake = Fake(monkeypatch)
    assert sweep.main(["--models", "a", "--out", str(tmp_path / "o"), "--endpoint", endpoint]) == 2
    assert not fake.calls and not (tmp_path / "o").exists()


def test_duplicate_models_and_bad_timeout_rejected(tmp_path, monkeypatch):
    Fake(monkeypatch)
    assert sweep.main(["--models", "a", "a", "--out", str(tmp_path / "o")]) == 2
    with pytest.raises(SystemExit):
        sweep.main(["--models", "a", "--out", str(tmp_path / "o"), "--timeout", "0"])


def test_secret_inherited_but_not_in_commands_or_saved_output(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret-value")
    fake = Fake(monkeypatch)
    run(tmp_path, models=("a",))
    assert all("s3cret-value" not in " ".join(c) for c, _ in fake.calls)
    assert all(kw["env"]["API_KEY"] == "s3cret-value" for _, kw in fake.calls)
    assert sweep.redact("x s3cret-value y") == "x [redacted] y"


def test_relative_python_not_symlink_resolved(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.write_text("")
    (tmp_path / "venv-python").symlink_to(real)
    monkeypatch.chdir(tmp_path)
    assert sweep.resolve_python("./venv-python") == str(tmp_path / "venv-python")


def test_public_cli_dry_run(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    out = tmp_path / "new"
    assert cli.main(["sweep", "--models", "a", "b", "--out", str(out), "--dry-run"]) == 0
    assert json.loads((out / "manifest.json").read_text())["total_planned_requests"] == 10
    assert len(fake.calls) == 2 and all("--dry-run" in c for c, _ in fake.calls)


def test_public_cli_propagates_failure_status(tmp_path, monkeypatch):
    Fake(monkeypatch, fail={("a", "run"): "exit"})
    out = tmp_path / "new"
    assert cli.main(["sweep", "--models", "a", "--out", str(out)]) == 1
    assert json.loads((out / "manifest.json").read_text())["failed"] is True


def test_public_cli_refuses_existing_out(tmp_path):
    assert cli.main(["sweep", "--models", "a", "--out", str(tmp_path)]) == 2


def test_public_cli_help_states_scope(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["sweep", "--help"])
    assert exc.value.code == 0
    text = " ".join(capsys.readouterr().out.split()).lower()
    assert "one at a time" in text and "never downloads" in text and "already served" in text


def test_public_cli_and_standalone_parse_identically(monkeypatch):
    seen = {}

    def capture(ns):
        seen["ns"] = ns
        return 0

    monkeypatch.setattr(cli, "run_sweep", capture)
    assert cli.main(["sweep", "--models", "a", "--out", "x"]) == 0
    standalone = argparse.ArgumentParser()
    sweep.add_arguments(standalone)
    expected = vars(standalone.parse_args(["--models", "a", "--out", "x"]))
    actual = {k: v for k, v in vars(seen["ns"]).items() if k not in ("command", "func")}
    assert actual == expected
    assert (expected["endpoint"], expected["pad"], expected["repeats"], expected["max_tokens"],
            expected["timeout"], expected["dry_run"]) == (
        sweep.DEFAULT_ENDPOINT, "0", 1, 4096, 1800.0, False)


def test_script_entry_point_delegates_to_package():
    import runpy
    script = Path(__file__).resolve().parents[1] / "scripts" / "model_sweep.py"
    assert runpy.run_path(str(script))["main"] is sweep.main


def test_default_request_timeout_forwarded_and_recorded(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    code, out, m = run(tmp_path, models=("a",))
    assert code == 0
    assert m["request_timeout_seconds"] == 120.0
    for command, _ in fake.calls:
        if command[3] == "run":
            assert "--request-timeout=120.0" in command


def test_custom_request_timeout_forwarded_and_recorded(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    code, out, m = run(tmp_path, "--request-timeout", "45", models=("a",))
    assert code == 0
    assert m["request_timeout_seconds"] == 45.0
    forwarded = any(
        "--request-timeout=45.0" in command
        for command, _ in fake.calls if command[3] in ("run",) or "--dry-run" in command
    )
    assert forwarded


def test_request_timeout_separate_from_step_timeout(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    code, out, m = run(
        tmp_path, "--timeout", "600", "--request-timeout", "30", models=("a",)
    )
    assert code == 0
    assert m["timeout_seconds"] == 600.0
    assert m["request_timeout_seconds"] == 30.0
    for _, kwargs in fake.calls:
        assert kwargs["timeout"] == 600.0


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_bad_request_timeout_rejected_before_output_created(tmp_path, monkeypatch, value):
    fake = Fake(monkeypatch)
    out = tmp_path / "will-not-exist"
    with pytest.raises(SystemExit):
        sweep.main(["--models", "a", "--out", str(out), "--request-timeout", value])
    assert not out.exists()
    assert not fake.calls


def test_manifest_exposes_running_step_before_subprocess_finishes(tmp_path, monkeypatch):
    fake = Fake(monkeypatch)
    observed = []

    def inspect(command, **kwargs):
        manifest = json.loads((Path(kwargs["cwd"]) / "manifest.json").read_text())
        observed.append(manifest["status"])
        if command[3] == "run":
            assert any(step["status"] == "running" for model in manifest["models"]
                       for step in model["steps"])
        return fake(command, **kwargs)

    monkeypatch.setattr(sweep.subprocess, "run", inspect)
    code, _, manifest = run(tmp_path, models=("a",))
    assert code == 0 and observed and set(observed) == {"running"}
    assert manifest["status"] == "complete"
