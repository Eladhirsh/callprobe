"""Incomplete provider evidence must survive normalization and offline replay."""

import copy
import json

import httpx
import pytest

from callprobe.client import ChatClient, Completion, parse_completion
from callprobe.gates import GatePolicy, evaluate_gate
from callprobe.models import Bundle, Call, Expectation, RunConfig, Suite, Task, Tool
from callprobe.recording_io import read_recordings, recordings_to_json
from callprobe.recordings import RecordedCompletion, score_recordings


def _suite(expect_call=False):
    return Suite(
        name="integrity",
        hash="scripted-integrity-suite",
        bundles={
            "b": Bundle(
                name="b",
                tools=[
                    Tool(
                        name="lookup",
                        description="Look up an item",
                        parameters={"type": "object"},
                    )
                ],
            ),
        },
        tasks=[
            Task(
                id="one",
                category="select" if expect_call else "abstain",
                bundle="b",
                messages=[{"role": "user", "content": "A scripted control"}],
                expect=Expectation(type="call", tool="lookup")
                if expect_call
                else Expectation(type="no_call"),
            ),
        ],
    )


def _config():
    return RunConfig(
        model="scripted",
        endpoint="recorded://local",
        suite="integrity",
        pads=[0],
        repeats=1,
        temperature=0,
        max_tokens=64,
    )


def _round_trip(tmp_path, completion, *, expect_call=False):
    suite, config = _suite(expect_call), _config()
    records = [RecordedCompletion("one", completion)]
    run = score_recordings(suite, config, records)
    path = tmp_path / "recordings.json"
    path.write_text(recordings_to_json(config, records), encoding="utf-8")
    restored_config, restored = read_recordings(path, suite_label="integrity")
    replayed = score_recordings(suite, restored_config, restored)
    assert replayed.results == run.results
    return run


@pytest.mark.parametrize(
    "finish,legacy,modern",
    [
        (
            "function_call",
            {"name": "legacy", "arguments": "PRIVATE_PROVIDER_VALUE"},
            False,
        ),
        ("stop", {"name": "legacy", "arguments": "{}"}, False),
        ("tool_calls", {"name": "legacy", "arguments": "{}"}, True),
        ("stop", {}, False),
        ("function_call", None, False),
    ],
)
def test_legacy_call_errors_survive_export_and_cannot_pass_gates(tmp_path, finish, legacy, modern):
    message = {"content": "PRIVATE_PROVIDER_VALUE", "function_call": legacy}
    if modern:
        message["tool_calls"] = [{"function": {"name": "lookup", "arguments": "{}"}}]
    body = {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    before = copy.deepcopy(body)
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    client = ChatClient("http://example.invalid/v1", transport=httpx.MockTransport(transport))
    try:
        completion = client.complete("scripted", [], [])
    finally:
        client.close()
    assert len(requests) == 1
    assert body == before and completion.raw == body
    assert completion.error == "unsupported legacy function-call response"
    assert (completion.prompt_tokens, completion.completion_tokens) == (7, 3)
    assert len(completion.calls) == int(modern)
    run = _round_trip(tmp_path, completion, expect_call=modern)
    result = run.results[0]
    assert result.error == completion.error
    assert not result.success and not result.success_lenient
    assert "PRIVATE_PROVIDER_VALUE" not in " ".join(result.failures)
    assert not evaluate_gate(run, run, GatePolicy())["passed"]


@pytest.mark.parametrize("finish", ["content_filter", "function_call", "PRIVATE_FINISH"])
@pytest.mark.parametrize("expect_call", [False, True])
def test_explicit_unfinished_recordings_cannot_pass(tmp_path, finish, expect_call):
    completion = Completion(
        calls=[Call(name="lookup")] if expect_call else [],
        content="A partial response",
        finish_reason=finish,
        prompt_tokens=7,
        completion_tokens=3,
        latency_ms=12.5,
    )
    run = _round_trip(tmp_path, completion, expect_call=expect_call)
    result = run.results[0]
    assert result.error == "response ended without a completed decision"
    assert not result.success and not result.success_lenient
    assert not result.truncated
    assert result.finish_reason == finish
    assert (result.prompt_tokens, result.completion_tokens, result.latency_ms) == (
        7,
        3,
        12.5,
    )
    assert completion.error is None  # scoring does not rewrite the caller's evidence
    assert "PRIVATE_FINISH" not in " ".join(result.failures)
    assert not evaluate_gate(run, run, GatePolicy())["passed"]


@pytest.mark.parametrize("calls", [None, []])
def test_tool_call_finish_without_call_is_not_abstention(tmp_path, calls):
    completion = parse_completion(
        {
            "choices": [
                {
                    "message": {"content": "No action", "tool_calls": calls},
                    "finish_reason": "tool_calls",
                }
            ],
        },
        0,
    )
    result = _round_trip(tmp_path, completion).results[0]
    assert result.error == "tool-call finish did not include a call"
    assert not result.success and not result.success_lenient


@pytest.mark.parametrize("finish", [None, "", "stop", "tool_calls"])
def test_valid_modern_calls_remain_successful(tmp_path, finish):
    completion = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "function_call": None,
                        "tool_calls": [{"function": {"name": "lookup", "arguments": "{}"}}],
                    },
                    "finish_reason": finish,
                }
            ],
        },
        0,
    )
    result = _round_trip(tmp_path, completion, expect_call=True).results[0]
    assert result.success and result.success_lenient and result.error is None


