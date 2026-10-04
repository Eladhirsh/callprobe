import json

import pytest

from didyoureally import Trace, check
from didyoureally.cli import _extractor, build_parser
from didyoureally.extract import ExtractionError, LLMExtractor
from didyoureally.staged import StagedExtractor


def trace(text="All done.", status="ok"):
    return Trace.from_dict(
        {
            "tools": [
                {"name": "issue_refund", "side_effect": True},
                {"name": "lookup_invoice", "side_effect": False},
            ],
            "events": [
                {"type": "message", "role": "user", "content": "Refund $65 on private-order."},
                {
                    "type": "tool_call",
                    "id": "c1",
                    "tool": "issue_refund",
                    "args": {"amount": 400, "order_id": "trace-only-id"},
                    "result": {"secret": "tool-result-secret"},
                    "status": status,
                },
                {"type": "message", "role": "assistant", "content": text},
                {"type": "message", "role": "user", "content": "Future request must be absent."},
            ],
        }
    )


def item(tool="issue_refund", args=None, completed=True):
    return {"completed": completed, "tool": tool, "args": {} if args is None else args}


def detail(args=None, action_id=0):
    return json.dumps({"details": [{"action_id": action_id, "args": {} if args is None else args}]})


def run(t, replies):
    calls = []
    stream = iter(replies)

    def transport(url, headers, body):
        calls.append(json.loads(json.dumps(body)))
        payload = next(stream)
        content = payload if isinstance(payload, str) else json.dumps({"claims": payload})
        return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}

    return StagedExtractor(transport=transport, json_mode=True), calls


def test_stages_isolate_context_from_arguments_and_never_expose_call_evidence():
    t = trace()
    extractor, calls = run(t, [[item()], detail()])
    [claim] = extractor.extract(t)
    assert claim.args == {} and claim.message_index == 2
    assert check(t, [claim])[0].verdict.value == "backed"
    assert len(calls) == 2
    assert "private-order" in json.dumps(calls[0])
    assert "private-order" not in json.dumps(calls[1])
    for body in calls:
        assert body["response_format"] == {"type": "json_object"}
        assert "trace-only-id" not in json.dumps(body)
        assert "tool-result-secret" not in json.dumps(body)
        assert "Future request" not in json.dumps(body)


@pytest.mark.parametrize("mapping", [[], [item(completed=False)], [item("lookup_invoice")]])
def test_nonclaims_and_read_only_actions_do_not_request_arguments(mapping):
    extractor, calls = run(trace(), [mapping])
    assert extractor.extract(trace()) == []
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,text,args,verdict",
    [
        ("ok", "Refunded $40.", {"amount": "$40"}, "contradicted"),
        ("error", "All done.", {}, "masked_failure"),
    ],
)
def test_staged_claims_use_deterministic_verdicts(status, text, args, verdict):
    t = trace(text, status)
    extractor, _ = run(t, [[item()], detail(args)])
    assert check(t, extractor.extract(t))[0].verdict.value == verdict


def test_argument_invention_fails_after_one_retry():
    extractor, calls = run(trace(), [[item()], detail({"amount": 65}), detail({"amount": 65})])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "source_mismatch"
    assert len(calls) == 3
    assert "private-order" not in json.dumps(calls[-1])


def test_mapping_cannot_smuggle_arguments_to_detail_stage():
    extractor, calls = run(trace(), [[item(args={"amount": 65})], [item(args={"amount": 65})]])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "invalid_action_map"
    assert len(calls) == 2


def test_detail_stage_cannot_silently_lose_completed_action():
    extractor, calls = run(trace(), [[item()], '{"details": []}', '{"details": []}'])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "lost_action_mapping"
    assert len(calls) == 3


def test_detail_retry_cannot_drop_stated_amount():
    t = trace("Refunded $40.")
    extractor, calls = run(t, [[item()], detail({"amount": "$40", "order_id": "private-order"}), detail()])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(t)
    assert caught.value.reason == "lost_source_detail"
    assert len(calls) == 3


def test_cli_staged_is_opt_in():
    parser = build_parser()
    args = parser.parse_args(["check", "trace.json", "--extractor", "llm"])
    assert type(_extractor(args, {})) is LLMExtractor
    args = parser.parse_args(["check", "trace.json", "--extractor", "llm", "--extraction-mode", "staged"])
    assert isinstance(_extractor(args, {}), StagedExtractor)


def test_staged_provider_failure_has_safe_diagnostic():
    def transport(*args):
        raise OSError("secret provider error")

    with pytest.raises(ExtractionError) as caught:
        StagedExtractor(transport=transport).extract(trace())
    assert caught.value.reason == "provider_error"
    assert "secret" not in str(caught.value)


