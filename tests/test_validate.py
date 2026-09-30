"""Offline suite validation: schema soundness and expected-argument checks."""

import socket
from pathlib import Path

import pytest

import callprobe.validate as validate
from callprobe.cli import main
from callprobe.examples import generate_example_suite
from callprobe.loader import load_suite
from callprobe.models import Bundle, Expectation, Suite, Task, Tool
from callprobe.openapi import generate_openapi_suite, load_openapi_file

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "github-issues"


def _suite(bundle_tools, tasks=(), distractors=()):
    return Suite(
        name="s",
        bundles={"main": Bundle(name="main", tools=list(bundle_tools))},
        distractors=list(distractors),
        tasks=list(tasks),
    )


def _tool(name, parameters):
    return Tool(name=name, description="d", parameters=parameters)


def _call_task(task_id, tool, args=None):
    return Task(
        id=task_id,
        category="args",
        bundle="main",
        messages=[{"role": "user", "content": "hi"}],
        expect=Expectation(type="call", tool=tool, args=args or {}),
    )


VALID_SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}
INVALID_SCHEMA = {"type": "object", "properties": {"a": {"type": "integer", "minimum": "nope"}}}


def test_invalid_schema_on_unused_bundle_tool_is_reported():
    suite = _suite([_tool("used", VALID_SCHEMA), _tool("unused", INVALID_SCHEMA)])
    problems = validate.validate_suite(suite)
    assert any("unused" in p and "invalid schema" in p for p in problems)


def test_invalid_distractor_schema_is_reported():
    suite = _suite([_tool("used", VALID_SCHEMA)], distractors=[_tool("bad-distractor", INVALID_SCHEMA)])
    problems = validate.validate_suite(suite)
    assert any("bad-distractor" in p and "invalid schema" in p for p in problems)


def test_invalid_referenced_tool_schema_does_not_crash_and_skips_arg_checks():
    task = _call_task("t1", "broken", args={"a": 1})
    suite = _suite([_tool("broken", INVALID_SCHEMA)], tasks=[task])
    problems = validate.validate_suite(suite)  # must not raise
    assert any("broken" in p and "invalid schema" in p for p in problems)
    # only the one schema-level diagnostic; no per-task arg-check noise from
    # trying to validate against the broken schema
    assert not any(p.startswith("t1:") for p in problems)


def test_local_ref_resolves_and_validates():
    schema = {
        "type": "object",
        "$defs": {"pos": {"type": "integer", "minimum": 0}},
        "properties": {"a": {"$ref": "#/$defs/pos"}},
    }
    ok_task = _call_task("ok", "tool", args={"a": 5})
    bad_task = _call_task("bad", "tool", args={"a": -1})
    suite = _suite([_tool("tool", schema)], tasks=[ok_task, bad_task])
    problems = validate.validate_suite(suite)
    assert not any(p.startswith("ok:") for p in problems)
    assert any(p.startswith("bad:") and "-1" in p for p in problems)


def test_unresolved_external_ref_never_retrieves_and_reports_diagnostic(monkeypatch):
    attempted_connections = []
    def forbidden_socket(*args, **kwargs):
        attempted_connections.append(args)
        raise AssertionError("unexpected network access while validating offline")

    monkeypatch.setattr(socket, "create_connection", forbidden_socket)

    schema = {
        "type": "object",
        "properties": {"a": {"$ref": "https://example.invalid/schema.json"}},
    }
    task = _call_task("t1", "tool", args={"a": 1})
    suite = _suite([_tool("tool", schema)], tasks=[task])
    problems = validate.validate_suite(suite)  # must not raise, must not touch the network
    assert any(p.startswith("t1:") for p in problems)
    assert not any("example.invalid" in p for p in problems)
    assert not attempted_connections


def test_no_expectation_args_means_ref_is_never_claimed_resolved():
    schema = {
        "type": "object",
        "properties": {"a": {"$ref": "https://example.invalid/schema.json"}},
    }
    task = _call_task("t1", "tool")  # no args -> no reference is ever evaluated
    suite = _suite([_tool("tool", schema)], tasks=[task])
    assert validate.validate_suite(suite) == []


def test_valid_github_issues_example_suite_still_passes(tmp_path):
    files, result = generate_openapi_suite(
        load_openapi_file(EXAMPLE / "openapi.json"), "github-issues"
    )
    assert result.skipped == []
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "tasks.yaml").write_text(
        (EXAMPLE / "tasks.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    suite = load_suite(str(tmp_path))
    assert validate.validate_suite(suite) == []


@pytest.mark.parametrize("key", ["support", "github-issues"])
def test_valid_example_suites_still_pass(key, tmp_path):
    files, result = generate_example_suite(key, key)
    assert result.tools
    root = tmp_path / key
    root.mkdir()
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    suite = load_suite(root)
    assert validate.validate_suite(suite) == []


def test_cli_validate_returns_1_for_invalid_schema(tmp_path, capsys):
    root = tmp_path / "s"
    root.mkdir()
    (root / "tools.yaml").write_text(
        "bundles:\n  main:\n    - name: broken\n      description: d\n"
        "      parameters: {type: object, properties: {a: {type: integer, minimum: nope}}}\n",
        encoding="utf-8",
    )
    (root / "tasks.yaml").write_text(
        "name: s\ntasks:\n"
        "  - id: t1\n    category: args\n    bundle: main\n"
        "    messages: [{role: user, content: hi}]\n"
        "    expect: {type: call, tool: broken, args: {a: 1}}\n",
        encoding="utf-8",
    )
    assert main(["validate", "--suite", str(root)]) == 1
    out = capsys.readouterr().out
    assert "invalid schema" in out


def test_malformed_schema_diagnostic_uses_location_without_dumping_values():
    schema = {"type": "object", "properties": {"a": {"minimum": {"secret": "private-value"}}}}
    problems = validate.validate_suite(_suite([_tool("broken", schema)]))
    assert len(problems) == 1
    assert "properties.a.minimum" in problems[0]
    assert "private-value" not in problems[0]


def test_recursive_reference_failure_is_a_diagnostic_not_a_traceback():
    schema = {"type": "object", "properties": {"a": {"$ref": "#/$defs/loop"}},
              "$defs": {"loop": {"$ref": "#/$defs/loop"}}}
    problems = validate.validate_suite(_suite([_tool("loop", schema)], [_call_task("t", "loop", {"a": 1})]))
    assert any("cannot validate offline" in problem for problem in problems)


@pytest.mark.parametrize("query,conflict", [
    ({"from": "dana@example.invalid"}, True),
    ({"from": "dana@example.invalid", "subject_contains": "invoice"}, False),
])
def test_exact_parent_expectation_cannot_conflict_with_descendant_check(query, conflict):
    from callprobe.models import ArgCheck
    schema = {"type": "object", "properties": {"query": {"type": "object", "properties": {
        "from": {"type": "string"}, "subject_contains": {"type": "string"}}}}}
    task = _call_task("search", "search", {"query": query})
    task.expect.arg_checks = [ArgCheck(path="query.subject_contains", op="matches", value="invoice")]
    problems = validate.validate_suite(_suite([_tool("search", schema)], [task]))
    assert any("conflicts with check query.subject_contains" in item for item in problems) == conflict


def test_exact_scalar_and_range_check_conflict_is_reported():
    from callprobe.models import ArgCheck
    task = _call_task("t", "tool", {"a": 1})
    task.expect.arg_checks = [ArgCheck(path="a", op="gte", value=2)]
    assert any("conflicts with check a gte" in item for item in
               validate.validate_suite(_suite([_tool("tool", VALID_SCHEMA)], [task])))
