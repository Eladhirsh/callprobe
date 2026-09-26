"""Scoring-version migration preserves evidence instead of reinterpreting it."""

from pathlib import Path

from callprobe import cli
from callprobe.examples import generate_example_suite
from callprobe.loader import load_suite
from callprobe.models import Run
from callprobe.runner import prepare_config

RECORDED = Path(__file__).resolve().parents[1] / "results/github-issues/qwen2.5-7b.json"


def _suite(tmp_path):
    root = tmp_path / "suite"
    root.mkdir()
    files, _ = generate_example_suite("github-issues", "github-issues")
    for name, content in files.items():
        (root / name).write_text(content)
    return root


def _forbidden(*args, **kwargs):
    raise AssertionError("migration validation must not call the model")


def test_new_run_config_records_v3_without_mutating_v2_evidence(tmp_path):
    recorded = Run.model_validate_json(RECORDED.read_text())
    assert recorded.config.scoring_version == 2
    prepared = prepare_config(load_suite(_suite(tmp_path)), recorded.config)
    assert prepared.scoring_version == 3
    assert recorded.config.scoring_version == 2


def test_v2_results_still_gate_together_but_mixed_v2_v3_is_refused(tmp_path, capsys):
    assert cli.main(["compare", str(RECORDED), str(RECORDED), "--fail-on-regression"]) == 0
    candidate = Run.model_validate_json(RECORDED.read_text())
    candidate.config.scoring_version = 3
    path = tmp_path / "new.json"
    path.write_text(candidate.model_dump_json())
    assert cli.main(["compare", str(RECORDED), str(path), "--fail-on-regression"]) == 2
    assert "matching scoring_version" in capsys.readouterr().err


def test_failed_from_v2_is_refused_before_network_or_output_changes(tmp_path, monkeypatch, capsys):
    root = _suite(tmp_path)
    output = tmp_path / "output.json"
    output.write_text("preserve evidence")
    monkeypatch.setattr(cli, "probe_server_version", _forbidden)
    monkeypatch.setattr(cli, "ChatClient", _forbidden)
    assert cli.main(["run", "--model", "stub", "--suite", str(root),
                     "--failed-from", str(RECORDED), "--out", str(output)]) == 2
    assert "scoring version" in capsys.readouterr().err
    assert output.read_text() == "preserve evidence"


def test_v2_checkpoint_cannot_be_resumed_with_v3_scoring(tmp_path, monkeypatch, capsys):
    root = _suite(tmp_path)
    recorded = Run.model_validate_json(RECORDED.read_text())
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(RECORDED.read_bytes())
    original = checkpoint.read_bytes()
    monkeypatch.setattr(cli, "ChatClient", _forbidden)
    monkeypatch.setattr(cli, "probe_server_version", lambda _: (
        recorded.config.server_name, recorded.config.server_version))
    assert cli.main(["run", "--model", recorded.config.model, "--suite", str(root),
                     "--pad", "0", "--max-tokens", "4096",
                     "--resume", str(checkpoint), "--out", str(checkpoint)]) == 2
    assert "scoring_version" in capsys.readouterr().err
    assert checkpoint.read_bytes() == original
