"""Distinct grouped actions need a joint assignment, including vague claims."""

from itertools import permutations

import pytest

from didyoureally import Claim, Trace, check


def session(calls):
    return Trace.from_dict(
        {
            "tools": [{"name": "send_email"}, {"name": "archive_file"}],
            "events": [
                {
                    "type": "tool_call",
                    "id": name,
                    "tool": "send_email",
                    "args": args,
                    "status": status,
                }
                for name, args, status in calls
            ]
            + [{"type": "message", "role": "assistant", "content": "I completed these actions."}],
        }
    )


def grouped(trace, args, message_index=None, group_id="actions"):
    return [
        Claim(
            text="I completed these actions.",
            tool="send_email",
            args=arg,
            message_index=trace.messages[-1].index if message_index is None else message_index,
            group_id=group_id,
        )
        for arg in args
    ]


@pytest.mark.parametrize("reverse_claims", [False, True])
@pytest.mark.parametrize("reverse_calls", [False, True])
def test_vague_action_does_not_take_specific_actions_only_call(reverse_claims, reverse_calls):
    calls = [("dana", {"to": "Dana"}, "ok"), ("priya", {"to": "Priya"}, "ok")]
    args = [{}, {"to": "Priya"}]
    trace = session(calls[::-1] if reverse_calls else calls)
    findings = check(trace, grouped(trace, args[::-1] if reverse_claims else args))
    assert [f.verdict.value for f in findings] == ["backed", "backed"]
    assert {f.call.id for f in findings} == {"dana", "priya"}
    assert next(f.call.id for f in findings if f.claim.args) == "priya"


@pytest.mark.parametrize("claim_order", list(permutations(range(3))))
@pytest.mark.parametrize("call_order", list(permutations(range(3))))
def test_joint_assignment_handles_overlapping_constraints(claim_order, call_order):
    calls = [
        ("only_a", {"a": 1, "b": 0}, "ok"),
        ("both", {"a": 1, "b": 1}, "ok"),
        ("only_b", {"a": 0, "b": 1}, "ok"),
    ]
    args = [{"a": 1}, {"b": 1}, {"a": 1, "b": 0}]
    trace = session([calls[i] for i in call_order])
    findings = check(trace, grouped(trace, [args[i] for i in claim_order]))
    assert [f.verdict.value for f in findings] == ["backed"] * 3
    assert len({f.call.id for f in findings}) == 3
    assert not any(f.unchecked for f in findings)


