"""model_sweep tests: subprocess is mocked, so no CLI, model, or network is touched."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "model_sweep.py"
spec = importlib.util.spec_from_file_location("model_sweep", SCRIPT)
sweep = importlib.util.module_from_spec(spec)
sys.modules["model_sweep"] = sweep
spec.loader.exec_module(sweep)


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
