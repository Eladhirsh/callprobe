import json
from pathlib import Path

import pytest

from didyoureally import GivenClaims, Trace, Verdict, bench, check, from_openai_messages, load_trace
from didyoureally.cli import main
from didyoureally.extract import LLMExtractor, parse_claims
from didyoureally.matcher import values_agree

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


# ---- benchmark ----------------------------------------------------------


def test_bundled_benchmark_passes_with_labeled_claims():
    result = bench.run()
    assert len(result.cases) == 82
    failing = [c.case_id for c in result.cases if not c.passed]
    assert not failing, bench.render(result)
    tp, fp, fn = result.detection()
    assert fp == 0 and fn == 0 and tp > 0


# ---- value comparison ---------------------------------------------------


@pytest.mark.parametrize(
    "claimed,actual",
    [
        ("$40", 40.0),
        ("$1,250.00", 1250),
        ("40 USD", 40),
        (12, "12"),
        ("Sam", "sam@acme.com"),
        ("  Tuesday ", "tuesday"),
        (["Sam"], ["sam@acme.com", "x@y.com"]),
        ("A-1001", "a-1001"),
    ],
)
def test_values_agree(claimed, actual):
    assert values_agree(claimed, actual)


@pytest.mark.parametrize(
    "claimed,actual",
    [
        ("$40", 400),
        ("Priya", "dana.k@acme.com"),
        ("acct_123", "ord_123"),
        ("Thursday", "Friday"),
        (True, False),
        (["Sam", "Lee"], ["sam@acme.com"]),
    ],
)
def test_values_disagree(claimed, actual):
    assert not values_agree(claimed, actual)


def test_renamed_argument_is_matched_by_value():
    trace = Trace.from_dict(
        {
            "id": "t",
            "events": [
                {"type": "tool_call", "id": "c1", "tool": "issue_refund", "args": {"amt": 40}},
                {"type": "message", "role": "assistant", "content": "Refunded $40."},
            ],
        }
    )
    [f] = check(
        trace,
        GivenClaims(
            [{"text": "Refunded $40", "tool": "issue_refund", "args": {"amount": "$40"}, "message_index": 1}]
        ).claims,
    )
    assert f.verdict is Verdict.BACKED and not f.unchecked


def test_unverifiable_detail_is_reported_not_passed_silently():
    trace = Trace.from_dict(
        {
            "id": "t",
            "events": [
                {"type": "tool_call", "id": "c1", "tool": "issue_refund", "args": {"amount_cents": 4000}},
                {"type": "message", "role": "assistant", "content": "Refunded $40."},
            ],
        }
    )
    [f] = check(
        trace,
        GivenClaims([{"text": "Refunded $40", "tool": "issue_refund", "args": {"amount": "$40"}}]).claims,
    )
    assert f.verdict is Verdict.BACKED
    assert f.unchecked == ["amount"]


# ---- OpenAI adapter -----------------------------------------------------


def test_openai_adapter_detects_errors_and_read_only_tools():
    trace = load_trace(json.loads((EXAMPLES / "openai_masked_failure.json").read_text()))
    by_tool = {c.tool: c for c in trace.calls}
    assert by_tool["cancel_subscription"].status == "error"
    assert by_tool["get_subscription"].status == "ok"
    assert not trace.is_side_effect("get_subscription")
    assert trace.is_side_effect("cancel_subscription")
    assert len(trace.assistant_messages()) == 1


def test_openai_adapter_bare_message_list():
    trace = from_openai_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "x",
                        "type": "function",
                        "function": {"name": "send_email", "arguments": '{"to": "a@b.c"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "x", "content": "sent"},
            {"role": "assistant", "content": [{"type": "text", "text": "Sent it."}]},
        ]
    )
    assert trace.calls[0].args == {"to": "a@b.c"} and trace.calls[0].status == "ok"
    assert trace.assistant_messages()[0].content == "Sent it."


# ---- LLM extractor (no network) -----------------------------------------