def test_shortage_reserves_specific_evidence_without_reusing_it():
    trace = session([("priya", {"to": "Priya"}, "ok")])
    findings = check(trace, grouped(trace, [{}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["phantom", "backed"]
    assert findings[1].call.id == "priya"


def test_wrong_recipient_stays_contradicted():
    trace = session([("dana", {"to": "Dana"}, "ok"), ("lee", {"to": "Lee"}, "ok")])
    findings = check(trace, grouped(trace, [{}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["backed", "contradicted"]
    assert findings[1].mismatches[0].claimed == "Priya"


@pytest.mark.parametrize("reverse", [False, True])
def test_failed_call_is_reserved_for_compatible_specific_claim(reverse):
    trace = session([("dana", {"to": "Dana"}, "ok"), ("priya", {"to": "Priya"}, "error")])
    args = [{}, {"to": "Priya"}]
    findings = check(trace, grouped(trace, args[::-1] if reverse else args))
    by_args = {bool(f.claim.args): f for f in findings}
    assert by_args[False].verdict.value == "backed"
    assert by_args[True].verdict.value == "masked_failure"
    assert by_args[True].call.id == "priya"


def test_extending_assignment_to_errors_can_reassign_successful_claim():
    # A constrained claim with no successful alternative must reclaim the
    # success from another equally specific claim that can use a failed call.
    trace = session(
        [
            ("success", {"a": 1, "b": 1}, "ok"),
            ("failed", {"a": 1, "b": 0}, "error"),
        ]
    )
    findings = check(trace, grouped(trace, [{"a": 1}, {"b": 1}]))
    assert [f.verdict.value for f in findings] == ["masked_failure", "backed"]
    assert [f.call.id for f in findings] == ["failed", "success"]


def test_compatible_failures_do_not_displace_available_successes():
    trace = session(
        [
            ("first", {"to": "Dana"}, "ok"),
            ("second", {"to": "Dana"}, "ok"),
            ("failed", {"to": "Dana"}, "error"),
        ]
    )
    findings = check(trace, grouped(trace, [{"to": "Dana"}, {"to": "Dana"}]))
    assert [f.verdict.value for f in findings] == ["backed", "backed"]
    assert {f.call.id for f in findings} == {"first", "second"}


def test_retry_success_and_other_failure_remain_distinct():
    trace = session(
        [
            ("retry-error", {"to": "Dana"}, "error"),
            ("retry-ok", {"to": "Dana"}, "ok"),
            ("other-error", {"to": "Priya"}, "error"),
        ]
    )
    findings = check(trace, grouped(trace, [{}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["backed", "masked_failure"]
    assert [f.call.id for f in findings] == ["retry-ok", "other-error"]


def test_missing_arguments_remain_unchecked():
    trace = session([("dana", {"to": "Dana"}, "ok"), ("missing", {}, "ok")])
    findings = check(trace, grouped(trace, [{}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["backed", "backed"]
    assert findings[1].call.id == "missing"
    assert findings[1].unchecked == ["to"]


def test_unmentioned_extra_success_still_reported():
    trace = session(
        [
            ("dana", {"to": "Dana"}, "ok"),
            ("priya", {"to": "Priya"}, "ok"),
            ("lee", {"to": "Lee"}, "ok"),
        ]
    )
    findings = check(trace, grouped(trace, [{}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["backed", "backed", "unmentioned"]
    assert len({f.call.id for f in findings}) == 3


def test_group_id_is_scoped_to_message_and_future_calls_cannot_back_earlier_claims():
    trace = Trace.from_dict(
        {
            "events": [
                {"type": "tool_call", "id": "dana", "tool": "send_email", "args": {"to": "Dana"}},
                {"type": "message", "role": "assistant", "content": "I sent both emails."},
                {"type": "tool_call", "id": "priya", "tool": "send_email", "args": {"to": "Priya"}},
                {"type": "message", "role": "assistant", "content": "Now I sent both emails."},
            ]
        }
    )
    args = [{}, {"to": "Priya"}]
    earlier = grouped(trace, args, message_index=1)
    later = grouped(trace, args, message_index=3)
    findings = check(trace, earlier + later)
    assert [f.verdict.value for f in findings] == ["backed", "phantom", "backed", "backed"]
    assert all(f.call is None or f.call.index < f.claim.message_index for f in findings)


def test_different_tools_in_one_group_do_not_compete():
    trace = Trace.from_dict(
        {
            "events": [
                {"type": "tool_call", "id": "mail", "tool": "send_email", "args": {}},
                {"type": "tool_call", "id": "file", "tool": "archive_file", "args": {}},
                {"type": "message", "role": "assistant", "content": "I sent it and archived it."},
            ]
        }
    )
    claims = grouped(trace, [{}, {}])
    claims[1].tool = "archive_file"
    findings = check(trace, claims)
    assert [f.verdict.value for f in findings] == ["backed", "backed"]
    assert [f.call.id for f in findings] == ["mail", "file"]


def test_unmatched_fallback_cannot_steal_later_claims_reserved_call():
    trace = session([("priya", {"to": "Priya"}, "ok"), ("dana", {"to": "Dana"}, "ok")])
    findings = check(trace, grouped(trace, [{"to": "Lee"}, {"to": "Priya"}]))
    assert [f.verdict.value for f in findings] == ["contradicted", "backed"]
    assert [f.call.id for f in findings] == ["dana", "priya"]