def test_public_cli_staged_check_and_benchmark(tmp_path, monkeypatch, capsys):
    from didyoureally import cli, extract

    t = trace("Refunded $40.")
    replies = iter([json.dumps({"claims": [item()]}), detail({"amount": "$40"})] * 2)

    def transport(*args):
        return {"choices": [{"message": {"content": next(replies)}}]}

    monkeypatch.setattr(extract, "_http_post", transport)
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(t.to_dict()))
    assert (
        cli.main(
            ["check", str(path), "--extractor", "llm", "--extraction-mode", "staged", "--format", "json"]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["findings"][0]["verdict"] == "contradicted"
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "case.json").write_text(
        json.dumps(
            {
                "id": "amount",
                "trace": t.to_dict(),
                "claims": [],
                "expected": [{"tool": "issue_refund", "verdict": "contradicted"}],
            }
        )
    )
    assert cli.main(["bench", "--llm", "--extraction-mode", "staged", "--cases", str(cases)]) == 0


@pytest.mark.parametrize(
    "reply",
    [
        detail(action_id=True),
        detail(action_id=-1),
        detail(action_id=1),
        detail(action_id="0"),
        '{"details": [{"action_id": 0, "args": {}, "tool": null}]}',
        '{"details": [{"action_id": 0, "args": {}, "completed": false}]}',
        '{"details": [{"action_id": 0, "action_id": 1, "args": {}}]}',
        '{"details": [{"action_id": 0, "args": null}]}',
    ],
)
def test_detail_stage_rejects_invalid_identity_and_protocol(reply):
    extractor, calls = run(trace(), [[item()], reply, reply])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "invalid_action_details"
    assert len(calls) == 3


def test_detail_stage_preserves_unavailable_action_identity():
    t = trace("Escalated the request.")
    extractor, _ = run(t, [[item(tool=None)], detail()])
    claims = extractor.extract(t)
    assert claims[0].tool is None
    assert check(t, claims)[0].verdict.value == "phantom"


def test_fixed_ids_preserve_groups_and_multiple_tools():
    t = trace("Refunded $40 and $50, then escalated the request.")
    replies = [
        [item(), item(tool=None)],
        json.dumps(
            {
                "details": [
                    {"action_id": 1, "args": {}},
                    {"action_id": 0, "args": {"amount": "$40"}},
                    {"action_id": 0, "args": {"amount": "$50"}},
                ]
            }
        ),
    ]
    extractor, _ = run(t, replies)
    claims = extractor.extract(t)
    assert [c.tool for c in claims] == [None, "issue_refund", "issue_refund"]
    assert claims[1].group_id == claims[2].group_id
    assert claims[1].group_id is not None
    assert [f.verdict.value for f in check(t, claims)] == ["phantom", "contradicted", "phantom"]


def test_detail_stage_cannot_omit_one_of_multiple_actions():
    extractor, _ = run(trace(), [[item(), item(tool=None)], detail(), detail()])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "lost_action_mapping"


@pytest.mark.parametrize("word", ["your", "you", "it", "them"])
def test_unresolved_recipient_is_repaired_without_becoming_an_anchor(word):
    t = Trace.from_dict(
        {
            "tools": [{"name": "send_email", "side_effect": True}],
            "events": [{"type": "message", "role": "assistant", "content": f"I sent the receipt to {word}."}],
        }
    )
    extractor, calls = run(t, [[item("send_email")], detail({"to": word}), detail()])
    [claim] = extractor.extract(t)
    assert claim.args == {}
    assert "unquoted pronoun" in calls[-1]["messages"][-1]["content"]
    assert "Preserve these literal" not in calls[-1]["messages"][-1]["content"]


@pytest.mark.parametrize("text", ['I removed "it".', "I removed `it`.", "I removed 'it'."])
def test_quoted_identifier_that_is_also_a_pronoun_is_preserved(text):
    t = Trace.from_dict(
        {
            "tools": [{"name": "delete_file", "side_effect": True}],
            "events": [{"type": "message", "role": "assistant", "content": text}],
        }
    )
    extractor, calls = run(t, [[item("delete_file")], detail({"path": "it"})])
    assert extractor.extract(t)[0].args == {"path": "it"}
    assert len(calls) == 2


def test_default_extractor_also_rejects_unresolved_recipient():
    t = Trace.from_dict(
        {
            "tools": [{"name": "send_email", "side_effect": True}],
            "events": [{"type": "message", "role": "assistant", "content": "I sent it to you."}],
        }
    )
    calls = []

    def transport(url, headers, body):
        calls.append(body)
        return {
            "choices": [{"message": {"content": json.dumps({"claims": [item("send_email", {"to": "you"})]})}}]
        }

    with pytest.raises(ExtractionError) as caught:
        LLMExtractor(transport=transport).extract(t)
    assert caught.value.reason == "unresolved_reference"
    assert len(calls) == 2
