import copy
import json

import pytest

from didyoureally import Claim, GivenClaims, ToolCall, Trace, check, load_trace
from didyoureally.cli import main


def native():
    return {
        "id": "session",
        "tools": [{"name": "send_email", "side_effect": True}],
        "events": [
            {"type": "tool_call", "id": "first", "tool": "send_email", "args": {"to": "Dana"}},
            {"type": "message", "role": "assistant", "content": "Sent to Dana."},
        ],
    }


@pytest.mark.parametrize("value", [None, [], "trace", 0])
def test_native_root_must_be_an_object(value):
    with pytest.raises(ValueError, match="trace must be an object"):
        Trace.from_dict(value)


@pytest.mark.parametrize("field", ["tools", "events"])
@pytest.mark.parametrize("value", [None, {}, "invalid"])
def test_native_collections_must_be_arrays(field, value):
    data = native()
    data[field] = value
    with pytest.raises(ValueError, match="must be an array"):
        load_trace(data)


@pytest.mark.parametrize("field", ["tools", "events"])
@pytest.mark.parametrize("value", [None, [], "invalid"])
def test_native_collection_entries_must_be_objects(field, value):
    data = native()
    data[field] = [value]
    with pytest.raises(ValueError, match="must be an object"):
        load_trace(data)


@pytest.mark.parametrize("value", [None, [], [["to", "Mallory"], ["to", "Dana"]], False, ""])
def test_native_arguments_and_reviewed_claims_cannot_coerce_pairs(value):
    data = native()
    data["events"][0]["args"] = value
    with pytest.raises(ValueError, match="args must be an object"):
        load_trace(data)
    with pytest.raises(ValueError, match="claim args must be an object"):
        GivenClaims([{"text": "Sent to Dana.", "tool": "send_email", "args": value}])


@pytest.mark.parametrize("value", [0, 1, None, "false", "", []])
def test_side_effect_requires_a_boolean_before_it_can_suppress_a_write(value):
    data = native()
    data["tools"][0]["side_effect"] = value
    data["events"] = data["events"][:1]
    with pytest.raises(ValueError, match="side_effect must be a boolean"):
        load_trace(data)


@pytest.mark.parametrize("flag,expected", [(True, ["unmentioned"]), (False, [])])
def test_explicit_boolean_side_effect_metadata_still_controls_silent_actions(flag, expected):
    data = native()
    data["tools"][0]["side_effect"] = flag
    assert [f.verdict.value for f in check(load_trace(data), [])] == expected


@pytest.mark.parametrize("same_definition", [True, False])
def test_duplicate_tool_definitions_cannot_replace_write_classification(same_definition):
    data = native()
    data["tools"].append({"name": "send_email", "side_effect": same_definition})
    with pytest.raises(ValueError, match="unique names"):
        load_trace(data)
    with pytest.raises(ValueError, match="unique names"):
        load_trace({"messages": [], "tools": data["tools"]})


@pytest.mark.parametrize("value", [None, 0, False, "", " "])
def test_names_and_call_ids_are_nonempty_strings(value):
    for collection, key in [("tools", "name"), ("events", "tool"), ("events", "id")]:
        data = native()
        data[collection][0][key] = value
        with pytest.raises(ValueError, match="nonempty string"):
            load_trace(data)


def test_duplicate_call_ids_cannot_hide_an_unreported_second_send():
    data = native()
    second = {**data["events"][0], "args": {"to": "Mallory"}}
    data["events"].insert(1, second)
    with pytest.raises(ValueError, match="unique IDs"):
        load_trace(data)
    second["id"] = "second"
    trace = load_trace(data)
    findings = check(trace, [Claim("Sent to Dana.", "send_email", {"to": "Dana"}, 2)])
    assert [(f.verdict.value, f.call.id) for f in findings] == [
        ("backed", "first"),
        ("unmentioned", "second"),
    ]


def test_direct_or_mutated_traces_are_checked_for_duplicate_call_identity():
    trace = Trace(id="direct", calls=[ToolCall("same", "send_email", {}), ToolCall("same", "send_email", {})])
    with pytest.raises(ValueError, match="unique IDs"):
        check(trace, [])
    trace = load_trace(native())
    trace.calls.append(copy.deepcopy(trace.calls[0]))
    with pytest.raises(ValueError, match="unique IDs"):
        check(trace, [])


def test_generated_ids_are_stable_and_cannot_collide_with_explicit_ids():
    data = native()
    del data["events"][0]["id"]
    data["events"].insert(1, {"type": "tool_call", "tool": "send_email", "args": {}})
    trace = load_trace(data)
    assert [c.id for c in trace.calls] == ["call_0", "call_1"]
    data["events"][1]["id"] = "call_0"
    with pytest.raises(ValueError, match="unique IDs"):
        load_trace(data)


@pytest.mark.parametrize(
    "field,value",
    [("role", None), ("role", "Assistant"), ("role", []), ("content", None), ("content", []), ("content", 0)],
)
def test_malformed_messages_fail_before_silent_omission_or_attribute_errors(field, value):
    data = native()
    data["events"][1][field] = value
    with pytest.raises(ValueError, match="event 1"):
        load_trace(data)


@pytest.mark.parametrize(
    "field,value", [("parameters", []), ("parameters", None), ("description", None), ("description", {})]
)
def test_tool_definition_fields_have_explicit_shapes(field, value):
    data = native()
    data["tools"][0][field] = value
    with pytest.raises(ValueError, match="tool 0"):
        load_trace(data)


def test_valid_roles_empty_arguments_and_conservative_unknown_tools_round_trip():
    data = {
        "events": [
            *[
                {"type": "message", "role": role, "content": ""}
                for role in ["system", "developer", "user", "assistant", "tool"]
            ],
            {"type": "tool_call", "tool": "unlisted_write"},
        ]
    }
    trace = load_trace(data)
    assert trace.calls[0].args == {} and trace.calls[0].status == "ok"
    assert trace.is_side_effect("unlisted_write") is True
    assert Trace.from_dict(trace.to_dict()) == trace
    assert [f.verdict.value for f in check(trace, [])] == ["unmentioned"]


def test_cli_invalid_native_record_does_not_abort_valid_later_files(tmp_path, capsys):
    bad = native()
    bad["events"][1]["content"] = None
    good = native()
    good["claims"] = [
        {"text": "Sent to Dana.", "tool": "send_email", "args": {"to": "Dana"}, "message_index": 1}
    ]
    paths = [tmp_path / "bad.json", tmp_path / "good.json"]
    for path, data in zip(paths, [bad, good], strict=True):
        path.write_text(json.dumps(data))
    assert main(["check", *map(str, paths), "--format", "json"]) == 2
    output = capsys.readouterr().out
    first, end = json.JSONDecoder().raw_decode(output)
    second = json.loads(output[end:])
    assert first["status"] == "invalid_input" and first["summary"] is None
    assert second["status"] == "complete" and second["summary"]["backed"] == 1
