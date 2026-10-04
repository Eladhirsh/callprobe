import json

import pytest

from didyoureally import Trace, check
from didyoureally.extract import parse_claims


def session(calls, message="I refunded both orders, A-1 and A-2."):
    return Trace.from_dict(
        {
            "tools": [
                {
                    "name": "refund",
                    "parameters": {
                        "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}}
                    },
                }
            ],
            "events": [
                {"type": "tool_call", "id": str(i), "tool": "refund", "args": args, "status": status}
                for i, (args, status) in enumerate(calls)
            ]
            + [{"type": "message", "role": "assistant", "content": message}],
        }
    )


def extract(t, actions):
    return parse_claims(
        json.dumps({"claims": [{"completed": True, "tool": "refund", "actions": actions}]}),
        t,
        t.messages[0].index,
        require_completed=True,
    )


def test_group_has_shared_source_and_distinct_calls():
    t = session([({"order_id": "A-1"}, "ok"), ({"order_id": "A-2"}, "ok")])
    claims = extract(t, [{"order_id": "A-1"}, {"order_id": "A-2"}])
    assert len({c.text for c in claims}) == 1
    assert len({c.group_id for c in claims}) == 1
    assert [f.verdict.value for f in check(t, claims)] == ["backed", "backed"]


def test_one_call_cannot_back_two_actions_in_same_group():
    t = session([({"order_id": "A-1"}, "ok")])
    findings = check(t, extract(t, [{"order_id": "A-1"}, {"order_id": "A-2"}]))
    assert [f.verdict.value for f in findings] == ["backed", "phantom"]


def test_failed_retry_does_not_hide_other_failed_action():
    t = session([({"order_id": "A-1"}, "error"), ({"order_id": "A-1"}, "ok"), ({"order_id": "A-2"}, "error")])
    findings = check(t, extract(t, [{"order_id": "A-1"}, {"order_id": "A-2"}]))
    assert [f.verdict.value for f in findings] == ["backed", "masked_failure"]


def test_repeated_summary_can_reference_same_successful_calls():
    t = session([({"order_id": "A-1"}, "ok"), ({"order_id": "A-2"}, "ok")])
    claims = extract(t, [{"order_id": "A-1"}, {"order_id": "A-2"}])
    from dataclasses import replace

    claims += [replace(c, group_id="later-summary") for c in claims]
    assert all(f.verdict.value == "backed" for f in check(t, claims))


@pytest.mark.parametrize("actions", [[], [None], [{"order_id": "A-1", "amount": [1, 2]}]])
def test_invalid_groups_rejected(actions):
    with pytest.raises(ValueError):
        extract(session([]), actions)


def test_separate_items_also_share_distinct_call_group():
    t = session([({"order_id": "A-1"}, "ok")])
    raw = {
        "claims": [{"completed": True, "tool": "refund", "args": {"order_id": oid}} for oid in ("A-1", "A-2")]
    }
    claims = parse_claims(json.dumps(raw), t, t.messages[0].index, require_completed=True)
    assert [f.verdict.value for f in check(t, claims)] == ["backed", "phantom"]
