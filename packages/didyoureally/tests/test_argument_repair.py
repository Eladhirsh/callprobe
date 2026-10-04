import json

import pytest

from didyoureally import Trace
from didyoureally.extract import ExtractionError, LLMExtractor, _argument_feedback, _argument_issues
from didyoureally.staged import StagedExtractor


def trace():
    return Trace.from_dict(
        {
            "tools": [{"name": "issue_refund", "side_effect": True}],
            "events": [
                {"type": "message", "role": "user", "content": "Private context: refund $12345."},
                {
                    "type": "tool_call",
                    "id": "secret-call",
                    "tool": "issue_refund",
                    "args": {"amount": 54321},
                    "status": "ok",
                },
                {"type": "message", "role": "assistant", "content": "Refunded B-1 and B-2."},
            ],
        }
    )


def transport(replies, requests):
    stream = iter(replies)

    def send(url, headers, body):
        requests.append(json.loads(json.dumps(body)))
        return {"choices": [{"message": {"content": json.dumps(next(stream))}}]}

    return send


def test_field_feedback_identifies_group_members_without_rejected_values():
    raw = json.dumps(
        {
            "claims": [
                {
                    "completed": True,
                    "tool": "issue_refund",
                    "actions": [
                        {"order_id": "B-1", "amount": None},
                        {"order_id": "B-2", "amount": "private-rejected-value"},
                    ],
                }
            ]
        }
    )
    issues = _argument_issues(raw, trace(), 2)
    assert [(i["action_index"], i["argument"], i["reason"]) for i in issues] == [
        (0, "amount", "null_argument"),
        (1, "amount", "source_mismatch"),
    ]
    feedback = _argument_feedback(raw, trace(), 2)
    for value in ("private-rejected-value", "12345", "54321", "secret-call"):
        assert value not in feedback


@pytest.mark.parametrize("mode", ["default", "staged"])
def test_null_repair_retains_distinct_actions_and_hides_context(mode):
    args = [{"order_id": "B-1"}, {"order_id": "B-2"}]
    bad = [{**a, "amount": None} for a in args]
    if mode == "default":

        def payload(values):
            return {"claims": [{"completed": True, "tool": "issue_refund", "actions": values}]}

        replies = [payload(bad), payload(args)]
        cls = LLMExtractor
    else:

        def payload(values):
            return {"details": [{"action_id": 0, "args": a} for a in values]}

        replies = [
            {"claims": [{"completed": True, "tool": "issue_refund", "args": {}}]},
            payload(bad),
            payload(args),
        ]
        cls = StagedExtractor
    requests = []
    claims = cls(transport=transport(replies, requests)).extract(trace())
    assert [c.args for c in claims] == args
    assert claims[0].group_id == claims[1].group_id
    last = json.dumps(requests[-1])
    assert "Argument validation issues" in last
    assert "null_argument" in last
    for value in ("12345", "54321", "secret-call"):
        assert value not in last


def test_repair_cannot_discard_one_valid_group_member():
    def payload(args):
        return {"claims": [{"completed": True, "tool": "issue_refund", "actions": args}]}

    replies = [
        payload([{"order_id": "B-1", "amount": None}, {"order_id": "B-2", "amount": None}]),
        payload([{"order_id": "B-1"}]),
    ]
    requests = []
    with pytest.raises(ExtractionError) as caught:
        LLMExtractor(transport=transport(replies, requests)).extract(trace())
    assert caught.value.reason == "lost_source_detail"
    assert len(requests) == 2


def test_pronoun_repair_can_correct_a_misclassified_future_action():
    t = Trace.from_dict(
        {
            "tools": [{"name": "send_email"}],
            "events": [
                {"type": "message", "role": "assistant", "content": "I will send it to you tomorrow."},
            ],
        }
    )
    requests = []
    replies = [{"claims": [{"completed": True, "tool": "send_email", "args": {"to": "you"}}]}, {"claims": []}]
    assert LLMExtractor(transport=transport(replies, requests)).extract(t) == []
    assert len(requests) == 2
    assert '"role": "assistant"' not in json.dumps(requests[-1]["messages"])


@pytest.mark.parametrize("mode", ["default", "staged"])
@pytest.mark.parametrize("copies", [1, 2])
def test_repair_preserves_identical_action_multiplicity(mode, copies):
    t = Trace.from_dict(
        {
            "tools": [{"name": "send_email"}],
            "events": [{"type": "message", "role": "assistant", "content": "I sent two copies to Dana."}],
        }
    )
    bad = [{"to": "Dana", "subject": None}] * 2
    repaired = [{"to": "Dana"}] * copies
    if mode == "default":

        def payload(values):
            return {"claims": [{"completed": True, "tool": "send_email", "actions": values}]}

        replies = [payload(bad), payload(repaired)]
        cls = LLMExtractor
    else:

        def payload(values):
            return {"details": [{"action_id": 0, "args": a} for a in values]}

        replies = [
            {"claims": [{"completed": True, "tool": "send_email", "args": {}}]},
            payload(bad),
            payload(repaired),
        ]
        cls = StagedExtractor
    extractor = cls(transport=transport(replies, []))
    if copies == 1:
        with pytest.raises(ExtractionError) as caught:
            extractor.extract(t)
        assert caught.value.reason == "lost_source_detail"
    else:
        claims = extractor.extract(t)
        assert len(claims) == 2
        assert claims[0].group_id == claims[1].group_id


def test_source_anchor_matching_reassigns_overlapping_subsets():
    from didyoureally import Claim
    from didyoureally.extract import _preserves_source_details

    anchors = [
        {"tool": "send_email", "args": {"to": "Dana"}},
        {"tool": "send_email", "args": {"to": "Dana", "subject": "Receipt"}},
    ]
    claims = [
        Claim("Sent", "send_email", {"to": "Dana", "subject": "Receipt"}),
        Claim("Sent", "send_email", {"to": "Dana", "subject": "Update"}),
    ]
    assert _preserves_source_details(claims, anchors)
    assert _preserves_source_details(list(reversed(claims)), anchors)
    assert not _preserves_source_details(claims[:1], anchors)
    claims[1].tool = "other_tool"
    assert not _preserves_source_details(claims, anchors)
