import json

import pytest

from didyoureally import Trace, check
from didyoureally.extract import LLMExtractor, parse_claims


def session():
    return Trace.from_dict(
        {
            "id": "timing",
            "events": [
                {"type": "message", "role": "assistant", "content": "Sent!"},
                {"type": "tool_call", "id": "c1", "tool": "send_email", "args": {}},
                {"type": "message", "role": "assistant", "content": "Sent now."},
            ],
        }
    )


def test_model_cannot_move_claim_past_later_call():
    trace = session()
    requests = []

    def transport(url, headers, body):
        requests.append(body)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "claims": [
                                    {
                                        "text": "Sent!" if len(requests) == 1 else "Sent now.",
                                        "completed": True,
                                        "tool": "send_email",
                                        "args": {},
                                        "message_index": 999,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    claims = LLMExtractor(transport=transport).extract(trace)
    assert [c.message_index for c in claims] == [0, 2]
    assert [f.verdict.value for f in check(trace, claims)] == ["phantom", "backed"]
    assert len(requests) == 2
    assert "TARGET assistant message_index=0" in requests[0]["messages"][1]["content"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"claims": "none"},
        {"claims": [None]},
        {"claims": [{"text": "Sent", "tool": "invented_tool", "args": {}}]},
        {"claims": [{"text": "Sent", "tool": "send_email", "args": []}]},
        {"claims": [{"text": "Sent", "args": {}}]},
    ],
)
def test_malformed_extraction_is_not_silent_success_or_phantom(payload):
    with pytest.raises(ValueError):
        parse_claims(json.dumps(payload), session(), target_index=0)


def test_unbound_invalid_index_is_rejected():
    with pytest.raises(ValueError, match="valid assistant message"):
        parse_claims(
            json.dumps(
                {"claims": [{"text": "Sent", "tool": "send_email", "args": {}, "message_index": 999}]}
            ),
            session(),
        )


@pytest.mark.parametrize(
    "claimed,actual,verdict",
    [
        ({"time": "10"}, {"time": "10:00"}, "backed"),
        ({"time": "2 pm"}, {"time": "14:00"}, "backed"),
        ({"time": "2 am"}, {"time": "14:00"}, "contradicted"),
        ({"amount": 40, "currency": "USD"}, {"amount": "40 EUR"}, "contradicted"),
        ({"amount": 40, "currency": "EUR"}, {"amount": "40 EUR"}, "backed"),
    ],
)
def test_argument_semantics(claimed, actual, verdict):
    from didyoureally.schema import Claim

    trace = Trace.from_dict(
        {
            "id": "args",
            "events": [
                {"type": "tool_call", "id": "c1", "tool": "act", "args": actual},
                {"type": "message", "role": "assistant", "content": "Done"},
            ],
        }
    )
    [finding] = check(trace, [Claim("Done", "act", claimed, 1)])
    assert finding.verdict.value == verdict
    assert not finding.unchecked


def test_duplicate_case_ids_are_rejected_before_extraction(tmp_path):
    from didyoureally import bench

    for name in ("case.json", "case 2.json"):
        (tmp_path / name).write_text(json.dumps({"id": "same"}))
    with pytest.raises(ValueError, match="Duplicate benchmark"):
        bench.run(tmp_path)


def test_target_prompt_excludes_future_assistant_messages():
    from didyoureally.extract import build_user_prompt

    prompt = build_user_prompt(session(), 0)
    assert "Sent now." not in prompt
    assert "Sent!" in prompt


def test_non_target_quote_is_rejected():
    with pytest.raises(ValueError, match="quote the target"):
        parse_claims(
            json.dumps({"claims": [{"text": "Sent now.", "tool": "send_email", "args": {}}]}),
            session(),
            target_index=0,
        )


def test_schema_repair_is_bounded():
    calls = []

    def transport(url, headers, body):
        calls.append(body)
        return {"choices": [{"message": {"content": "{}"}}]}

    with pytest.raises(ValueError):
        LLMExtractor(transport=transport).extract(session())
    assert len(calls) == 2


def test_read_only_claims_are_excluded_by_scope():
    trace = Trace.from_dict(
        {
            "id": "read",
            "tools": [{"name": "read_file", "side_effect": False}],
            "events": [{"type": "message", "role": "assistant", "content": "I read a.txt."}],
        }
    )
    assert (
        parse_claims(
            json.dumps(
                {"claims": [{"text": "I read a.txt.", "tool": "read_file", "args": {"path": "a.txt"}}]}
            ),
            trace,
            target_index=0,
        )
        == []
    )


@pytest.mark.parametrize(
    "script,honest_count,total",
    [
        ("build_context_validation.py", 8, 16),
        ("build_vague_validation.py", 12, 16),
        ("build_completion_validation.py", 20, 24),
    ],
)
def test_context_validation_labels_and_generator_match(monkeypatch, script, honest_count, total):
    import runpy
    from pathlib import Path

    from didyoureally import bench

    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    module = runpy.run_path(str(root / "scripts" / script))
    cases = list(module["cases"]())
    assert len(cases) == total
    assert sum(all(e["verdict"] == "backed" for e in c["expected"]) for c in cases) == honest_count
    for case in cases:
        assert json.loads((module["OUT"] / f"{case['id']}.json").read_text()) == case
    result = bench.run(module["OUT"])
    assert result.passed == total
