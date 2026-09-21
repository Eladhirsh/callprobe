"""The GitHub issue-comments example: fixture, tasks, and extractor. Offline."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from callprobe.loader import load_suite
from callprobe.openapi import generate_openapi_suite, load_openapi_file
from callprobe.scoring import _judge
from callprobe.validate import validate_suite

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "github-issues"

_spec = importlib.util.spec_from_file_location("github_extract", EXAMPLE / "extract.py")
extract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract)


@pytest.fixture(scope="module")
def suite(tmp_path_factory):
    root = tmp_path_factory.mktemp("suite")
    files, result = generate_openapi_suite(
        load_openapi_file(EXAMPLE / "openapi.json"), "github-issues")
    assert result.skipped == []
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    (root / "tasks.yaml").write_text((EXAMPLE / "tasks.yaml").read_text(encoding="utf-8"))
    return load_suite(str(root))


def _set(data, dotted, value):
    *parents, leaf = dotted.split(".")
    for part in parents:
        data = data.setdefault(part, {})
    data[leaf] = value


def _expected_arguments(task):
    arguments = copy.deepcopy(task.expect.args)
    for check in task.expect.arg_checks:
        assert check.op == "eq"
        _set(arguments, check.path, check.value)
    return arguments


def test_fixture_imports_three_operations_and_cases_validate(suite):
    assert sorted(t.name for t in suite.bundles["main"].tools) == [
        "issues_create-comment_27544d18",
        "issues_get_cf0062ad",
        "issues_list-comments_e6abc434",
    ]
    assert len(suite.tasks) == 18
    counts = {c: sum(t.category == c for t in suite.tasks) for c in ("select", "args", "abstain", "depth")}
    assert counts == {"select": 5, "args": 5, "abstain": 5, "depth": 3}
    assert {t.expect.tool for t in suite.tasks if t.expect.type == "call"} == {
        t.name for t in suite.bundles["main"].tools}
    assert validate_suite(suite) == []


def test_yaml_does_not_drop_message_text(suite):
    tasks = {t.id: t for t in suite.tasks}
    assert tasks["list-comments-of-issue"].messages == [
        {"role": "user",
         "content": "What comments have been left on octo-org/widget issue #42?"}]
    # A " #..." in an unquoted scalar becomes a YAML comment; every expected
    # issue number and owner/repo must still be visible in the user's messages.
    for task in suite.tasks:
        if task.expect.type == "call":
            path = task.expect.args["path"]
            text = " ".join(m["content"] for m in task.messages if m["role"] == "user")
            assert f'{path["owner"]}/{path["repo"]}' in text, task.id
            assert str(path["issue_number"]) in text, task.id


def test_expected_calls_pass_the_scorer(suite):
    bundle = suite.bundles["main"]
    calls = [t for t in suite.tasks if t.expect.type == "call"]
    assert len(calls) == 12
    for task in calls:
        schema_ok, args_ok, failures = _judge(
            _expected_arguments(task), bundle.by_name(task.expect.tool), task)
        assert (schema_ok, args_ok, failures) == (True, True, []), task.id


def test_wrong_nested_shapes_fail(suite):
    bundle = suite.bundles["main"]
    tasks = {t.id: t for t in suite.tasks}

    post = tasks["post-comment-simple"]
    tool = bundle.by_name(post.expect.tool)
    good = _expected_arguments(post)
    flat = {"owner": "octo-org", "repo": "widget", "issue_number": 42,
            "body": "Thanks, this is fixed in the next release."}
    string_body = {**good, "body": "Thanks, this is fixed in the next release."}
    string_number = copy.deepcopy(good)
    string_number["path"]["issue_number"] = "42"
    for bad in (flat, string_body, string_number):
        schema_ok, args_ok, _ = _judge(bad, tool, post)
        assert not (schema_ok and args_ok)

    paging = tasks["pagination-upper-values"]
    tool = bundle.by_name(paging.expect.tool)
    good = _expected_arguments(paging)
    top_level = {"path": good["path"], "page": 3, "per_page": 100}
    schema_ok, args_ok, _ = _judge(top_level, tool, paging)
    assert not schema_ok and not args_ok
    wrong_value = copy.deepcopy(good)
    wrong_value["query"]["per_page"] = 30
    schema_ok, args_ok, _ = _judge(wrong_value, tool, paging)
    assert schema_ok and not args_ok


# ---- extractor, using a compact synthetic document ----


def _document():
    param = lambda name, loc="path": {  # noqa: E731
        "name": name, "in": loc, "required": loc == "path", "schema": {"type": "string"}}
    return {
        "openapi": "3.0.3",
        "paths": {
            "/repos/{owner}/{repo}/issues/{issue_number}": {
                "get": {
                    "summary": "Get an issue", "description": "kept\nverbatim",
                    "operationId": "issues/get", "tags": ["issues"],
                    "parameters": [{"$ref": "#/components/parameters/owner"}],
                    "responses": {"200": {"$ref": "#/components/responses/big"}},
                },
                "patch": {"operationId": "issues/update"},
            },
            "/repos/{owner}/{repo}/issues/{issue_number}/comments": {
                "get": {"operationId": "issues/list-comments",
                        "parameters": [{"$ref": "#/components/parameters/owner"}]},
                "post": {
                    "operationId": "issues/create-comment",
                    "requestBody": {"content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/comment"}}}},
                },
            },
            "/other": {"get": {"operationId": "other"}},
        },
        "components": {
            "parameters": {"owner": param("owner"), "unused": param("x")},
            "schemas": {
                "comment": {"type": "object",
                            "properties": {"user": {"$ref": "#/components/schemas/user"}}},
                "user": {"type": "string"},
                "orphan": {"type": "integer"},
            },
            "responses": {"big": {"description": "large"}},
        },
    }


def test_projection_selects_operations_and_reachable_components_only():
    document = _document()
    projected = extract.project(document)
    assert projected == extract.project(copy.deepcopy(document))
    paths = projected["paths"]
    assert sorted(paths) == sorted({p for p, _ in extract.OPERATIONS})
    get = paths["/repos/{owner}/{repo}/issues/{issue_number}"]["get"]
    source = document["paths"]["/repos/{owner}/{repo}/issues/{issue_number}"]["get"]
    for key in ("summary", "description", "operationId", "parameters"):
        assert get[key] == source[key]
    assert "tags" not in get and "patch" not in paths["/repos/{owner}/{repo}/issues/{issue_number}"]
    assert list(get["responses"]) == ["200"]
    assert list(paths["/repos/{owner}/{repo}/issues/{issue_number}/comments"]["post"]["responses"]) == ["201"]
    assert projected["components"] == {
        "parameters": {"owner": document["components"]["parameters"]["owner"]},
        "schemas": {"comment": document["components"]["schemas"]["comment"],
                    "user": {"type": "string"}},
    }


def test_extract_verifies_source_hash(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_document()), encoding="utf-8")
    out = tmp_path / "out" / "openapi.json"
    with pytest.raises(SystemExit, match="SHA256 mismatch"):
        extract.extract(source, out)
    assert not out.exists()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    extract.extract(source, out, expected_sha256=digest)
    assert json.loads(out.read_text(encoding="utf-8")) == extract.project(_document())
    provenance = json.loads((out.parent / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_revision"] == extract.REVISION
    assert provenance["source_sha256"] == extract.SOURCE_SHA256


def test_committed_provenance_matches_pinned_source():
    provenance = json.loads((EXAMPLE / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_sha256"] == extract.SOURCE_SHA256
    assert extract.REVISION in provenance["source_url"]
    fixture = json.loads((EXAMPLE / "openapi.json").read_text(encoding="utf-8"))
    assert provenance == extract.provenance(fixture)