@pytest.mark.parametrize("finish", [None, "", "stop"])
def test_absent_finish_metadata_remains_compatible_for_abstention(tmp_path, finish):
    completion = parse_completion(
        {
            "choices": [
                {
                    "message": {"content": "No action", "function_call": None},
                    "finish_reason": finish,
                }
            ],
        },
        0,
    )
    assert _round_trip(tmp_path, completion).results[0].success
    assert "raw" not in json.loads((tmp_path / "recordings.json").read_text())["records"][0]["completion"]


@pytest.mark.parametrize("modern", [False, True])
def test_explicit_provider_refusal_is_not_a_successful_decision(tmp_path, modern):
    message = {"content": None, "refusal": "PRIVATE_REFUSAL"}
    if modern:
        message["tool_calls"] = [{"function": {"name": "lookup", "arguments": "{}"}}]
    body = {"choices": [{"message": message, "finish_reason": "stop"}]}
    client = ChatClient(
        "http://example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    try:
        completion = client.complete("scripted", [], [])
    finally:
        client.close()
    assert completion.error == "provider refused the completion"
    run = _round_trip(tmp_path, completion, expect_call=modern)
    assert not run.results[0].success and not run.results[0].success_lenient
    assert not evaluate_gate(run, run, GatePolicy())["passed"]
    assert "PRIVATE_REFUSAL" not in run.model_dump_json()
    assert "PRIVATE_REFUSAL" not in (tmp_path / "recordings.json").read_text()


@pytest.mark.parametrize("refusal", [False, 0, [], {}, {"secret": "PRIVATE_REFUSAL"}])
def test_malformed_refusal_is_a_generic_request_error(refusal):
    body = {"choices": [{"message": {"content": None, "refusal": refusal}, "finish_reason": "stop"}]}
    with pytest.raises(ValueError, match="^message refusal must be a string or null$"):
        parse_completion(body, 0)
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    client = ChatClient("http://example.invalid/v1", transport=httpx.MockTransport(transport))
    try:
        completion = client.complete("scripted", [], [])
    finally:
        client.close()
    assert completion.error == "invalid chat completion response (ValueError)"
    assert completion.raw == {}
    assert len(requests) == 1


@pytest.mark.parametrize("refusal", [None, ""])
def test_empty_refusal_metadata_remains_compatible(tmp_path, refusal):
    completion = parse_completion(
        {
            "choices": [{"message": {"content": "No action", "refusal": refusal}, "finish_reason": "stop"}],
        },
        0,
    )
    assert completion.error is None
    assert _round_trip(tmp_path, completion).results[0].success
