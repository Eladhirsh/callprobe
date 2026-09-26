"""Reject ambiguous tool contracts before any model request."""

import pytest
import yaml

from callprobe.loader import load_suite


TOOL = {"name": "lookup", "description": "Lookup", "parameters": {"type": "object"}}


@pytest.mark.parametrize("duplicate_in", ["bundle", "distractors"])
def test_duplicate_tool_names_are_rejected(tmp_path, duplicate_in):
    bundle_tools = [TOOL, TOOL] if duplicate_in == "bundle" else [TOOL]
    distractors = [TOOL, TOOL] if duplicate_in == "distractors" else []
    (tmp_path / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"support": bundle_tools}}))
    (tmp_path / "distractors.yaml").write_text(yaml.safe_dump({"tools": distractors}))
    with pytest.raises(ValueError, match="duplicate tool name: lookup"):
        load_suite(tmp_path)


def test_tool_names_may_repeat_across_separate_bundles_and_distractor_pool(tmp_path):
    (tmp_path / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"a": [TOOL], "b": [TOOL]}}))
    (tmp_path / "distractors.yaml").write_text(yaml.safe_dump({"tools": [TOOL]}))
    suite = load_suite(tmp_path)
    assert len(suite.bundles) == 2
    assert len(suite.distractors) == 1


@pytest.mark.parametrize("filename,document,diagnostic", [
    ("suite.yaml", [], "suite.yaml: expected a YAML mapping"),
    ("tools.yaml", False, "tools.yaml: expected a YAML mapping"),
    ("tools.yaml", {"bundles": []}, "bundles must be a mapping"),
    ("tools.yaml", {"bundles": {"support": "oops"}}, "expected a list"),
    ("tools.yaml", {"bundles": {"support": [1]}}, "item 1 must be a mapping"),
    ("distractors.yaml", {"tools": {}}, "expected a list"),
    ("tasks.yaml", {"tasks": "oops"}, "expected a list"),
    ("tasks.yaml", {"tasks": [None]}, "item 1 must be a mapping"),
    ("tasks.yaml", {"tasks": [{1: "oops"}]}, "mapping with string keys"),
])
def test_malformed_suite_yaml_has_actionable_error(tmp_path, filename, document, diagnostic):
    (tmp_path / filename).write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match=diagnostic):
        load_suite(tmp_path)


def test_invalid_suite_yaml_is_cli_error_without_traceback(tmp_path, capsys):
    from callprobe.cli import main
    (tmp_path / "tasks.yaml").write_text("tasks: wrong-shape")
    assert main(["validate", "--suite", str(tmp_path)]) == 2
    assert "tasks.yaml tasks: expected a list" in capsys.readouterr().err
