"""Tests for `callprobe explain`: shape-hint helpers, case classification,
run-level assembly, and the CLI, using the archived GitHub issues example
as a realistic fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.explain import (
    build_shape_hint,
    check_suite_matches,
    classify_case,
    explain_run,
    render_explain_text,
)
from callprobe.loader import load_suite
from callprobe.models import Call, Run, RunConfig, Task, TaskResult, Tool
from callprobe.openapi import generate_openapi_suite, load_openapi_file

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "github-issues"


@pytest.fixture(scope="module")
def github_suite_dir(tmp_path_factory):
    """Materialize the archived GitHub issues example the same way the
    README instructs: import the pinned OpenAPI document, drop in the
    example's real tasks.yaml.
    """
    root = tmp_path_factory.mktemp("github-issues-suite")
    files, result = generate_openapi_suite(
        load_openapi_file(EXAMPLE / "openapi.json"), "github-issues"
    )
    assert result.skipped == []
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    (root / "tasks.yaml").write_text(
        (EXAMPLE / "tasks.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


@pytest.fixture(scope="module")
def github_suite(github_suite_dir):
    return load_suite(str(github_suite_dir))


def _config(suite, **kwargs):
    base = dict(
        model="stub-model",
        endpoint="http://fake",
        suite="github-issues-suite",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=2048,
        suite_hash=suite.hash,
        suite_name=suite.name,
        suite_version=suite.version,
    )
    base.update(kwargs)
    return RunConfig(**base)


def _base_result(task, **kwargs):
    base = dict(
        task_id=task.id,
        category=task.category,
        model="stub-model",
        pad=0,
        repeat=0,
        selection_ok=False,
        schema_ok=False,
        args_ok=False,
        success=False,
    )
    base.update(kwargs)
    return TaskResult(**base)


def _tasks(suite):
    return {t.id: t for t in suite.tasks}


def _tool(suite, name):
    return suite.bundles["main"].by_name(name)


# --------------------------------------------------------- shape hints


def test_nested_move_hint_moves_flat_keys_under_missing_path_group(github_suite):
    tool = _tool(github_suite, "issues_get_cf0062ad")
    flat = {"owner": "octo-org", "repo": "widget", "issue_number": 42}
    hint = build_shape_hint(tool, flat)
    assert hint["kind"] == "nested_move"
    assert hint["moved"] == {"owner": "path", "repo": "path", "issue_number": "path"}
    assert hint["candidate_arguments"] == {
        "path": {"owner": "octo-org", "repo": "widget", "issue_number": 42}
    }
    # the input dict itself must never be mutated
    assert flat == {"owner": "octo-org", "repo": "widget", "issue_number": 42}


def test_scalar_wrap_hint_wraps_a_flat_body_string(github_suite):
    tool = _tool(github_suite, "issues_create-comment_27544d18")
    original = {
        "path": {"owner": "octo-org", "repo": "widget", "issue_number": 101},
        "body": "LGTM!",
    }
    hint = build_shape_hint(tool, original)
    assert hint["kind"] == "scalar_wrap"
    assert hint["wrapped"] == {"body": "body"}
    assert hint["candidate_arguments"]["body"] == {"body": "LGTM!"}
    assert hint["candidate_arguments"]["path"] == original["path"]
    assert original["body"] == "LGTM!"  # untouched


def test_move_and_wrap_combine_when_both_are_needed(github_suite):
    tool = _tool(github_suite, "issues_create-comment_27544d18")
    flat = {"owner": "octo-org", "repo": "widget", "issue_number": 101, "body": "LGTM!"}
    hint = build_shape_hint(tool, flat)
    assert hint["kind"] == "nested_move+scalar_wrap"
    assert hint["candidate_arguments"] == {
        "path": {"owner": "octo-org", "repo": "widget", "issue_number": 101},
        "body": {"body": "LGTM!"},
    }


def test_no_hint_when_arguments_already_valid(github_suite):
    tool = _tool(github_suite, "issues_get_cf0062ad")
    good = {"path": {"owner": "octo-org", "repo": "widget", "issue_number": 42}}
    assert build_shape_hint(tool, good) is None


def test_no_hint_on_ambiguous_collision():
    # "id" exists in both candidate groups, so no unambiguous mapping exists.
    tool = Tool(
        name="ambiguous",
        description="",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "object", "properties": {"id": {"type": "string"}},
                          "additionalProperties": False},
                "query": {"type": "object", "properties": {"id": {"type": "string"}},
                          "additionalProperties": False},
            },
            "additionalProperties": False,
        },
    )
    assert build_shape_hint(tool, {"id": "42"}) is None


def test_no_hint_when_key_matches_no_missing_group():
    tool = Tool(
        name="one-group",
        description="",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "object", "properties": {"owner": {"type": "string"}},
                          "additionalProperties": False},
            },
            "additionalProperties": False,
        },
    )
    assert build_shape_hint(tool, {"unrelated": "value"}) is None


def test_no_hint_when_key_is_already_a_valid_root_property():
    # "path" is a legitimate top-level property already, not a stray key,
    # even though it does not itself validate (it's a string, not an object).
    tool = Tool(
        name="already-present",
        description="",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "object",
                          "properties": {"owner": {"type": "string"}, "id": {"type": "string"}},
                          "additionalProperties": False},
            },
            "additionalProperties": False,
        },
    )
    # "path" present as a root key, but wrong shape; "id" is not one of
    # path's declared properties as a loose key here since path isn't missing.
    assert build_shape_hint(tool, {"path": "not-an-object"}) is None


@pytest.mark.parametrize("schema_extra", [
    {"oneOf": [{"type": "object"}]},
    {"anyOf": [{"type": "object"}]},
    {"allOf": [{"type": "object"}]},
    {"$ref": "#/components/schemas/Thing"},
    {"patternProperties": {"^x-": {"type": "string"}}},
    {"additionalProperties": {"type": "string"}},
])
def test_no_hint_on_unsupported_schema_constructs(schema_extra):
    tool = Tool(
        name="combinator",
        description="",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "object", "properties": {"owner": {"type": "string"}},
                          "additionalProperties": False, **schema_extra},
            },
            "additionalProperties": False,
        },
    )
    assert build_shape_hint(tool, {"owner": "octo-org"}) is None


def test_no_hint_when_top_schema_itself_uses_a_combinator():
    tool = Tool(
        name="root-combinator",
        description="",
        parameters={
            "oneOf": [
                {"type": "object", "properties": {"path": {"type": "object", "properties": {}}}},
            ]
        },
    )
    assert build_shape_hint(tool, {"owner": "octo-org"}) is None


# ------------------------------------------------------------ classify_case


def test_classify_request_error_short_circuits(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task, error="connection refused")
    assert classify_case(task, github_suite.bundles["main"], result) == ["request_error"]


def test_classify_truncation_before_any_call(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task, truncated=True)
    assert classify_case(task, github_suite.bundles["main"], result) == ["truncated", "no_call"]


def test_classify_no_call(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task)
    assert classify_case(task, github_suite.bundles["main"], result) == ["no_call"]


def test_classify_unexpected_call_on_abstain_task(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["missing-repository"]
    call = Call(name="issues_get_cf0062ad", arguments={"path": {}})
    result = _base_result(task, called=call.name, calls=[call])
    assert classify_case(task, github_suite.bundles["main"], result) == ["unexpected_call"]


def test_classify_multiple_calls(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    calls = [
        Call(name="issues_get_cf0062ad", arguments={"path": {"owner": "o", "repo": "r",
                                                              "issue_number": 1}}),
        Call(name="issues_get_cf0062ad", arguments={"path": {"owner": "o", "repo": "r",
                                                              "issue_number": 1}}),
    ]
    result = _base_result(task, called=calls[0].name, calls=calls,
                          selection_ok=True, schema_ok=True, args_ok=True)
    assert "multiple_calls" in classify_case(task, github_suite.bundles["main"], result)


def test_classify_wrong_tool(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name="issues_list-comments_e6abc434", arguments={"path": {"owner": "o", "repo": "r",
                                                                          "issue_number": 1}})
    # the wrong tool's schema happens to validate here too, isolating the
    # wrong-tool signal from a coincidental schema/argument failure.
    result = _base_result(task, called=call.name, calls=[call], selection_ok=False,
                          schema_ok=True, args_ok=True)
    assert classify_case(task, github_suite.bundles["main"], result) == ["wrong_tool"]


def test_classify_malformed_arguments(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name="issues_get_cf0062ad", raw_arguments="{not json",
               parse_error="Expecting property name enclosed in double quotes")
    result = _base_result(task, called=call.name, calls=[call], selection_ok=True)
    assert classify_case(task, github_suite.bundles["main"], result) == ["malformed_arguments"]


def test_classify_schema_and_argument_value(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name="issues_get_cf0062ad", arguments={"owner": "octo-org", "repo": "widget",
                                                        "issue_number": 42})
    result = _base_result(task, called=call.name, calls=[call], selection_ok=True,
                          schema_ok=False, args_ok=False)
    assert classify_case(task, github_suite.bundles["main"], result) == ["schema", "argument_value"]


def test_classify_legacy_record_trusts_recorded_flags(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task, called="issues_get_cf0062ad", calls=[],
                          selection_ok=True, schema_ok=False, args_ok=False)
    assert classify_case(task, github_suite.bundles["main"], result) == ["schema", "argument_value"]


def test_classify_unresolved_tool_name_stops_at_wrong_tool(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name="not_a_real_tool", arguments={"x": 1})
    result = _base_result(task, called=call.name, calls=[call], selection_ok=False)
    assert classify_case(task, github_suite.bundles["main"], result) == ["wrong_tool"]


# ---------------------------------------------------------- case-report detail


def test_case_report_request_error_shows_no_call_evidence(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task, error="connection refused", failures=["request failed: connection refused"])
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    assert case["diagnostics"] == ["request_error"]
    assert case["call_evidence"] == "none"
    assert case["calls"] == []
    assert case["reasons"] == ["request failed: connection refused"]


def test_case_report_dumps_every_call_including_malformed_raw_arguments(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    good_call = Call(id="a", name=task.expect.tool,
                     arguments={"path": {"owner": "o", "repo": "r", "issue_number": 1}},
                     raw_arguments='{"path": ...}')
    bad_call = Call(id="b", name=task.expect.tool, raw_arguments="{not json",
                    parse_error="Expecting property name")
    result = _base_result(task, called=good_call.name, calls=[good_call, bad_call],
                          selection_ok=True)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    assert case["call_evidence"] == "full"
    assert len(case["calls"]) == 2
    assert case["calls"][0]["arguments"] == good_call.arguments
    assert case["calls"][1]["parse_error"] == "Expecting property name"
    assert case["calls"][1]["raw_arguments"] == "{not json"
    # the scored (first-matching-name) call already has valid arguments,
    # so there is nothing for a shape hint to fix
    assert "shape_hint" not in case


def test_case_report_includes_the_user_prompts(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    expected_prompts = [m["content"] for m in task.messages if m["role"] == "user"]
    assert case["prompts"] == expected_prompts
    assert case["prompts"]  # never empty for this fixture's tasks


def test_case_report_shows_argument_assertions_separately_from_shape_hint(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["comment-body-punctuation"]
    call = Call(name=task.expect.tool,
               arguments={"path": {"owner": "octo-org", "repo": "widget", "issue_number": 101},
                         "body": "LGTM!"})
    result = _base_result(task, called=call.name, calls=[call], selection_ok=True,
                          schema_ok=False, args_ok=False)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    assertions = {a["path"]: a for a in case["argument_assertions"]}
    assert assertions["body"]["ok"] is False
    assert assertions["body"]["expected"] == task.expect.args["body"]
    assert case["shape_hint"]["kind"] == "scalar_wrap"
    # the assertion is not rewritten to match the hint's candidate
    assert assertions["body"]["actual"] == "LGTM!"


# --------------------------------------------------------------- explain_run


def test_hash_mismatch_is_a_clear_error(github_suite):
    run = Run(config=_config(github_suite, suite_hash="not-the-real-hash"), started_at="now")
    with pytest.raises(ValueError, match="suite hash mismatch"):
        check_suite_matches(run, github_suite)


def test_missing_hash_is_a_clear_error(github_suite):
    run = Run(config=_config(github_suite, suite_hash=None), started_at="now")
    with pytest.raises(ValueError, match="no recorded suite hash"):
        check_suite_matches(run, github_suite)


def test_unknown_task_filter_is_a_clear_error(github_suite):
    run = Run(config=_config(github_suite), started_at="now")
    with pytest.raises(ValueError, match="unknown task"):
        explain_run(run, github_suite, task_id="does-not-exist")


def test_task_filter_reports_pass_with_no_failures(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    good = _base_result(task, called=task.expect.tool,
                        calls=[Call(name=task.expect.tool,
                                    arguments={"path": {"owner": "octo-org", "repo": "widget",
                                                        "issue_number": 42}})],
                        selection_ok=True, schema_ok=True, args_ok=True, success=True)
    run = Run(config=_config(github_suite), started_at="now", results=[good])
    report = explain_run(run, github_suite, task_id="get-issue-details")
    assert report["task_passed"] is True
    assert report["failed_cases"] == 0
    assert report["cases"] == []
    assert "passed" in render_explain_text(report)


def test_task_filter_with_no_results_is_reported_not_erased(github_suite):
    run = Run(config=_config(github_suite), started_at="now", results=[])
    report = explain_run(run, github_suite, task_id="get-issue-details")
    assert report["task_has_results"] is False
    assert "no recorded results" in render_explain_text(report)


def test_task_filter_includes_every_pad_and_repeat(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    others = tasks["post-comment-simple"]
    cases = [
        _base_result(task, pad=0, repeat=0),
        _base_result(task, pad=0, repeat=1),
        _base_result(task, pad=8, repeat=0),
        _base_result(others, pad=0, repeat=0),  # must be excluded by the filter
    ]
    run = Run(config=_config(github_suite), started_at="now", results=cases)
    report = explain_run(run, github_suite, task_id="get-issue-details")
    assert report["scored_cases"] == 3
    assert {(c["pad"], c["repeat"]) for c in report["cases"]} == {(0, 0), (0, 1), (8, 0)}


def test_success_report_when_everything_passes(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    good = _base_result(task, called=task.expect.tool,
                        calls=[Call(name=task.expect.tool,
                                    arguments={"path": {"owner": "octo-org", "repo": "widget",
                                                        "issue_number": 42}})],
                        selection_ok=True, schema_ok=True, args_ok=True, success=True)
    run = Run(config=_config(github_suite), started_at="now", results=[good])
    report = explain_run(run, github_suite)
    assert report["failed_cases"] == 0
    assert "no failures" in render_explain_text(report)


def test_shape_hint_surfaces_on_a_failing_nested_move_case(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    flat_call = Call(
        id="call_1", name=task.expect.tool,
        arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42},
        raw_arguments='{"owner":"octo-org","repo":"widget","issue_number":42}',
    )
    result = _base_result(task, called=task.expect.tool, calls=[flat_call],
                          selection_ok=True, schema_ok=False, args_ok=False,
                          failures=["schema: (root): 'path' is a required property"])
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    assert case["diagnostics"] == ["schema", "argument_value"]
    assert case["shape_hint"]["kind"] == "nested_move"
    assert case["shape_hint"]["candidate_arguments"] == {
        "path": {"owner": "octo-org", "repo": "widget", "issue_number": 42}
    }
    assert "not executed" in case["shape_hint"]["advisory"]
    # the original recorded call is untouched in the report
    assert case["calls"][0]["arguments"] == flat_call.arguments


def test_no_shape_hint_when_selection_is_wrong(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name="issues_list-comments_e6abc434",
               arguments={"path": {"owner": "octo-org", "repo": "widget", "issue_number": 42}})
    result = _base_result(task, called=call.name, calls=[call], selection_ok=False)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    assert "shape_hint" not in report["cases"][0]


def test_legacy_case_has_no_calls_and_no_shape_hint(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    result = _base_result(task, called=task.expect.tool, calls=[],
                          selection_ok=True, schema_ok=False, args_ok=False,
                          failures=["schema: (root): 'path' is a required property"])
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    case = report["cases"][0]
    assert case["call_evidence"] == "legacy"
    assert case["calls"] is None
    assert "shape_hint" not in case
    assert "unavailable" in case["legacy_note"]
    assert "unavailable" in render_explain_text(report)


def test_input_run_and_suite_are_not_mutated(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    flat_call = Call(name=task.expect.tool,
                     arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42})
    result = _base_result(task, called=task.expect.tool, calls=[flat_call],
                          selection_ok=True, schema_ok=False, args_ok=False)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    before_run = run.model_dump_json()
    before_suite = github_suite.model_dump_json()
    explain_run(run, github_suite)
    assert run.model_dump_json() == before_run
    assert github_suite.model_dump_json() == before_suite


def test_diagnostic_counts_are_case_counts_not_reason_counts(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    call = Call(name=task.expect.tool, arguments={"owner": "o"})
    result = _base_result(task, called=task.expect.tool, calls=[call], selection_ok=True,
                          schema_ok=False, args_ok=False,
                          failures=["schema: (root): a", "schema: (root): b", "owner expected 'x', got 'o'"])
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    report = explain_run(run, github_suite)
    assert report["diagnostic_counts"]["schema"] == 1
    assert report["diagnostic_counts"]["argument_value"] == 1


# ---------------------------------------------------------------------- CLI


def _write_run(path, run):
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")


def test_cli_json_output_is_valid_and_structured(tmp_path, github_suite, github_suite_dir, capsys):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    flat_call = Call(name=task.expect.tool,
                     arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42})
    result = _base_result(task, called=task.expect.tool, calls=[flat_call],
                          selection_ok=True, schema_ok=False, args_ok=False,
                          failures=["schema: (root): 'path' is a required property"])
    passing = _base_result(tasks["post-comment-simple"],
                           called="issues_create-comment_27544d18",
                           calls=[Call(name="issues_create-comment_27544d18",
                                      arguments={"path": {"owner": "octo-org", "repo": "widget",
                                                          "issue_number": 42},
                                                "body": {"body": "ok"}})],
                           selection_ok=True, schema_ok=True, args_ok=True, success=True)
    run = Run(config=_config(github_suite), started_at="now", finished_at="later",
              results=[result, passing])
    results_path = tmp_path / "run.json"
    _write_run(results_path, run)

    code = cli.main(["explain", str(results_path), "--suite", str(github_suite_dir),
                     "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    report = json.loads(out)  # must be valid, parseable JSON on stdout
    assert report["failed_cases"] == 1
    assert report["cases"][0]["task_id"] == "get-issue-details"
    assert report["cases"][0]["shape_hint"]["kind"] == "nested_move"


def test_cli_text_output_and_input_file_immutability(tmp_path, github_suite, github_suite_dir, capsys):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    flat_call = Call(name=task.expect.tool,
                     arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42})
    result = _base_result(task, called=task.expect.tool, calls=[flat_call],
                          selection_ok=True, schema_ok=False, args_ok=False)
    run = Run(config=_config(github_suite), started_at="now", results=[result])
    results_path = tmp_path / "run.json"
    _write_run(results_path, run)
    before = results_path.read_bytes()
    before_suite_files = {p.name: p.read_bytes() for p in github_suite_dir.iterdir()}

    code = cli.main(["explain", str(results_path), "--suite", str(github_suite_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "get-issue-details" in out
    assert "nested_move" in out
    assert "not executed" in out

    assert results_path.read_bytes() == before
    assert {p.name: p.read_bytes() for p in github_suite_dir.iterdir()} == before_suite_files


def test_cli_rejects_hash_mismatch(tmp_path, github_suite, github_suite_dir, capsys):
    run = Run(config=_config(github_suite, suite_hash="wrong"), started_at="now")
    results_path = tmp_path / "run.json"
    _write_run(results_path, run)

    code = cli.main(["explain", str(results_path), "--suite", str(github_suite_dir)])
    err = capsys.readouterr().err
    assert code == 2
    assert "suite hash mismatch" in err


def test_cli_task_filter(tmp_path, github_suite, github_suite_dir, capsys):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    flat_call = Call(name=task.expect.tool,
                     arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42})
    result = _base_result(task, called=task.expect.tool, calls=[flat_call],
                          selection_ok=True, schema_ok=False, args_ok=False)
    other = _base_result(tasks["post-comment-simple"])
    run = Run(config=_config(github_suite), started_at="now", results=[result, other])
    results_path = tmp_path / "run.json"
    _write_run(results_path, run)

    code = cli.main(["explain", str(results_path), "--suite", str(github_suite_dir),
                     "--task", "get-issue-details", "--format", "json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["scored_cases"] == 1
    assert all(c["task_id"] == "get-issue-details" for c in report["cases"])


def test_cli_unknown_task_is_an_error(tmp_path, github_suite, github_suite_dir, capsys):
    run = Run(config=_config(github_suite), started_at="now")
    results_path = tmp_path / "run.json"
    _write_run(results_path, run)

    code = cli.main(["explain", str(results_path), "--suite", str(github_suite_dir), "--task", "nope"])
    err = capsys.readouterr().err
    assert code == 2
    assert "unknown task" in err


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_recipe_explains_the_recorded_github_run(tmp_path, capsys):
    """The exact copy/pastable recipe from the README: regenerate the
    example suite and explain the committed Qwen3 8B run against it.
    """
    suite_dir = tmp_path / "github-issues-suite"
    code = cli.main([
        "init", "--from-openapi", str(REPO_ROOT / "examples" / "github-issues" / "openapi.json"),
        "--out", str(suite_dir),
    ])
    assert code == 0
    capsys.readouterr()
    (suite_dir / "tasks.yaml").write_text(
        (REPO_ROOT / "examples" / "github-issues" / "tasks.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    results_path = REPO_ROOT / "results" / "github-issues" / "qwen3-8b.json"
    before = results_path.read_bytes()
    code = cli.main(["explain", str(results_path), "--suite", str(suite_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "get-issue-details" in out
    assert results_path.read_bytes() == before  # the committed result is never touched


@pytest.mark.parametrize('model,failed', [('qwen2.5-7b', 13), ('qwen3-8b', 7)])
def test_archived_runs_both_formats(model, failed, github_suite_dir, capsys):
    source = REPO_ROOT / 'results' / 'github-issues' / f'{model}.json'
    before = source.read_bytes()
    args = ['explain', str(source), '--suite', str(github_suite_dir)]
    assert cli.main(args) == 0
    rendered = capsys.readouterr().out
    assert 'shape hint' in rendered
    assert cli.main(args + ['--format', 'json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['failed_cases'] == failed
    assert report['total_cases'] == report['scored_cases'] == 18
    assert report['request_errors'] == 0
    assert source.read_bytes() == before


@pytest.mark.parametrize('reference', ['$ref', '$dynamicRef'])
@pytest.mark.parametrize('container', ['prefixItems', 'contains'])
def test_full_report_never_retrieves_nested_references(reference, container, github_suite, monkeypatch):
    import socket
    import callprobe.explain as diagnostics
    from referencing import Registry

    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(args)
        raise AssertionError('unexpected reference retrieval or network access')

    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(diagnostics, '_NO_RETRIEVAL_REGISTRY', Registry(retrieve=forbidden))
    suite = github_suite.model_copy(deep=True)
    task = _tasks(suite)['get-issue-details']
    tool = _tool(suite, task.expect.tool)
    nested = {reference: 'https://example.invalid/schema'}
    tool.parameters = {'type': 'object', 'properties': {
        'items': {'type': 'array', container: [nested] if container == 'prefixItems' else nested}}}
    result = _base_result(task, called=tool.name, selection_ok=True,
                          calls=[Call(name=tool.name, arguments={'items': [1]})])
    run = Run(config=_config(suite), started_at='now', results=[result])
    case = explain_run(run, suite)['cases'][0]
    assert 'schema_diagnostics_limited' in case
    assert 'shape_hint' not in case
    assert attempts == []


@pytest.mark.parametrize('kind', ['truncated', 'multiple', 'unexpected'])
def test_full_report_suppresses_ineligible_hints(kind, github_suite):
    task = _tasks(github_suite)['get-issue-details' if kind != 'unexpected' else 'missing-repository']
    name = _tasks(github_suite)['get-issue-details'].expect.tool
    call = Call(name=name, arguments={'owner': 'octo-org', 'repo': 'widget', 'issue_number': 42})
    result = _base_result(task, called=name, selection_ok=True,
                          truncated=kind == 'truncated', calls=[call] * (2 if kind == 'multiple' else 1))
    run = Run(config=_config(github_suite), started_at='now', results=[result])
    case = explain_run(run, github_suite)['cases'][0]
    assert 'shape_hint' not in case
    assert len(case['calls']) == len(result.calls)


def test_invalid_schema_is_reported_without_a_crash(github_suite):
    suite = github_suite.model_copy(deep=True)
    task = _tasks(suite)['get-issue-details']
    _tool(suite, task.expect.tool).parameters = {'type': 'object', 'required': 'invalid'}
    result = _base_result(task, called=task.expect.tool, selection_ok=True,
                          calls=[Call(name=task.expect.tool, arguments={})])
    run = Run(config=_config(suite), started_at='now', results=[result])
    case = explain_run(run, suite)['cases'][0]
    assert 'schema_diagnostics_limited' in case
    assert 'shape_hint' not in case


def test_unknown_result_ids_are_rejected_and_empty_runs_are_not_passed(github_suite):
    run = Run(config=_config(github_suite), started_at='now')
    assert 'no recorded results' in render_explain_text(explain_run(run, github_suite))
    task = _tasks(github_suite)['get-issue-details']
    result = _base_result(task).model_copy(update={'task_id': 'not-in-suite'})
    run.results = [result]
    with pytest.raises(ValueError, match='not defined in this suite'):
        explain_run(run, github_suite)


def test_explain_works_on_a_targeted_debug_run_with_the_original_suite_hash(github_suite):
    task = _tasks(github_suite)['get-issue-details']
    config = _config(github_suite, task_ids=[t.id for t in github_suite.tasks],
                      selected_task_ids=[task.id])
    run = Run(config=config, started_at='now', results=[_base_result(task, success=True,
              selection_ok=True, schema_ok=True, args_ok=True)])
    report = explain_run(run, github_suite)
    assert report['total_cases'] == 1


def test_request_errors_are_not_scored_cases(github_suite):
    task = _tasks(github_suite)['get-issue-details']
    run = Run(config=_config(github_suite), started_at='now',
              results=[_base_result(task, error='timeout')])
    report = explain_run(run, github_suite)
    assert (report['total_cases'], report['scored_cases'], report['request_errors']) == (1, 0, 1)
    assert report['cases'][0]['diagnostics'] == ['request_error']


def test_permissive_root_is_not_relocated(github_suite):
    tool = _tool(github_suite, _tasks(github_suite)['get-issue-details'].expect.tool).model_copy(deep=True)
    tool.parameters['additionalProperties'] = True
    assert build_shape_hint(tool, {'owner': 'octo-org', 'repo': 'widget', 'issue_number': 42}) is None
