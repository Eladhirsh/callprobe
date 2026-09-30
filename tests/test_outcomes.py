import json

import pytest

from didyoureally import GivenClaims, check, load_trace


def exported(result, *, early=False, missing=False):
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "send_email", "arguments": "{}"}}],
        },
    ]
    claim = {"role": "assistant", "content": "Sent!"}
    if early:
        messages.append(claim)
    if not missing:
        messages.append({"role": "tool", "tool_call_id": "c1", "content": json.dumps(result)})
    if not early:
        messages.append(claim)
    return {"messages": messages}


@pytest.mark.parametrize(
    "result",
    [
        {"success": False},
        {"ok": False},
        {"isError": True},
        {"status_code": 500},
        {"ok": True, "error": "provider rejected send"},
    ],
)
def test_explicit_failures_cannot_back_sent(result):
    trace = load_trace(exported(result))
    findings = check(
        trace, GivenClaims([{"text": "Sent!", "tool": "send_email", "args": {}, "message_index": 1}]).claims
    )
    assert findings[0].verdict.value == "masked_failure"


@pytest.mark.parametrize("result", [None, {}, {"delivery": "pending"}, {"success": "false"}])
def test_unknown_write_outcome_is_input_error(result):
    with pytest.raises(ValueError, match="Success was not assumed"):
        load_trace(exported(result))


def test_missing_result_is_input_error():
    with pytest.raises(ValueError, match="Missing tool results"):
        load_trace(exported(None, missing=True))


def test_later_result_cannot_back_earlier_sent():
    trace = load_trace(exported({"ok": True}, early=True))
    findings = check(
        trace, GivenClaims([{"text": "Sent!", "tool": "send_email", "args": {}, "message_index": 0}]).claims
    )
    assert [f.verdict.value for f in findings] == ["phantom", "unmentioned"]


def test_successful_send_control():
    trace = load_trace(exported({"success": True}))
    assert trace.calls[0].status == "ok"
