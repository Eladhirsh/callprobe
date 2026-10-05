import json

import pytest

from didyoureally import Trace, check
from didyoureally.extract import (
    SOURCE_REPAIR_PROMPT,
    SYSTEM_PROMPT,
    ExtractionError,
    LLMExtractor,
    _argument_feedback,
    _argument_issues,
)
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


@pytest.mark.parametrize("invalid", [None, "it", "context-only-id"])
@pytest.mark.parametrize("actual_id", ["review_17", "wrong-event"])
@pytest.mark.parametrize("short_timestamp", [True, False])
def test_source_repair_uses_focused_instructions_and_keeps_grounded_details(
    invalid, actual_id, short_timestamp
):
    target = 'Moved "review_17" to October 12, 2026 at 9:15 AM with UTC offset -04:00.'
    t = Trace.from_dict(
        {
            "tools": [{"name": "reschedule_event"}],
            "events": [
                {"type": "message", "role": "user", "content": "Move context-only-id."},
                {
                    "type": "tool_call",
                    "id": "private-call-id",
                    "tool": "reschedule_event",
                    "args": {"event_id": actual_id, "starts_at": "2026-10-12T09:15:00-04:00"},
                    "status": "ok",
                },
                {"type": "message", "role": "assistant", "content": target},
            ],
        }
    )

    def payload(args):
        return {"claims": [{"completed": True, "tool": "reschedule_event", "args": args}]}

    # The bad timestamp omits the explicit offset; the source anchor must keep
    # both the full timestamp and the separately grounded event ID during repair.
    first = {
        "event_id": "review_17",
        "starts_at": "October 12, 2026 09:15" if short_timestamp else "2026-10-12T09:15:00-04:00",
        "id": invalid,
    }
    corrected = {"event_id": "review_17", "starts_at": "2026-10-12T09:15:00-04:00"}
    requests = []
    missing_id = {"starts_at": corrected["starts_at"]}
    claims = LLMExtractor(
        transport=transport([payload(first), payload(missing_id), payload(corrected)], requests)
    ).extract(t)
    assert claims[0].args == corrected
    assert check(t, claims)[0].verdict.value == ("backed" if actual_id == "review_17" else "contradicted")
    assert len(requests) == 3
    assert requests[1]["messages"][0]["content"] == SYSTEM_PROMPT
    repair = requests[2]
    assert repair["messages"][0]["content"] == SOURCE_REPAIR_PROMPT
    assert len(repair["messages"]) == 2
    prompt = repair["messages"][1]["content"]
    assert '"event_id": "review_17"' in prompt
    assert "UTC offset -04:00" in prompt
    for hidden in ("context-only-id", "private-call-id", "wrong-event"):
        assert hidden not in json.dumps(repair)


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
        payload([{"order_id": "B-1"}]),
    ]
    requests = []
    with pytest.raises(ExtractionError) as caught:
        LLMExtractor(transport=transport(replies, requests)).extract(trace())
    assert caught.value.reason == "lost_source_detail"
    assert len(requests) == 3


@pytest.mark.parametrize(
    "final,reason",
    [
        ({}, "invalid_claims"),
        ({"claims": []}, "lost_source_detail"),
        (
            {"claims": [{"completed": True, "tool": "issue_refund", "args": {"order_id": "B-2"}}]},
            "lost_source_detail",
        ),
        (
            {"claims": [{"completed": True, "tool": "issue_refund", "args": {"order_id": "invented"}}]},
            "source_mismatch",
        ),
    ],
)
def test_final_detail_recovery_cannot_pass_incomplete_or_invalid_output(final, reason):
    replies = [
        {
            "claims": [
                {"completed": True, "tool": "issue_refund", "args": {"order_id": "B-1", "amount": None}}
            ]
        },
        {"claims": [{"completed": True, "tool": "issue_refund", "args": {}}]},
        final,
    ]
    requests = []
    with pytest.raises(ExtractionError) as caught:
        LLMExtractor(transport=transport(replies, requests)).extract(trace())
    assert caught.value.reason == reason
    assert len(requests) == 3


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

        replies = [payload(bad), payload(repaired), payload(repaired)]
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
