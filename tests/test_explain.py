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


def _flat_failure(task, **kwargs):
    call = Call(name=task.expect.tool,
                arguments={"owner": "octo-org", "repo": "widget", "issue_number": 42})
    return _base_result(task, called=task.expect.tool, calls=[call], selection_ok=True,
                        schema_ok=False, args_ok=False, **kwargs)


def test_shape_summary_counts_observations_separately_from_unique_tasks(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [_flat_failure(task, pad=0, repeat=0), _flat_failure(task, pad=0, repeat=1),
               _flat_failure(task, pad=8, repeat=0)]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    report = explain_run(run, github_suite)
    assert report["argument_shape_summary"] == {
        "affected_observations": 3, "unique_tasks": 1, "by_kind": {"nested_move": 3},
    }
    text = render_explain_text(report)
    assert "3 observation(s) across 1 task(s)" in text
    assert "adapter" in text and "rerun with the same suite" in text
    assert "nothing was repaired" in text


def test_shape_summary_is_empty_without_hints_and_ignores_plain_schema_failures(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    unhinted = _base_result(task, called=task.expect.tool,
                            calls=[Call(name=task.expect.tool, arguments={"owner": "o"})],
                            selection_ok=True, schema_ok=False, args_ok=False,
                            failures=["schema: (root): 'path' is a required property"])
    run = Run(config=_config(github_suite), started_at="now", results=[unhinted])
    report = explain_run(run, github_suite)
    assert "shape_hint" not in report["cases"][0]
    assert report["argument_shape_summary"] == {
        "affected_observations": 0, "unique_tasks": 0, "by_kind": {},
    }
    assert "argument shape hints" not in render_explain_text(report)


def test_shape_summary_respects_task_filter(github_suite):
    tasks = _tasks(github_suite)
    task = tasks["get-issue-details"]
    other = tasks["post-comment-simple"]
    other_call = Call(name=other.expect.tool, arguments={
        "path": {"owner": "octo-org", "repo": "widget", "issue_number": 101},
        "body": "LGTM!"})
    other_result = _base_result(other, called=other.expect.tool, calls=[other_call],
                                selection_ok=True, schema_ok=False, args_ok=False)
    results = [_flat_failure(task), _flat_failure(task, repeat=1), other_result]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    assert explain_run(run, github_suite)["argument_shape_summary"] == {
        "affected_observations": 3, "unique_tasks": 2,
        "by_kind": {"nested_move": 2, "scalar_wrap": 1},
    }
    scoped = explain_run(run, github_suite, task_id="get-issue-details")["argument_shape_summary"]
    assert scoped["affected_observations"] == 2
    assert scoped["unique_tasks"] == 1


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


@pytest.mark.parametrize('saved_success', [False, True])
def test_empty_request_error_cannot_be_explained_as_model_output(github_suite, saved_success):
    task = _tasks(github_suite)['get-issue-details']
    result = _base_result(task, error='', success=saved_success,
                          response_text='{"name": "issues_get_cf0062ad", "arguments": {}}')
    run = Run(config=_config(github_suite), started_at='now', results=[result])
    original = run.model_dump()
    report = explain_run(run, github_suite)
    assert (report['total_cases'], report['scored_cases'], report['request_errors']) == (1, 0, 1)
    assert len(report['cases']) == 1
    case = report['cases'][0]
    assert case['diagnostics'] == ['request_error']
    assert case['call_evidence'] == 'none'
    assert case['calls'] == []
    assert 'shape_hint' not in case
    assert run.model_dump() == original


def test_permissive_root_is_not_relocated(github_suite):
    tool = _tool(github_suite, _tasks(github_suite)['get-issue-details'].expect.tool).model_copy(deep=True)
    tool.parameters['additionalProperties'] = True
    assert build_shape_hint(tool, {'owner': 'octo-org', 'repo': 'widget', 'issue_number': 42}) is None


# ------------------------------------------- tool JSON in assistant content

_GET = 'issues_get_cf0062ad'
_ARGS = {"path": {"owner": "octo-org", "repo": "widget", "issue_number": 42}}


def _content_case(suite, text, task_id='get-issue-details', **kwargs):
    task = _tasks(suite)[task_id]
    result = _base_result(task, response_text=text, **kwargs)
    run = Run(config=_config(suite), started_at='now', results=[result])
    return explain_run(run, suite), result


@pytest.mark.parametrize('payload', [
    {"name": _GET, "arguments": _ARGS},
    {"function": {"name": _GET, "arguments": _ARGS}},
    {"type": "function", "function": {"name": _GET, "arguments": json.dumps(_ARGS)}},
    [{"name": _GET, "arguments": _ARGS}, {"function": {"name": _GET, "arguments": {}}}],
    {"type": "function", "function": {"name": _GET, "description": "d", "parameters": {"type": "object"}}},
])
def test_content_tool_json_matches_exact_forms(github_suite, payload):
    report, result = _content_case(github_suite, "  " + json.dumps(payload) + "\n",
                                   failures=["no tool call"])
    case = report['cases'][0]
    assert case['diagnostics'] == ['no_call']
    assert case['content_tool_json']['tools'] == [_GET]
    advisory = case['content_tool_json']['advisory']
    assert 'not the provider' in advisory and 'adapter' in advisory
    assert 'does not establish the root cause' in advisory
    assert case['response_text'] == result.response_text
    assert case['reasons'] == ['no tool call']
    assert 'shape_hint' not in case
    assert 'tool JSON in assistant text' in render_explain_text(report)


@pytest.mark.parametrize('text', [
    json.dumps({"name": "not_a_tool", "arguments": {}}),
    json.dumps({"name": _GET}),
    json.dumps({"name": _GET, "arguments": {}, "extra": 1}),
    json.dumps({"type": "function", "function": {"name": _GET, "arguments": {}, "x": 1}}),
    json.dumps({"type": "other", "function": {"name": _GET, "arguments": {}}}),
    json.dumps({"function": {"name": _GET, "parameters": {}}}),  # definition needs type
    json.dumps({"name": ["x"], "arguments": {}}),
    json.dumps([{"name": _GET, "arguments": {}}, {"name": "nope", "arguments": {}}]),
    json.dumps([]),
    json.dumps({"unrelated": True}),
    '{"name": "' + _GET + '", "arguments": NaN}',
    json.dumps(_GET),
    f"I will call {_GET} with owner octo-org",
    f'Sure: {json.dumps({"name": _GET, "arguments": {}})}',
    "```json\n" + json.dumps({"name": _GET, "arguments": {}}) + "\n```",
    '{"name": "' + _GET + '", "arguments": ',
    "",
])
def test_content_tool_json_false_positives(github_suite, text):
    report, _ = _content_case(github_suite, text)
    assert 'content_tool_json' not in report['cases'][0]
    assert 'tool JSON in assistant text' not in render_explain_text(report)


def test_content_tool_json_rejects_oversized_and_deep_content(github_suite):
    big = json.dumps({"name": _GET, "arguments": {"pad": "x" * 30_000}})
    deep = "[" * 100_000 + "]" * 100_000
    many = json.dumps([{"name": _GET, "arguments": {}}] * 21)
    for text in (big, deep, many):
        report, _ = _content_case(github_suite, text)
        assert 'content_tool_json' not in report['cases'][0]


def test_content_tool_json_survives_deeply_nested_arguments(github_suite):
    nested = "[" * 3000 + "]" * 3000
    report, _ = _content_case(github_suite, '{"name": "%s", "arguments": %s}' % (_GET, nested))
    # either parsed (outer shape matches) or safely skipped on recursion
    # limits; never an exception, and the no_call classification is kept
    assert report['cases'][0]['diagnostics'] == ['no_call']


def test_content_tool_json_ineligible_cases(github_suite):
    text = json.dumps({"name": _GET, "arguments": _ARGS})
    for kwargs in ({'error': 'boom'}, {'truncated': True},
                   {'calls': [Call(name=_GET, arguments=_ARGS)], 'called': _GET}):
        report, _ = _content_case(github_suite, text, **kwargs)
        assert 'content_tool_json' not in report['cases'][0]
    # an abstention task is not an expected-call task
    report, _ = _content_case(github_suite, text, task_id='missing-repository')
    assert 'content_tool_json' not in report['cases'][0]


def test_content_tool_json_does_not_change_scores_or_inputs(github_suite):
    task = _tasks(github_suite)['get-issue-details']
    text = json.dumps({"name": _GET, "arguments": _ARGS})
    result = _base_result(task, response_text=text)
    run = Run(config=_config(github_suite), started_at='now', results=[result])
    before = run.model_dump_json()
    case = explain_run(run, github_suite)['cases'][0]
    assert run.model_dump_json() == before
    assert (result.selection_ok, result.schema_ok, result.args_ok, result.success) == (False,) * 4
    assert case['diagnostics'] == ['no_call']
    assert case['calls'] == [] and case['call_evidence'] == 'none'


def test_content_tool_json_ignores_tool_not_in_bundle(github_suite):
    report, _ = _content_case(github_suite, json.dumps({"name": "other", "arguments": {}}))
    assert 'content_tool_json' not in report['cases'][0]


# ----------------------------------------- repeat-variation diagnostics


def _passing_result(task, pad, repeat):
    return _base_result(task, pad=pad, repeat=repeat,
                        selection_ok=True, schema_ok=True, args_ok=True, success=True)


def _failing_result(task, pad, repeat):
    # defaults already encode a failure (all flags False, success False)
    return _base_result(task, pad=pad, repeat=repeat)


def test_repeat_variation_flags_mixed_scored_outcomes(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=1),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    variation = explain_run(run, github_suite)["repeat_variation"]
    assert variation["groups_examined"] == 1
    assert len(variation["mixed_groups"]) == 1
    group = variation["mixed_groups"][0]
    assert group["task_id"] == task.id
    assert group["pad"] == 0
    assert group["passing_repeat_ids"] == [0]
    assert group["failing_repeat_ids"] == [1]
    assert "excluded_error_repeat_ids" not in group
    assert "deterministic" in variation["caveat"]


def test_repeat_variation_stable_group_is_examined_not_mixed(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _passing_result(task, pad=0, repeat=1),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    # No failing cases, so render_explain_text would early-return; we check
    # the JSON object directly for the recorded group count.
    variation = explain_run(run, github_suite)["repeat_variation"]
    assert variation["groups_examined"] == 1
    assert variation["mixed_groups"] == []


def test_repeat_variation_never_mixes_pads(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _passing_result(task, pad=0, repeat=1),
        _failing_result(task, pad=8, repeat=0),
        _failing_result(task, pad=8, repeat=1),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    variation = explain_run(run, github_suite)["repeat_variation"]
    # Each (task, pad) group is stable on its own, even though success
    # differs across pads.
    assert variation["groups_examined"] == 2
    assert variation["mixed_groups"] == []


def test_repeat_variation_excludes_errors_from_mixed_counts(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    err = _base_result(task, pad=0, repeat=2, error="timeout",
                       failures=["request failed: timeout"])
    results = [
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=1),
        err,
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    variation = explain_run(run, github_suite)["repeat_variation"]
    group = variation["mixed_groups"][0]
    assert group["passing_repeat_ids"] == [0]
    assert group["failing_repeat_ids"] == [1]
    assert group["excluded_error_repeat_ids"] == [2]


def test_repeat_variation_omitted_for_single_repeat_runs(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    run = Run(config=_config(github_suite), started_at="now",
              results=[_failing_result(task, pad=0, repeat=0)])
    assert "repeat_variation" not in explain_run(run, github_suite)


def test_repeat_variation_omitted_when_only_errors_cover_the_group(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _base_result(task, pad=0, repeat=0, error="a", failures=["request failed: a"]),
        _base_result(task, pad=0, repeat=1, error="b", failures=["request failed: b"]),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    # fewer than two scored repeats → nothing examined; stay concise
    assert "repeat_variation" not in explain_run(run, github_suite)


def test_repeat_variation_requires_two_distinct_scored_repeats(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _base_result(task, pad=0, repeat=1, error="timeout",
                     failures=["request failed: timeout"]),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    assert "repeat_variation" not in explain_run(run, github_suite)


def test_repeat_variation_respects_task_filter(github_suite):
    tasks = _tasks(github_suite)
    a = tasks["get-issue-details"]
    b = tasks["post-comment-simple"]
    results = [
        _passing_result(a, pad=0, repeat=0),
        _failing_result(a, pad=0, repeat=1),
        _passing_result(b, pad=0, repeat=0),
        _failing_result(b, pad=0, repeat=1),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    full = explain_run(run, github_suite)["repeat_variation"]
    assert {g["task_id"] for g in full["mixed_groups"]} == {a.id, b.id}
    scoped = explain_run(run, github_suite, task_id=a.id)["repeat_variation"]
    assert [g["task_id"] for g in scoped["mixed_groups"]] == [a.id]
    assert scoped["groups_examined"] == 1


def test_repeat_variation_duplicate_observations_raise_value_error(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=0),  # same (task, pad, repeat)
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    with pytest.raises(ValueError, match="duplicate observation"):
        explain_run(run, github_suite)


def test_repeat_variation_does_not_mutate_run_or_scores(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    r0 = _passing_result(task, pad=0, repeat=0)
    r1 = _failing_result(task, pad=0, repeat=1)
    run = Run(config=_config(github_suite), started_at="now", results=[r0, r1])
    before = run.model_dump_json()
    explain_run(run, github_suite)
    assert run.model_dump_json() == before
    # Flags are untouched: the summary never rescored anything.
    assert (r0.success, r0.selection_ok, r0.schema_ok, r0.args_ok) == (True, True, True, True)
    assert (r1.success, r1.selection_ok, r1.schema_ok, r1.args_ok) == (False, False, False, False)


def test_repeat_variation_is_rendered_in_text_report(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=1),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    text = render_explain_text(explain_run(run, github_suite))
    assert "repeat variation" in text
    assert "1 mixed (task,pad) group(s) across 1 examined" in text
    assert "deterministic tool order" in text
    assert task.id in text
    assert "passing=[0]" in text and "failing=[1]" in text


def test_repeat_variation_text_includes_excluded_error_ids_when_present(github_suite):
    task = _tasks(github_suite)["get-issue-details"]
    results = [
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=1),
        _base_result(task, pad=0, repeat=2, error="timeout",
                     failures=["request failed: timeout"]),
    ]
    run = Run(config=_config(github_suite), started_at="now", results=results)
    text = render_explain_text(explain_run(run, github_suite))
    assert "excluded_errors=[2]" in text


_ARCHIVED_EVIDENCE = (
    REPO_ROOT / "results" / "2026-10-01-rc3-model-validation" / "evidence"
)


@pytest.mark.parametrize("result_file,expected_mixed", [
    ("04-result.json", 11),  # granite3.3:8b core; 24/50 vs 27/50, 11 verdicts moved
    ("08-result.json", 2),   # phi4-mini core; 11/50 both repeats, 2 verdicts moved
])
def test_archived_core_repeat_variation_counts(result_file, expected_mixed):
    from callprobe.models import Run as _Run
    results_path = _ARCHIVED_EVIDENCE / "core" / result_file
    suite = load_suite(str(_ARCHIVED_EVIDENCE / "core-suite"))
    before = results_path.read_bytes()
    run = _Run.model_validate_json(results_path.read_text(encoding="utf-8"))
    report = explain_run(run, suite)
    variation = report["repeat_variation"]
    assert len(variation["mixed_groups"]) == expected_mixed
    # The archived evidence itself must stay byte-identical.
    assert results_path.read_bytes() == before
    # Mixed groups come out in deterministic (task_id, pad) order and
    # never cross pads.
    keys = [(g["task_id"], g["pad"]) for g in variation["mixed_groups"]]
    assert keys == sorted(keys)
    for group in variation["mixed_groups"]:
        assert group["passing_repeat_ids"] and group["failing_repeat_ids"]
        assert not set(group["passing_repeat_ids"]) & set(group["failing_repeat_ids"])


def test_observed_phi_text_tool_shape_is_advisory_only():
    suite = load_suite(str(Path(__file__).resolve().parents[1] / "src/callprobe/suites/core"))
    # Exact structural form observed in the local Phi-4 Mini run: it names
    # the function in `type` and places values in `parameters`.
    text = json.dumps([{"type": "cancel_meeting", "function": {
        "name": "cancel_meeting", "parameters": {
            "meeting_id": "mtg_9012", "notify_attendees": False}}}])
    report, result = _content_case(suite, text, task_id="depth-notify-preference-earlier")
    case = report["cases"][0]
    assert case["content_tool_json"]["tools"] == ["cancel_meeting"]
    assert case["diagnostics"] == ["no_call"]
    assert not result.success and not result.calls


@pytest.fixture
def observation_run(github_suite):
    task, other = github_suite.tasks[:2]
    return Run(config=_config(github_suite, pads=[0, 2], repeats=2), started_at='now', results=[
        _passing_result(task, pad=0, repeat=0),
        _failing_result(task, pad=0, repeat=1),
        _base_result(task, pad=2, repeat=0, error='timeout'),
        _failing_result(other, pad=0, repeat=1),
    ])


@pytest.mark.parametrize('filters,total,errors,failed', [
    ({'pad': 0}, 3, 0, 2), ({'repeat': 1}, 2, 0, 2),
    ({'pad': 2}, 1, 1, 1), ({'pad': 0, 'repeat': 0}, 1, 0, 0),
    ({'pad': 99}, 0, 0, 0), ({'repeat': 99}, 0, 0, 0),
])
def test_observation_filters_scope_all_counts(github_suite, observation_run, filters, total, errors, failed):
    before = observation_run.model_dump_json()
    report = explain_run(observation_run, github_suite, **filters)
    assert report['observation_filter'] == filters
    assert report['total_cases'] == total
    assert report['scored_cases'] == total - errors
    assert report['request_errors'] == errors
    assert report['failed_cases'] == failed
    assert all(all(case[key] == value for key, value in filters.items()) for case in report['cases'])
    text = render_explain_text(report)
    assert 'counts and verdicts cover only this selection' in text
    if total == 0:
        assert 'no recorded results in this selection' in text
        assert 'passed' not in text
    if 'repeat' in filters:
        assert 'repeat_variation' not in report
    assert observation_run.model_dump_json() == before


def test_pad_filter_keeps_repeat_variation_and_task_filter_scopes_verdict(github_suite, observation_run):
    task = github_suite.tasks[0].id
    report = explain_run(observation_run, github_suite, task_id=task, pad=0)
    assert len(report['repeat_variation']['mixed_groups']) == 1
    assert not report['task_passed']
    passed = explain_run(observation_run, github_suite, task_id=task, pad=0, repeat=0)
    assert passed['task_passed'] and passed['total_cases'] == 1
    missing = explain_run(observation_run, github_suite, task_id=task, repeat=99)
    assert not missing['task_passed'] and not missing['task_has_results']
    assert 'no recorded results in this selection' in render_explain_text(missing)
    assert 'observation_filter' not in explain_run(observation_run, github_suite)


@pytest.mark.parametrize('field', ['pad', 'repeat'])
@pytest.mark.parametrize('value', [-1, True, 0.0, '0'])
def test_invalid_observation_filter_is_rejected(github_suite, observation_run, field, value):
    with pytest.raises(ValueError, match='filter must be a nonnegative integer'):
        explain_run(observation_run, github_suite, **{field: value})


def test_cli_observation_filter_is_offline_and_preserves_source(tmp_path, github_suite, github_suite_dir, observation_run, capsys, monkeypatch):
    import httpx
    def no_network(*args, **kwargs):
        raise AssertionError('explain must not contact a model')
    monkeypatch.setattr(httpx, 'Client', no_network)
    path = tmp_path / 'run.json'
    _write_run(path, observation_run)
    before = path.read_bytes()
    code = cli.main(['explain', str(path), '--suite', str(github_suite_dir),
                     '--task', github_suite.tasks[0].id, '--pad', '0', '--repeat', '1', '--format', 'json'])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report['observation_filter'] == {'pad': 0, 'repeat': 1}
    assert report['total_cases'] == report['failed_cases'] == 1
    assert path.read_bytes() == before
    assert cli.main(['explain', str(path), '--suite', str(github_suite_dir), '--repeat', '-1']) == 2
    assert 'repeat filter must be a nonnegative integer' in capsys.readouterr().err
