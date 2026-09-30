"""The offline demo: `callprobe demo`. No model endpoint or network access."""

import shlex
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.demo import INSPECT_TASK, REGRESSED_TASKS, SUITE_DIRNAME, generate_demo_files
from callprobe.loader import load_suite
from callprobe.models import Run
from callprobe.validate import validate_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = {
    "baseline.json": REPO_ROOT / "results" / "github-issues" / "qwen2.5-7b.json",
    "candidate.json": REPO_ROOT / "results" / "github-issues" / "qwen3-8b.json",
    "comparison.txt": REPO_ROOT / "results" / "github-issues" / "comparison.txt",
    "CONDITIONS.md": REPO_ROOT / "results" / "github-issues" / "README.md",
}


class _UnreachableClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError("ChatClient must not be constructed by `callprobe demo`")


def _boom(_):
    raise AssertionError("probe_server_version must not be called by `callprobe demo`")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    monkeypatch.setattr(cli, "probe_server_version", _boom)


def test_bundled_demo_resources_match_canonical_results_byte_for_byte():
    for name, canonical_path in CANONICAL.items():
        bundled_name = "README.md" if name == "CONDITIONS.md" else name
        bundled = (REPO_ROOT / "src" / "callprobe" / "demo_data" / bundled_name).read_bytes()
        assert bundled == canonical_path.read_bytes(), f"demo_data/{bundled_name} has drifted"


def test_generate_demo_files_writes_baseline_and_candidate_verbatim():
    top_files, suite_files = generate_demo_files()
    assert top_files["baseline.json"] == CANONICAL["baseline.json"].read_text(encoding="utf-8")
    assert top_files["candidate.json"] == CANONICAL["candidate.json"].read_text(encoding="utf-8")
    assert "(baseline.json)" in top_files["CONDITIONS.md"]
    assert "(candidate.json)" in top_files["CONDITIONS.md"]
    assert "OFFLINE DEMO" in top_files["DEMO.md"]
    assert "tools.yaml" in suite_files and "tasks.yaml" in suite_files


def test_demo_cli_creates_a_complete_offline_directory(tmp_path, capsys):
    out = tmp_path / "callprobe-demo"
    code = cli.main(["demo", "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "OFFLINE DEMO" in printed
    assert "5/18" in printed and "11/18" in printed
    for name in REGRESSED_TASKS:
        assert name in printed

    assert (out / "baseline.json").read_bytes() == CANONICAL["baseline.json"].read_bytes()
    assert (out / "candidate.json").read_bytes() == CANONICAL["candidate.json"].read_bytes()
    assert (out / "comparison.txt").read_bytes() == CANONICAL["comparison.txt"].read_bytes()
    assert (out / "DEMO.md").exists()

    suite_dir = out / SUITE_DIRNAME
    suite = load_suite(suite_dir)
    assert len(suite.tasks) == 18
    assert not validate_suite(suite)

    baseline = Run.model_validate_json((out / "baseline.json").read_text(encoding="utf-8"))
    candidate = Run.model_validate_json((out / "candidate.json").read_text(encoding="utf-8"))
    assert baseline.config.suite_hash == suite.hash
    assert candidate.config.suite_hash == suite.hash
    assert sum(r.success for r in baseline.results) == 5
    assert sum(r.success for r in candidate.results) == 11


def test_demo_gate_reproduces_the_two_recorded_regressions(tmp_path):
    out = tmp_path / "callprobe-demo"
    assert cli.main(["demo", "--out", str(out)]) == 0
    code = cli.main([
        "compare", str(out / "baseline.json"), str(out / "candidate.json"),
        "--fail-on-regression", "--format", "json",
    ])
    assert code == 1


def test_demo_gate_json_output_names_the_two_regressions(tmp_path, capsys):
    out = tmp_path / "callprobe-demo"
    assert cli.main(["demo", "--out", str(out)]) == 0
    capsys.readouterr()
    code = cli.main([
        "compare", str(out / "baseline.json"), str(out / "candidate.json"),
        "--fail-on-regression", "--format", "json",
    ])
    assert code == 1
    import json
    payload = json.loads(capsys.readouterr().out)
    regressed = {r["task_id"] for r in payload["gate"]["regressions"]}
    assert regressed == set(REGRESSED_TASKS)


def test_demo_explain_works_offline_on_the_candidate(tmp_path, capsys):
    out = tmp_path / "callprobe-demo"
    assert cli.main(["demo", "--out", str(out)]) == 0
    capsys.readouterr()
    code = cli.main([
        "explain", str(out / "candidate.json"), "--suite", str(out / SUITE_DIRNAME),
        "--task", INSPECT_TASK,
    ])
    assert code == 0
    printed = capsys.readouterr().out
    assert INSPECT_TASK in printed
    assert "shape hint" in printed or "schema error" in printed


def test_demo_output_path_can_be_pasted_into_shell(tmp_path, capsys):
    out = tmp_path / "demo with 'quotes' and $characters"
    assert cli.main(["demo", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    commands = [line.strip() for line in printed.splitlines() if line.strip().startswith("callprobe ")]
    assert commands
    for command in commands:
        parts = shlex.split(command)
        assert parts[0] == "callprobe"


def test_demo_respects_overwrite_protection_and_leaves_existing_files_untouched(tmp_path):
    out = tmp_path / "callprobe-demo"
    assert cli.main(["demo", "--out", str(out)]) == 0
    marker = (out / "baseline.json").read_bytes()
    (out / "baseline.json").write_bytes(b"do not touch me")

    assert cli.main(["demo", "--out", str(out)]) == 1
    assert (out / "baseline.json").read_bytes() == b"do not touch me"

    assert cli.main(["demo", "--out", str(out), "--force"]) == 0
    assert (out / "baseline.json").read_bytes() == marker


def test_demo_protects_untracked_existing_directory_without_force(tmp_path):
    out = tmp_path / "callprobe-demo"
    out.mkdir()
    (out / "notes.txt").write_text("keep me", encoding="utf-8")
    assert cli.main(["demo", "--out", str(out)]) == 0
    assert (out / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_demo_default_out_directory_name():
    top_files, _ = generate_demo_files()
    assert set(top_files) == {"baseline.json", "candidate.json", "CONDITIONS.md", "DEMO.md", "comparison.txt"}


def test_suite_conflict_does_not_write_partial_demo(tmp_path):
    out = tmp_path / "demo"
    suite = out / SUITE_DIRNAME
    suite.mkdir(parents=True)
    (suite / "tasks.yaml").write_text("preserve this")
    assert cli.main(["demo", "--out", str(out)]) == 1
    assert not (out / "baseline.json").exists()
    assert (suite / "tasks.yaml").read_text() == "preserve this"
