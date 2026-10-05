import json

import pytest

from didyoureally import Claim, GivenClaims, Trace, check
from didyoureally.cli import main
from didyoureally.extract import LLMExtractor


def session():
    return Trace.from_dict(
        {
            "events": [
                {"type": "message", "role": "assistant", "content": "Sent!"},
                {"type": "tool_call", "id": "send", "tool": "send_email", "args": {}},
                {"type": "message", "role": "user", "content": "Thanks."},
                {"type": "message", "role": "assistant", "content": " "},
                {"type": "message", "role": "system", "content": "Sent!"},
                {"type": "message", "role": "assistant", "content": "Sent!"},
            ]
        }
    )


@pytest.mark.parametrize("value", [{}, "", None, False, (), {"claims": []}])
def test_supplied_claims_require_an_array_even_when_empty(value):
    with pytest.raises(ValueError, match="claims must be an array"):
        GivenClaims(value)


@pytest.mark.parametrize("value", [None, [], "Sent!", 1])
def test_supplied_claim_entries_require_objects(value):
    with pytest.raises(ValueError, match="claim must be an object"):
        GivenClaims([value])


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", None),
        ("text", ""),
        ("text", " "),
        ("text", 0),
        ("text", []),
        ("tool", ""),
        ("tool", " "),
        ("tool", False),
        ("tool", []),
        ("message_index", True),
        ("message_index", False),
        ("message_index", 1.0),
        ("message_index", "5"),
        ("message_index", -1),
        ("message_index", []),
        ("group_id", ""),
        ("group_id", " "),
        ("group_id", []),
        ("group_id", 0),
    ],
)
def test_claim_fields_are_validated_without_coercion(field, value):
    data = {"text": "Sent!", "tool": "send_email", "message_index": 5, field: value}
    with pytest.raises(ValueError):
        Claim.from_dict(data)
    with pytest.raises(ValueError):
        check(session(), [Claim(**data)])


@pytest.mark.parametrize("index", [1, 2, 3, 4, 999])
def test_explicit_claim_references_must_identify_nonempty_assistant_messages(index):
    trace = session()
    supplied = GivenClaims([{"text": "Sent!", "tool": "send_email", "message_index": index}])
    with pytest.raises(ValueError, match="identify a nonempty assistant message"):
        supplied.extract(trace)
    with pytest.raises(ValueError, match="identify a nonempty assistant message"):
        check(trace, supplied.claims)


@pytest.mark.parametrize("index,expected", [(0, ["phantom", "unmentioned"]), (5, ["backed"])])
def test_valid_claim_references_keep_tool_result_chronology(index, expected):
    trace = session()
    claims = GivenClaims([{"text": "Sent!", "tool": "send_email", "message_index": index}])
    assert [f.verdict.value for f in check(trace, claims.extract(trace))] == expected


@pytest.mark.parametrize("fields", [{}, {"message_index": None}])
@pytest.mark.parametrize("early", [True, False])
def test_unpositioned_claims_use_the_only_assistant_message_without_mutating_inputs(fields, early):
    data = session().to_dict()
    data["events"] = data["events"][:2] if early else data["events"][1:3]
    if not early:
        data["events"][-1] = {"type": "message", "role": "assistant", "content": "Sent!"}
    trace = Trace.from_dict(data)
    supplied = GivenClaims([{"text": "Sent!", "tool": "send_email", **fields}])
    expected = ["phantom", "unmentioned"] if early else ["backed"]
    assert [f.verdict.value for f in check(trace, supplied.claims)] == expected
    extracted = supplied.extract(trace)
    assert extracted[0].message_index == (0 if early else 1)
    assert supplied.claims[0].message_index is None
    assert [f.verdict.value for f in check(trace, extracted)] == expected


@pytest.mark.parametrize(
    "events", [[], [{"type": "message", "role": "user", "content": "Sent!"}], session().to_dict()["events"]]
)
def test_unpositioned_claims_require_an_unambiguous_assistant_source(events):
    trace = Trace.from_dict({"events": events})
    supplied = GivenClaims([Claim("Sent!", "send_email")])
    with pytest.raises(ValueError, match="exactly one nonempty assistant message"):
        supplied.extract(trace)
    with pytest.raises(ValueError, match="exactly one nonempty assistant message"):
        check(trace, supplied.claims)


