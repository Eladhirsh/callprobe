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
    extractor, calls = run(t, [[item()], [item()]])
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
    extractor, _ = run(t, [[item()], [item(args=args)]])
    assert check(t, extractor.extract(t))[0].verdict.value == verdict


def test_argument_invention_fails_after_one_retry():
    extractor, calls = run(trace(), [[item()], [item(args={"amount": 65})], [item(args={"amount": 65})]])
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
    extractor, calls = run(trace(), [[item()], [], []])
    with pytest.raises(ExtractionError) as caught:
        extractor.extract(trace())
    assert caught.value.reason == "lost_action_mapping"
    assert len(calls) == 3


def test_detail_retry_cannot_drop_stated_amount():
    t = trace("Refunded $40.")
    extractor, calls = run(
        t, [[item()], [item(args={"amount": "$40", "order_id": "private-order"})], [item()]]
    )
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
    replies = iter([[item()], [item(args={"amount": "$40"})]] * 2)

    def transport(*args):
        return {"choices": [{"message": {"content": json.dumps({"claims": next(replies)})}}]}

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
