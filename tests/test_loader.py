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
    ("suite.yaml", [], "suite.yaml: file must contain a YAML mapping"),
    ("tools.yaml", False, "tools.yaml: file must contain a YAML mapping"),
    ("tools.yaml", {"bundles": []}, "bundles must be a mapping"),
    ("tools.yaml", {"bundles": {"support": "oops"}}, "expected a list"),
    ("tools.yaml", {"bundles": {"support": [1]}}, "item 1 must be a mapping"),
    ("distractors.yaml", {"tools": {}}, "expected a list"),
    ("tasks.yaml", {"tasks": "oops"}, "expected a list"),
    ("tasks.yaml", {"tasks": [None]}, "item 1 must be a mapping"),
    ("tasks.yaml", {"tasks": [{1: "oops"}]}, "tasks.yaml: mapping keys must be strings"),
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


TASK = {
    "id": "t1",
    "category": "select",
    "bundle": "support",
    "messages": [{"role": "user", "content": "Look it up"}],
    "expect": {"type": "call", "tool": "lookup", "arg_checks": [{"path": "q", "op": "exists"}]},
}


def write_minimal_suite(directory, task=None):
    (directory / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"support": [TOOL]}}))
    (directory / "tasks.yaml").write_text(yaml.safe_dump({"tasks": [task or TASK]}))


def test_minimal_suite_loads(tmp_path):
    write_minimal_suite(tmp_path)
    assert [t.id for t in load_suite(tmp_path).tasks] == ["t1"]


@pytest.mark.parametrize("filename,text,diagnostic", [
    ("tasks.yaml", "tasks: []\ntasks: []\n", "tasks.yaml: duplicate key: 'tasks' at line 2"),
    ("tools.yaml", "bundles:\n  support:\n    - name: a\n      name: b\n", "tools.yaml: duplicate key: 'name' at line 4"),
    ("suite.yaml", "name: x\nversoin: 2\n", "suite.yaml: unknown field 'versoin' \\(did you mean 'version'\\?\\)"),
    ("distractors.yaml", "tool: []\n", "distractors.yaml: unknown field 'tool' \\(did you mean 'tools'\\?\\)"),
])
def test_suite_files_reject_duplicate_keys_and_unknown_fields(tmp_path, filename, text, diagnostic):
    write_minimal_suite(tmp_path)
    (tmp_path / filename).write_text(text)
    with pytest.raises(ValueError, match=diagnostic):
        load_suite(tmp_path)


@pytest.mark.parametrize("change,diagnostic", [
    (lambda t: t.update(exclude_distractor=["x"]),
     "tasks.yaml task t1: unknown field 'exclude_distractor' \\(did you mean 'exclude_distractors'\\?\\)"),
    (lambda t: t.update(depth=3), "tasks.yaml task t1: unknown field 'depth'"),
    (lambda t: t["expect"].update(also_acceptible=["x"], notes="n"),
     "tasks.yaml task t1 expect: unknown fields 'also_acceptible' \\(did you mean 'also_acceptable'\\?\\), 'notes'"),
    (lambda t: t["expect"]["arg_checks"][0].update(operator="eq"),
     "tasks.yaml task t1 expect.arg_checks item 1: unknown field 'operator'"),
])
def test_tasks_reject_unknown_fields_at_every_level(tmp_path, change, diagnostic):
    task = yaml.safe_load(yaml.safe_dump(TASK))
    change(task)
    write_minimal_suite(tmp_path, task)
    with pytest.raises(ValueError, match=diagnostic):
        load_suite(tmp_path)


def test_tool_entries_reject_unknown_fields(tmp_path):
    write_minimal_suite(tmp_path)
    (tmp_path / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"support": [{**TOOL, "parameter": {}}]}}))
    with pytest.raises(ValueError, match="tools.yaml bundle support item 1: unknown field 'parameter'"):
        load_suite(tmp_path)


def test_blank_and_comment_only_suite_files_still_load(tmp_path):
    write_minimal_suite(tmp_path)
    (tmp_path / "suite.yaml").write_text("# no settings yet\n")
    (tmp_path / "distractors.yaml").write_text("")
    assert load_suite(tmp_path).name == tmp_path.name


def test_unknown_field_is_a_cli_error_without_traceback(tmp_path, capsys):
    from callprobe.cli import main
    task = yaml.safe_load(yaml.safe_dump(TASK))
    task["exclude_distractor"] = ["x"]
    write_minimal_suite(tmp_path, task)
    assert main(["validate", "--suite", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "unknown field 'exclude_distractor'" in err and "Traceback" not in err