def test_unpositioned_empty_claim_list_does_not_require_a_source_message():
    trace = Trace.from_dict({"events": []})
    assert GivenClaims([]).extract(trace) == []
    assert check(trace, []) == []


@pytest.mark.parametrize("tool", [None, "unknown_action"])
def test_unmapped_actions_remain_findings_instead_of_input_errors(tool):
    trace = Trace.from_dict({"events": [{"type": "message", "role": "assistant", "content": "Done!"}]})
    claims = GivenClaims([{"text": "Done!", "tool": tool, "message_index": 0}])
    assert [f.verdict.value for f in check(trace, claims.extract(trace))] == ["phantom"]


def test_explicit_empty_claims_are_valid_and_do_not_hide_unmentioned_calls():
    trace = session()
    claims = GivenClaims([]).extract(trace)
    assert [f.verdict.value for f in check(trace, claims)] == ["unmentioned"]


@pytest.mark.parametrize("claims", [{}, "", None, [None], [{}]])
def test_direct_matcher_rejects_invalid_claim_collections(claims):
    with pytest.raises(ValueError):
        check(session(), claims)


def test_revalidation_catches_claims_changed_after_loading():
    trace = session()
    claims = GivenClaims([Claim("Sent!", "send_email", message_index=5)])
    claims.claims[0].message_index = 999
    with pytest.raises(ValueError, match="assistant message"):
        claims.extract(trace)
    with pytest.raises(ValueError, match="assistant message"):
        check(trace, claims.claims)


@pytest.mark.parametrize("args", [[], {"amount": float("nan")}, {"amount": float("inf")}])
def test_direct_claim_arguments_cannot_bypass_object_and_finite_number_checks(args):
    with pytest.raises(ValueError):
        check(session(), [Claim("Sent!", "send_email", args, 5)])


@pytest.mark.parametrize("claims", [{}, "", [{"text": "Sent!", "tool": "send_email", "message_index": 999}]])
def test_invalid_embedded_claims_return_input_error_and_batch_continues(
    tmp_path, capsys, monkeypatch, claims
):
    bad, good = tmp_path / "bad.json", tmp_path / "good.json"
    bad.write_text(json.dumps({**session().to_dict(), "claims": claims}))
    good.write_text(
        json.dumps(
            {**session().to_dict(), "claims": [{"text": "Sent!", "tool": "send_email", "message_index": 5}]}
        )
    )

    def no_model(*args):
        raise AssertionError("Reviewed claims must not call an extraction model")

    monkeypatch.setattr(LLMExtractor, "extract", no_model)
    assert main(["check", str(bad), str(good), "--format", "json", "--fail-on", ""]) == 2
    output = capsys.readouterr().out
    first, end = json.JSONDecoder().raw_decode(output)
    second = json.loads(output[end:])
    assert first["status"] == "invalid_input" and first["summary"] is None
    assert second["status"] == "complete" and second["summary"]["backed"] == 1


def test_external_claim_file_is_validated_without_model_fallback(tmp_path, capsys):
    trace, claims = tmp_path / "trace.json", tmp_path / "claims.json"
    trace.write_text(json.dumps(session().to_dict()))
    claims.write_text("{}")
    assert main(["check", str(trace), "--claims", str(claims), "--format", "json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"


@pytest.mark.parametrize("index", [None, 0])
def test_duplicate_source_indices_in_direct_python_traces_are_ambiguous(index):
    trace = session()
    trace.messages[-1].index = trace.messages[0].index
    supplied = GivenClaims([Claim("Sent!", "send_email", message_index=index)])
    with pytest.raises(ValueError, match="assistant message"):
        supplied.extract(trace)
    with pytest.raises(ValueError, match="assistant message"):
        check(trace, supplied.claims)
