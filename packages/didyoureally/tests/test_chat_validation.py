import json

import pytest

from didyoureally import Claim, check, from_openai_messages, load_trace
from didyoureally.cli import main
from didyoureally.extract import LLMExtractor


def recording():
    return {
        "tools": [{"type": "function", "function": {"name": "send_email", "parameters": {}}}],
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "send_email", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
            {"role": "assistant", "content": "Sent!"},
        ],
    }


@pytest.mark.parametrize("value", [None, {}, "messages", False])
def test_message_collection_cannot_be_an_empty_object_or_scalar(value):
    with pytest.raises(ValueError, match="messages must be an array"):
        load_trace({"messages": value})


def test_direct_adapter_requires_messages_in_a_wrapped_recording():
    with pytest.raises(ValueError, match="messages must be an array"):
        from_openai_messages({"tools": []})


@pytest.mark.parametrize("value", [None, [], "message", 0])
def test_message_entries_fail_cleanly_instead_of_attribute_errors(value):
    with pytest.raises(ValueError, match="message 0 must be an object"):
        load_trace({"messages": [value]})


@pytest.mark.parametrize("role", [None, "Assistant", "function", [], 0])
def test_unknown_roles_cannot_silently_hide_completed_action_text(role):
    with pytest.raises(ValueError, match="role is not supported"):
        load_trace({"messages": [{"role": role, "content": "Sent!"}]})


@pytest.mark.parametrize("role", ["user", "system", "developer", "tool"])
def test_only_assistant_messages_can_propose_calls(role):
    data = recording()
    data["messages"][0]["role"] = role
    with pytest.raises(ValueError, match="Only assistant"):
        load_trace(data)


@pytest.mark.parametrize("value", [{}, False, 0, "", [None], ["call"]])
def test_tool_call_container_and_entries_have_explicit_shapes(value):
    data = recording()
    data["messages"][0]["tool_calls"] = value
    with pytest.raises(ValueError):
        load_trace(data)


@pytest.mark.parametrize("value", [None, [], "function"])
def test_function_call_envelopes_must_be_objects(value):
    data = recording()
    data["messages"][0]["tool_calls"][0]["function"] = value
    with pytest.raises(ValueError, match="function must be an object"):
        load_trace(data)


@pytest.mark.parametrize("name", [None, "", " ", 0])
def test_calls_cannot_invent_an_unknown_tool_for_missing_names(name):
    data = recording()
    data["messages"][0]["tool_calls"][0]["function"]["name"] = name
    with pytest.raises(ValueError, match="name must be a nonempty string"):
        load_trace(data)


@pytest.mark.parametrize("value", [None, {}, [None], [{"function": None}], [{"function": {"name": None}}]])
def test_invalid_catalogs_fail_before_result_interpretation(value):
    data = recording()
    data["tools"] = value
    with pytest.raises(ValueError):
        load_trace(data)


@pytest.mark.parametrize("location", ["catalog", "call"])
def test_unsupported_tool_types_are_not_treated_as_functions(location):
    data = recording()
    target = data["tools"][0] if location == "catalog" else data["messages"][0]["tool_calls"][0]
    target["type"] = "custom"
    with pytest.raises(ValueError, match="Unsupported tool"):
        load_trace(data)


@pytest.mark.parametrize(
    "content",
    [
        {},
        False,
        0,
        ["Sent!"],
        [None],
        [{"type": "text"}],
        [{"type": "text", "text": None}],
        [{"type": "text", "text": 1}],
        [{"type": "image_url", "image_url": {"url": "unused"}}],
        [{"type": "refusal", "refusal": None}],
        [{"text": "Sent!"}, {"type": "unsupported"}],
    ],
)
def test_unsupported_content_is_not_discarded_or_stringified(content):
    with pytest.raises(ValueError):
        load_trace({"messages": [{"role": "assistant", "content": content}]})


@pytest.mark.parametrize("content", [None, "", []])
def test_empty_assistant_content_preserves_proposal_and_result_lifecycle(content):
    data = recording()
    data["messages"][0]["content"] = content
    trace = load_trace(data)
    assert len(trace.calls) == 1 and trace.calls[0].status == "ok"
    assert [m.content for m in trace.assistant_messages()] == ["Sent!"]


def test_text_parts_and_refusal_parts_preserve_text_exactly():
    trace = load_trace(
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Send "}, {"text": "the receipt."}]},
                {"role": "assistant", "content": [{"type": "refusal", "refusal": "I could not send it."}]},
            ]
        }
    )
    assert [m.content for m in trace.messages] == ["Send the receipt.", "I could not send it."]


@pytest.mark.parametrize("role", ["user", "assistant", "system", "developer"])
@pytest.mark.parametrize("calls", [None, []])
def test_empty_optional_call_fields_are_not_proposals(role, calls):
    trace = load_trace({"messages": [{"role": role, "content": "", "tool_calls": calls}]})
    assert not trace.calls


@pytest.mark.parametrize("early", [True, False])
def test_text_parts_keep_completion_claims_on_the_correct_side_of_results(early):
    data = recording()
    parts = [{"type": "text", "text": "Sent"}, {"text": "!"}]
    if early:
        data["messages"][0]["content"] = parts
        data["messages"].pop()
    else:
        data["messages"][-1]["content"] = parts
    trace = load_trace(data)
    claim = Claim("Sent!", "send_email", message_index=trace.assistant_messages()[0].index)
    assert [f.verdict.value for f in check(trace, [claim])] == (
        ["phantom", "unmentioned"] if early else ["backed"]
    )


@pytest.mark.parametrize("call_id", [None, [], 0, " "])
def test_tool_results_require_nonempty_string_references(call_id):
    data = recording()
    data["messages"][1]["tool_call_id"] = call_id
    with pytest.raises(ValueError, match="tool_call_id must be a nonempty string"):
        load_trace(data)


def test_malformed_chat_cli_input_is_an_input_error_and_batch_continues(tmp_path, capsys, monkeypatch):
    bad, good = tmp_path / "bad.json", tmp_path / "good.json"
    bad.write_text(json.dumps({"messages": [None]}))
    data = recording()
    data["claims"] = [{"text": "Sent!", "tool": "send_email", "message_index": 1}]
    good.write_text(json.dumps(data))

    def no_model(*args):
        raise AssertionError("Malformed chat input must not reach extraction")

    monkeypatch.setattr(LLMExtractor, "extract", no_model)
    assert main(["check", str(bad), str(good), "--format", "json"]) == 2
    output = capsys.readouterr().out
    first, end = json.JSONDecoder().raw_decode(output)
    second = json.loads(output[end:])
    assert first["status"] == "invalid_input" and first["summary"] is None
    assert second["status"] == "complete" and second["summary"]["backed"] == 1
