import json

import pytest

from didyoureally.cli import main
from didyoureally.extract import ExtractionError, LLMExtractor
from didyoureally.schema import Trace
from didyoureally.staged import StagedExtractor


def trace():
    return Trace.from_dict(
        {
            "tools": [{"name": "send_email"}],
            "events": [{"type": "message", "role": "assistant", "content": "Sent!"}],
        }
    )


def response(content='{"claims": []}', **message_fields):
    return {"choices": [{"message": {"content": content, **message_fields}, "finish_reason": "stop"}]}


@pytest.mark.parametrize("cls", [LLMExtractor, StagedExtractor])
@pytest.mark.parametrize("content", ['{"claims": []}', None])
def test_refusal_never_looks_like_a_completed_empty_extraction(cls, content):
    requests = []

    def transport(*args):
        requests.append(args)
        return response(content, refusal="private refusal reason")

    with pytest.raises(ExtractionError) as caught:
        cls(transport=transport).extract(trace())
    assert caught.value.reason == "provider_refusal"
    assert "private" not in str(caught.value)
    assert len(requests) == 1


@pytest.mark.parametrize("cls", [LLMExtractor, StagedExtractor])
@pytest.mark.parametrize("role", [None, "assistant", "omitted"])
@pytest.mark.parametrize("refusal", [None, "", "omitted"])
def test_absent_or_empty_optional_metadata_remains_compatible(cls, role, refusal):
    fields = {}
    if role != "omitted":
        fields["role"] = role
    if refusal != "omitted":
        fields["refusal"] = refusal
    assert cls(transport=lambda *args: response(**fields)).extract(trace()) == []


@pytest.mark.parametrize("cls", [LLMExtractor, StagedExtractor])
@pytest.mark.parametrize(
    "body",
    [
        response(role="user"),
        response(role="tool"),
        response(role={}),
        response(refusal=False),
        response(refusal=[]),
        response(refusal={}),
        response(content=[]),
        response(content=False),
        {"choices": {"0": {"message": {"content": '{"claims": []}'}}}},
        {**response(), "error": {"message": "private provider diagnostic"}},
        {"choices": [{"message": {"content": '{"claims": []}'}, "finish_reason": False}]},
    ],
)
def test_malformed_provider_metadata_fails_without_retry_or_raw_diagnostics(cls, body):
    requests = []

    def transport(*args):
        requests.append(args)
        return body

    with pytest.raises(ExtractionError) as caught:
        cls(transport=transport).extract(trace())
    assert caught.value.reason == "provider_error"
    assert "private" not in str(caught.value)
    assert len(requests) == 1


def test_refusal_in_staged_detail_request_cannot_return_partial_mapping():
    replies = iter(
        [
            response('{"claims": [{"completed": true, "tool": "send_email", "args": {}}]}'),
            response('{"details": []}', refusal="private refusal"),
        ]
    )
    with pytest.raises(ExtractionError) as caught:
        StagedExtractor(transport=lambda *args: next(replies)).extract(trace())
    assert caught.value.reason == "provider_refusal"


@pytest.mark.parametrize("mode", ["default", "staged"])
def test_cli_reports_refusal_as_incomplete_even_with_finding_gates_disabled(
    tmp_path, monkeypatch, capsys, mode
):
    from didyoureally import extract

    path = tmp_path / "trace.json"
    path.write_text(json.dumps({"events": [{"type": "message", "role": "assistant", "content": "Sent!"}]}))
    monkeypatch.setattr(extract, "_http_post", lambda *args: response(refusal="private refusal reason"))
    assert main(["check", str(path), "--extraction-mode", mode, "--format", "json", "--fail-on", ""]) == 3
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "incomplete"
    assert report["summary"] is None
    assert report["error"]["reason"] == "provider_refusal"
    assert "private refusal" not in output
