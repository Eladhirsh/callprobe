import json
import math
from pathlib import Path

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
