import json
import math
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.client import Completion

SUITE = Path(__file__).resolve().parents[1] / "src" / "callprobe" / "suites" / "core"


class _FakeClient:
    """Never calls a tool, so only the abstain tasks succeed."""

    def __init__(self, *args, **kwargs):
        pass

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        return Completion(content="no thanks", prompt_tokens=1, completion_tokens=1)

    def close(self):
        pass


def _run_cli(monkeypatch, extra_args, capsys):
    monkeypatch.setattr(cli, "ChatClient", _FakeClient)
    monkeypatch.setattr(cli, "probe_server_version", lambda _: (None, None))
    args = [
        "run",
        "--model",
        "stub",
        "--suite",
        str(SUITE),
        "--pad",
        "0",
        "--repeats",
        "1",
        "--quiet",
        *extra_args,
    ]
    code = cli.main(args)
    return code, capsys.readouterr().out


def test_format_json_is_valid_and_strict(monkeypatch, capsys):
    code, out = _run_cli(monkeypatch, ["--format", "json"], capsys)
    assert code == 0
    payload = json.loads(out)  # raises if malformed
    assert 0.0 <= payload["overall"]["success"] <= 1.0
    # inf must not leak through as a bare, non-standard JSON token.
    assert "Infinity" not in out
    assert payload["cost"]["tokens_per_success"] is None or math.isfinite(
        payload["cost"]["tokens_per_success"]
    )


def test_fail_under_passes_when_threshold_met(monkeypatch, capsys):
    code, _ = _run_cli(monkeypatch, ["--format", "json", "--fail-under", "0.0"], capsys)
    assert code == 0


def test_fail_under_fails_when_threshold_not_met(monkeypatch, capsys):
    code, _ = _run_cli(monkeypatch, ["--format", "json", "--fail-under", "0.99"], capsys)
    assert code == 1


def test_text_format_unaffected_by_fail_under_flag(monkeypatch, capsys):
    code, out = _run_cli(monkeypatch, ["--fail-under", "0.99"], capsys)
    assert code == 1
    assert "model            stub" in out  # still the human-readable report


def test_missing_resume_file_is_an_error(monkeypatch, tmp_path, capsys):
    code, _ = _run_cli(monkeypatch, ["--resume", str(tmp_path / "missing.json")], capsys)
    assert code == 2


def test_resume_rejects_changed_model_without_overwriting_checkpoint(monkeypatch, tmp_path, capsys):
    path = tmp_path / "run.json"
    assert _run_cli(monkeypatch, ["--out", str(path)], capsys)[0] == 0
    original = path.read_bytes()
    code, _ = _run_cli(monkeypatch, ["--model", "other", "--resume", str(path),
                                    "--out", str(path)], capsys)
    assert code == 2
    assert path.read_bytes() == original


def test_failed_checkpoint_write_preserves_previous_file(monkeypatch, tmp_path):
    from test_gates import make_run

    path = tmp_path / "run.json"
    path.write_text("previous checkpoint")

    def fail_replace(self, target):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        cli._write_run(str(path), make_run())
    assert path.read_text() == "previous checkpoint"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("interrupt", [False, True])
def test_fail_under_cannot_pass_errored_or_interrupted_run(monkeypatch, capsys, interrupt):
    def complete(self, **kwargs):
        if interrupt:
            raise KeyboardInterrupt
        return Completion(error="offline")

    monkeypatch.setattr(_FakeClient, "complete", complete)
    code, _ = _run_cli(monkeypatch, ["--fail-under", "0"], capsys)
    assert code == 1