def test_llm_extractor_parses_fenced_json_and_sanitizes():
    trace = load_trace(json.loads((EXAMPLES / "openai_masked_failure.json").read_text()))
    trace.assistant_messages()[0].content += " I escalated this."
    idx = trace.assistant_messages()[0].index
    reply = (
        "```json\n"
        + json.dumps(
            {
                "claims": [
                    {
                        "text": "cancelled",
                        "completed": True,
                        "tool": "cancel_subscription",
                        "args": {"subscription_id": "sub_9"},
                        "message_index": idx,
                    },
                    {"text": "escalated", "completed": True, "tool": None, "args": {}, "message_index": 999},
                ]
            }
        )
        + "\n```"
    )
    seen = {}

    def fake_transport(url, headers, body):
        seen["url"], seen["body"] = url, body
        return {"choices": [{"message": {"content": reply}}]}

    claims = LLMExtractor(
        base_url="http://local/v1", model="m", api_key="k", transport=fake_transport
    ).extract(trace)
    assert seen["url"] == "http://local/v1/chat/completions"
    assert seen["body"]["temperature"] == 0
    assert claims[0].tool == "cancel_subscription" and claims[0].message_index == idx
    assert (
        claims[1].tool is None and claims[1].message_index == idx
    )  # target index is assigned by the application

    [masked, phantom] = check(trace, claims)
    assert masked.verdict is Verdict.MASKED_FAILURE
    assert phantom.verdict is Verdict.PHANTOM


def test_parse_claims_rejects_non_json():
    with pytest.raises(ValueError):
        parse_claims("sorry, I can't", Trace(id="t"))


# ---- CLI ----------------------------------------------------------------


def test_cli_exit_codes(tmp_path, capsys):
    case = bench.default_cases_dir() / "02_wrong_amount.json"
    assert main(["check", str(case)]) == 1
    assert "Contradicted" in capsys.readouterr().out

    honest = bench.default_cases_dir() / "01_honest_refund.json"
    assert main(["check", str(honest)]) == 0

    silent = bench.default_cases_dir() / "06_silent_side_effect.json"
    assert main(["check", str(silent)]) == 0
    assert main(["check", str(silent), "--fail-on", "unmentioned"]) == 1

    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": 1}')
    assert main(["check", str(bad)]) == 2


def test_cli_json_output(capsys):
    case = bench.default_cases_dir() / "04_masked_failure.json"
    main(["check", str(case), "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["masked_failure"] == 1
    assert out["findings"][0]["call"]["status"] == "error"


@pytest.mark.parametrize(
    "claimed,actual,expected",
    [
        ("40 cents", "$0.40", True),
        ("40 cents", "$40", False),
        ("40 EUR", "40 USD", False),
        ("40 EUR", "€40", True),
        ("20%", "$20", False),
        ("20 percent", "20%", True),
        ("$100", 100.40, False),
        ("$100.40", 100.40, True),
        ("report.csv", "report.csv.bak", False),
        ("ORDER-100", "ORDER-1000", False),
        ("Dana", "dana.k@example.com", True),
        ("Dana", "danab@example.com", False),
        (True, 1, False),
        ("40 widgets", 40, False),
    ],
)
def test_comparison_preserves_units_precision_and_identity(claimed, actual, expected):
    assert values_agree(claimed, actual) is expected


def test_unrelated_equal_value_cannot_verify_an_argument():
    trace = Trace.from_dict(
        {
            "id": "units",
            "events": [
                {
                    "type": "tool_call",
                    "id": "c1",
                    "tool": "issue_refund",
                    "args": {"amount_cents": 40, "order_id": 40},
                },
                {"type": "message", "role": "assistant", "content": "I refunded $40."},
            ],
        }
    )
    [finding] = check(
        trace,
        GivenClaims(
            [
                {
                    "text": "I refunded $40",
                    "tool": "issue_refund",
                    "args": {"amount": "$40"},
                    "message_index": 1,
                }
            ]
        ).claims,
    )
    assert finding.unchecked == ["amount"]


def test_benchmark_has_honest_controls_and_matches_generator():
    import runpy

    source = runpy.run_path(str(EXAMPLES.parent / "scripts" / "build_benchmark.py"))
    cases = source["CASES"]
    honest = [c for c in cases if all(e["verdict"] == "backed" for e in c["expected"])]
    assert len(honest) * 3 >= len(cases)
    assert len({c["id"] for c in cases}) == 82
    for case in cases:
        bundled = json.loads((bench.default_cases_dir() / f"{case['id']}.json").read_text())
        assert bundled == source["build"](case)


def test_extractor_sees_conversation_context_but_not_call_arguments():
    from didyoureally.extract import build_user_prompt

    trace = Trace.from_dict(
        {
            "id": "context",
            "events": [
                {"type": "message", "role": "user", "content": "Please refund order A-30."},
                {
                    "type": "tool_call",
                    "id": "secret-call",
                    "tool": "issue_refund",
                    "args": {"internal_note": "SECRET_TRACE_DETAIL"},
                },
                {"type": "message", "role": "assistant", "content": "I took care of it."},
            ],
        }
    )
    prompt = build_user_prompt(trace)
    assert "Please refund order A-30" in prompt
    assert "I took care of it" in prompt
    assert "SECRET_TRACE_DETAIL" not in prompt
    assert "secret-call" not in prompt
