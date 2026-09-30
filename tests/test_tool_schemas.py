import json

import pytest

from didyoureally import Trace, load_trace
from didyoureally.extract import LLMExtractor, build_user_prompt, parse_claims


def trace_with_schema(properties, text="Deleted alpha.txt and beta.txt."):
    return Trace.from_dict(
        {
            "id": "schema",
            "tools": [{"name": "act", "parameters": {"type": "object", "properties": properties}}],
            "events": [{"type": "message", "role": "assistant", "content": text}],
        }
    )


def parse(trace, args, *, completed=True):
    return parse_claims(
        json.dumps(
            {
                "claims": [
                    {
                        "text": trace.messages[0].content,
                        "completed": completed,
                        "tool": "act",
                        "args": args,
                    }
                ]
            }
        ),
        trace,
        target_index=0,
        require_completed=True,
    )


def test_explicit_scalar_schema_splits_named_objects():
    trace = trace_with_schema({"path": {"type": "string"}})
    claims = parse(trace, {"path": ["alpha.txt", "beta.txt"]})
    assert [c.args for c in claims] == [{"path": "alpha.txt"}, {"path": "beta.txt"}]


def test_array_schema_retains_one_action():
    trace = trace_with_schema({"attendees": {"type": "array"}}, "Invited Alpha and Beta to a meeting.")
    [claim] = parse(trace, {"attendees": ["Alpha", "Beta"]})
    assert claim.args == {"attendees": ["Alpha", "Beta"]}


def test_absent_schema_does_not_guess_scalar_arity():
    trace = trace_with_schema({})
    assert len(parse(trace, {"path": ["alpha.txt", "beta.txt"]})) == 1


def test_parallel_scalar_lists_are_not_cartesian_product():
    trace = trace_with_schema({"path": {"type": "string"}, "destination": {"type": "string"}})
    with pytest.raises(ValueError, match="ambiguous pairings"):
        parse(trace, {"path": ["alpha.txt", "beta.txt"], "destination": ["one", "two"]})


def test_native_schema_roundtrip_and_openai_schema_retained():
    properties = {"path": {"type": "string"}}
    native = trace_with_schema(properties)
    assert Trace.from_dict(native.to_dict()).tools["act"].parameters == native.tools["act"].parameters
    trace = load_trace(
        {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "act",
                        "parameters": {"type": "object", "properties": properties},
                    },
                }
            ],
            "messages": [],
        }
    )
    assert trace.tools["act"].parameters == native.tools["act"].parameters
    assert '"path": {"type": "string"}' in build_user_prompt(native)


def test_noncompletion_is_not_a_success_claim():
    trace = trace_with_schema({}, "I can delete it after you approve.")
    assert parse(trace, {}, completed=False) == []
    with pytest.raises(ValueError, match="boolean completed"):
        parse(trace, {}, completed="false")


def test_null_placeholder_requires_repair():
    trace = trace_with_schema({})
    with pytest.raises(ValueError, match="null"):
        parse(trace, {"event_id": None})


def test_json_mode_is_explicit_and_repair_contains_original_reply():
    calls = []

    def transport(url, headers, body):
        calls.append(json.loads(json.dumps(body)))
        raw = "{}" if len(calls) == 1 else '{"claims": []}'
        return {"choices": [{"message": {"content": raw}}]}

    trace = trace_with_schema({}, "I can delete it later.")
    assert LLMExtractor(transport=transport, json_mode=True).extract(trace) == []
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": "{}"}
