import io
import json

import pytest

from didyoureally import GivenClaims, Trace, check, load_trace
from didyoureally.cli import main
from didyoureally.extract import ExtractionError, LLMExtractor
from didyoureally.schema import load_json
from didyoureally.staged import StagedExtractor


def recording(arguments='{"to":"dana@example.invalid"}', result='{"ok":true}'):
    return {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"id": "c1", "function": {"name": "send_email", "arguments": arguments}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": result},
            {"role": "assistant", "content": "Sent the email."},
        ],
        "claims": [{"text": "Sent the email.", "tool": "send_email", "message_index": 1}],
    }


@pytest.mark.parametrize(
    "arguments",
    [
        '{"to":"wrong@example.invalid","to":"dana@example.invalid"}',
        '{"to":"dana@example.invalid","to":"dana@example.invalid"}',
        '{"address":{"to":"wrong@example.invalid","to":"dana@example.invalid"}}',
        '{"to":"wrong@example.invalid","t\\u006f":"dana@example.invalid"}',
    ],
)
def test_duplicate_arguments_cannot_back_a_completion(arguments):
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        load_trace(recording(arguments=arguments))


@pytest.mark.parametrize(
    "result",
    [
        '{"ok":false,"ok":true}',
        '{"ok":true,"ok":false}',
        '{"ok":true,"metadata":{"attempt":1,"attempt":2}}',
    ],
)
def test_duplicate_outcome_keys_are_not_treated_as_success_or_plain_text(result):
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        load_trace(recording(result=result))


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e400"])
@pytest.mark.parametrize("field", ["arguments", "result"])
def test_nonfinite_json_numbers_are_invalid_evidence(field, number):
    value = '{"ok":true,"metadata":{"latency":' + number + "}}"
    with pytest.raises(ValueError, match="Nonfinite"):
        load_trace(recording(**{field: value}))


@pytest.mark.parametrize("arguments", [None, False, 0, [], [["to", "Dana"]], "", "{", "[]", "null"])
def test_invalid_arguments_cannot_turn_into_empty_or_raw_successful_calls(arguments):
    with pytest.raises(ValueError):
        load_trace(recording(arguments=arguments))


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_decoded_adapter_and_native_inputs_cannot_bypass_finite_validation(number):
    with pytest.raises(ValueError, match="Nonfinite"):
        load_trace(recording(arguments={"metadata": [number]}))
    with pytest.raises(ValueError, match="Nonfinite"):
        load_trace(recording(result={"ok": True, "metadata": [number]}))
    with pytest.raises(ValueError, match="Nonfinite"):
        Trace.from_dict({"events": [{"type": "tool_call", "tool": "send_email", "args": {"x": number}}]})
    with pytest.raises(ValueError, match="Nonfinite"):
        GivenClaims([{"text": "Sent!", "tool": "send_email", "args": {"x": number}}])


@pytest.mark.parametrize("ok,verdict", [(False, "masked_failure"), (True, "backed")])
def test_valid_nested_results_and_distinct_sibling_keys_keep_their_outcomes(ok, verdict):
    args = '{"to":"dana@example.invalid","options":{"enabled":false},"metadata":{"enabled":true}}'
    result = json.dumps({"ok": ok, "attempt": {"ok": True, "latency": 0.25}, "count": 0})
    data = recording(arguments=args, result=result)
    trace = load_trace(data)
    [finding] = check(trace, GivenClaims(data["claims"]).claims)
    assert finding.verdict.value == verdict
    assert trace.calls[0].args["options"]["enabled"] is False


@pytest.mark.parametrize("result", ["ok", "Success!", '{"ok":true,"latency":1.5e2}'])
def test_plain_text_success_and_finite_scientific_notation_still_load(result):
    assert load_trace(recording(result=result)).calls[0].status == "ok"


@pytest.mark.parametrize(
    "raw",
    [
        '{"events":[],"events":[]}',
        '{"claims":[],"claims":[]}',
        '{"events":[{"type":"tool_call","tool":"send_email","status":"error","status":"ok"}]}',
        '{"events":[],"metadata":{"number":1e400}}',
    ],
)
def test_file_input_rejects_ambiguity_before_trace_construction(tmp_path, raw):
    path = tmp_path / "trace.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_json(path)


def test_cli_reports_invalid_input_and_continues_batch_without_extraction(tmp_path, capsys, monkeypatch):
    bad, good = tmp_path / "bad.json", tmp_path / "good.json"
    bad.write_text(json.dumps(recording(result='{"ok":false,"ok":true}')))
    good.write_text(json.dumps(recording()))

    def no_model(*args):
        raise AssertionError("Invalid recorded evidence must not reach the model")

    monkeypatch.setattr(LLMExtractor, "extract", no_model)
    assert main(["check", str(bad), str(good), "--format", "json"]) == 2
    output = capsys.readouterr().out
    decoder = json.JSONDecoder()
    first, end = decoder.raw_decode(output)
    second = json.loads(output[end:])
    assert first["status"] == "invalid_input" and first["summary"] is None
    assert second["status"] == "complete" and second["summary"]["backed"] == 1


@pytest.mark.parametrize("extractor", [LLMExtractor, StagedExtractor])
@pytest.mark.parametrize("number", ["NaN", "Infinity", "1e400"])
def test_nonfinite_extractor_json_cannot_become_a_clean_empty_result(extractor, number):
    calls = []

    def transport(*args):
        calls.append(args)
        return {"choices": [{"message": {"content": '{"claims":[],"metadata":' + number + "}"}}]}

    trace = load_trace(recording())
    with pytest.raises(ExtractionError):
        extractor(transport=transport).extract(trace)
    assert len(calls) == 2


def test_nonfinite_staged_details_exhaust_repair_without_passing():
    replies = iter(
        [
            '{"claims":[{"completed":true,"tool":"send_email","args":{}}]}',
            '{"details":[{"action_id":0,"args":{}}],"metadata":NaN}',
            '{"details":[{"action_id":0,"args":{}}],"metadata":NaN}',
        ]
    )

    def transport(*args):
        return {"choices": [{"message": {"content": next(replies)}}]}

    with pytest.raises(ExtractionError, match="invalid_action_details"):
        StagedExtractor(transport=transport).extract(load_trace(recording()))


@pytest.mark.parametrize("extractor", [LLMExtractor, StagedExtractor])
def test_ambiguous_http_envelope_is_an_incomplete_provider_response(extractor, monkeypatch):
    raw = b'{"choices":[],"choices":[{"message":{"content":"{\\"claims\\":[]}"}}]}'
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(raw))
    with pytest.raises(ExtractionError) as caught:
        extractor().extract(load_trace(recording()))
    assert caught.value.reason == "provider_error"
