"""Bundled runnable examples: `callprobe examples` and `callprobe init --example`."""

from pathlib import Path

import pytest
import yaml

from callprobe import cli
from callprobe.examples import EXAMPLES, generate_example_suite, list_examples
from callprobe.loader import load_suite
from callprobe.validate import validate_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = {
    "support": {
        "openapi.yaml": REPO_ROOT / "examples" / "openapi" / "support-api.yaml",
        "tasks.yaml": REPO_ROOT / "examples" / "openapi" / "tasks.yaml",
    },
    "github-issues": {
        "openapi.json": REPO_ROOT / "examples" / "github-issues" / "openapi.json",
        "tasks.yaml": REPO_ROOT / "examples" / "github-issues" / "tasks.yaml",
        "LICENSE.md": REPO_ROOT / "examples" / "github-issues" / "LICENSE.md",
        "provenance.json": REPO_ROOT / "examples" / "github-issues" / "provenance.json",
    },
}


def test_bundled_resources_match_canonical_examples_byte_for_byte():
    for key, files in CANONICAL.items():
        bundled_dir = REPO_ROOT / "src" / "callprobe" / "examples" / key
        for filename, canonical_path in files.items():
            bundled = (bundled_dir / filename).read_bytes()
            assert bundled == canonical_path.read_bytes(), f"{key}/{filename} has drifted"


def test_list_examples_reports_support_and_github_issues():
    entries = {name: count for name, count, _ in list_examples()}
    assert entries == {"support": 6, "github-issues": 18}


def test_examples_cli_lists_both_examples(capsys):
    assert cli.main(["examples"]) == 0
    out = capsys.readouterr().out
    assert "support" in out and "(6 tasks)" in out
    assert "github-issues" in out and "(18 tasks)" in out
    assert "callprobe init --example" in out


@pytest.mark.parametrize("key", sorted(EXAMPLES))
def test_generated_example_suite_is_valid_and_fully_active(key, tmp_path):
    files, result = generate_example_suite(key, key)
    assert result.tools
    root = tmp_path / key
    root.mkdir()
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    suite = load_suite(root)
    assert suite.tasks
    assert not validate_suite(suite)
    if EXAMPLES[key]["provenance_files"]:
        for filename in EXAMPLES[key]["provenance_files"]:
            assert (root / filename).exists()


def test_init_with_example_writes_a_ready_to_run_suite(tmp_path, capsys):
    out = tmp_path / "my-support-suite"
    code = cli.main(["init", "--example", "support", "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "6 task(s) are active and ready to run" in printed
    assert f"callprobe validate --suite {out}" in printed
    suite = load_suite(out)
    assert len(suite.tasks) == 6
    assert not validate_suite(suite)


def test_init_with_example_github_issues_includes_license_and_provenance(tmp_path):
    out = tmp_path / "github-issues-suite"
    assert cli.main(["init", "--example", "github-issues", "--out", str(out)]) == 0
    assert (out / "LICENSE.md").read_text(encoding="utf-8") == CANONICAL["github-issues"]["LICENSE.md"].read_text(
        encoding="utf-8"
    )
    provenance = yaml.safe_load((out / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_sha256"]
    suite = load_suite(out)
    assert len(suite.tasks) == 18


def test_init_example_and_from_are_mutually_exclusive(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["init", "--example", "support", "--from-openapi", "x.yaml", "--out", str(tmp_path / "s")])
    assert "not allowed with" in capsys.readouterr().err


def test_init_unknown_example_is_rejected(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["init", "--example", "nope", "--out", str(tmp_path / "s")])
    err = capsys.readouterr().err
    assert "invalid choice" in err
    assert "support" in err and "github-issues" in err


def test_init_example_respects_overwrite_protection(tmp_path):
    out = tmp_path / "suite"
    assert cli.main(["init", "--example", "support", "--out", str(out)]) == 0
    assert cli.main(["init", "--example", "support", "--out", str(out)]) == 1
    assert cli.main(["init", "--example", "support", "--out", str(out), "--force"]) == 0


def test_existing_from_openapi_behavior_is_unaffected(tmp_path, capsys):
    out = tmp_path / "support-suite"
    document = REPO_ROOT / "examples" / "openapi" / "support-api.yaml"
    code = cli.main(["init", "--from-openapi", str(document), "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "no tasks are active yet" in printed
    suite = load_suite(out)
    assert suite.tasks == []
    assert not validate_suite(suite)


def test_example_output_path_can_be_pasted_into_shell(tmp_path, capsys):
    import shlex

    out = tmp_path / "suite with 'quotes' and $characters"
    assert cli.main(["init", "--example", "support", "--out", str(out)]) == 0
    command = next(line.strip() for line in capsys.readouterr().out.splitlines()
                   if line.strip().startswith("callprobe validate"))
    assert shlex.split(command) == ["callprobe", "validate", "--suite", str(out)]


def test_existing_tasks_are_preserved_without_partial_writes(tmp_path):
    out = tmp_path / "suite"
    out.mkdir()
    (out / "tasks.yaml").write_text("my existing tasks\n", encoding="utf-8")
    assert cli.main(["init", "--example", "support", "--out", str(out)]) == 1
    assert (out / "tasks.yaml").read_text(encoding="utf-8") == "my existing tasks\n"
    assert list(out.iterdir()) == [out / "tasks.yaml"]


@pytest.mark.parametrize("option", [["--tag", "issues"], ["--skip-unsupported"]])
def test_example_rejects_import_only_options(option, tmp_path):
    out = tmp_path / "suite"
    with pytest.raises(SystemExit) as exc:
        cli.main(["init", "--example", "support", "--out", str(out), *option])
    assert exc.value.code == 2
    assert not out.exists()
