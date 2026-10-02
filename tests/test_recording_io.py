import json
from pathlib import Path

import pytest

from callprobe.client import Completion
from callprobe.models import Call, RunConfig
from callprobe.recording_io import read_recordings
from callprobe.recordings import RecordedCompletion


def _minimal_doc():
    return {
        "schema_version": 1,
        "config": {
            "model": "demo-model",
            "pads": [0],
            "repeats": 1,
            "temperature": 0.0,
            "max_tokens": 64,
        },
        "records": [
            {"task_id": "t1", "completion": {}},
        ],
    }


def _write(tmp_path, obj, name="recording.json"):
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _write_raw(tmp_path, text, name="recording.json", encoding="utf-8"):
    path = tmp_path / name
    if encoding is None:
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return path


def test_minimal_document_builds_runconfig_and_recorded_completion(tmp_path):
    config, records = read_recordings(_write(tmp_path, _minimal_doc()), suite_label="demo")
    assert isinstance(config, RunConfig)
    assert config.model == "demo-model"
    assert config.endpoint == "recorded://local"
    assert config.suite == "demo"
    assert config.pads == [0]
    assert config.repeats == 1
    assert config.temperature == 0.0
    assert config.max_tokens == 64
    assert config.quantization is None
    assert config.selected_task_ids is None
    # No inference of generation settings or provenance beyond what was in the doc.
    assert config.callprobe_version is None
    assert config.suite_hash is None
    assert config.suite_name is None
    assert config.task_ids is None
    assert config.scoring_version is None

    assert len(records) == 1
    rec = records[0]
    assert isinstance(rec, RecordedCompletion)
    assert rec.task_id == "t1"
    assert rec.pad == 0 and rec.repeat == 0
    assert isinstance(rec.completion, Completion)
    assert rec.completion.calls == []
    assert rec.completion.content == ""
    assert rec.completion.reasoning == ""
    assert rec.completion.error is None
    assert rec.completion.finish_reason == ""
    assert rec.completion.prompt_tokens == 0
    assert rec.completion.completion_tokens == 0
    assert rec.completion.latency_ms == 0.0


def test_full_document_populates_all_optional_fields(tmp_path):
    doc = _minimal_doc()
    doc["config"]["quantization"] = "q4_0"
    doc["config"]["selected_task_ids"] = ["t1", "t2"]
    doc["records"] = [{
        "task_id": "t1",
        "pad": 4,
        "repeat": 2,
        "completion": {
            "calls": [{
                "name": "do_thing",
                "arguments": {"n": 3, "nested": {"k": [1, 2]}},
                "id": "call_x",
                "raw_arguments": '{"n":3}',
                "parse_error": None,
            }],
            "content": "ok",
            "reasoning": "think",
            "error": None,
            "finish_reason": "stop",
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "latency_ms": 42.5,
        },
    }]
    config, records = read_recordings(_write(tmp_path, doc), suite_label="suite-x")
    assert config.quantization == "q4_0"
    assert config.selected_task_ids == ["t1", "t2"]
    assert config.suite == "suite-x"

    rec = records[0]
    assert rec.pad == 4 and rec.repeat == 2
    completion = rec.completion
    assert completion.content == "ok"
    assert completion.reasoning == "think"
    assert completion.finish_reason == "stop"
    assert completion.prompt_tokens == 11
    assert completion.completion_tokens == 7
    assert completion.latency_ms == 42.5

    call = completion.calls[0]
    assert isinstance(call, Call)
    assert call.id == "call_x"
    assert call.name == "do_thing"
    assert call.arguments == {"n": 3, "nested": {"k": [1, 2]}}
    assert call.raw_arguments == '{"n":3}'
    assert call.parse_error is None


def test_abstention_with_error_is_preserved_verbatim(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {"error": "timeout", "latency_ms": 25.0}
    _, records = read_recordings(_write(tmp_path, doc), suite_label="demo")
    assert records[0].completion.error == "timeout"
    assert records[0].completion.latency_ms == 25.0
    assert records[0].completion.calls == []


def test_malformed_call_evidence_round_trips(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {
        "calls": [{
            "name": "get_order_status",
            "raw_arguments": "{oops",
            "parse_error": "Expecting property name",
        }],
        "finish_reason": "tool_calls",
    }
    _, records = read_recordings(_write(tmp_path, doc), suite_label="demo")
    call = records[0].completion.calls[0]
    assert call.name == "get_order_status"
    assert call.raw_arguments == "{oops"
    assert call.parse_error == "Expecting property name"
    assert call.arguments == {}
    assert call.id is None


def test_path_can_be_string_or_path(tmp_path):
    path = _write(tmp_path, _minimal_doc())
    config, records = read_recordings(str(path), suite_label="demo")
    assert config.model == "demo-model"
    assert len(records) == 1


def test_input_bytes_are_not_mutated(tmp_path):
    path = _write(tmp_path, _minimal_doc())
    before = path.read_bytes()
    read_recordings(path, suite_label="demo")
    assert path.read_bytes() == before


def test_omitted_completion_fields_match_explicit_defaults(tmp_path):
    omitted = _minimal_doc()
    omitted["records"][0]["completion"] = {}

    explicit = _minimal_doc()
    explicit["records"][0]["completion"] = {
        "calls": [], "content": "", "reasoning": "", "error": None,
        "finish_reason": "", "prompt_tokens": 0, "completion_tokens": 0,
        "latency_ms": 0.0,
    }
    _, left = read_recordings(_write(tmp_path, omitted, "a.json"), suite_label="demo")
    _, right = read_recordings(_write(tmp_path, explicit, "b.json"), suite_label="demo")
    assert left[0].completion == right[0].completion


def test_file_not_found_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_recordings(tmp_path / "missing.json", suite_label="demo")


def test_invalid_utf8_has_safe_diagnostic(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe\xfd not utf-8")
    with pytest.raises(ValueError, match="must be UTF-8"):
        read_recordings(path, suite_label="demo")


def test_invalid_json_syntax_is_rejected(tmp_path):
    path = _write_raw(tmp_path, "{not json")
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_root_must_be_an_object(tmp_path):
    path = _write_raw(tmp_path, "[]")
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_rejects_nonfinite_number_tokens(tmp_path, literal):
    text = (
        '{"schema_version":1,"config":{"model":"m","pads":[0],"repeats":1,'
        f'"temperature":{literal},"max_tokens":1}},'
        '"records":[{"task_id":"t","completion":{}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_rejects_overflow_float_literal(tmp_path):
    text = (
        '{"schema_version":1,"config":{"model":"m","pads":[0],"repeats":1,'
        '"temperature":1e400,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_rejects_nonfinite_number_inside_arguments(tmp_path):
    text = (
        '{"schema_version":1,"config":{"model":"m","pads":[0],"repeats":1,'
        '"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{"calls":[{"name":"x",'
        '"arguments":{"n":Infinity}}]}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_rejects_overflow_float_inside_arguments(tmp_path):
    text = (
        '{"schema_version":1,"config":{"model":"m","pads":[0],"repeats":1,'
        '"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{"calls":[{"name":"x",'
        '"arguments":{"n":2e400}}]}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_rejects_duplicate_keys_at_root(tmp_path):
    text = (
        '{"schema_version":1,"schema_version":1,'
        '"config":{"model":"m","pads":[0],"repeats":1,"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


def test_rejects_duplicate_keys_deep_inside_arguments(tmp_path):
    text = (
        '{"schema_version":1,'
        '"config":{"model":"m","pads":[0],"repeats":1,"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{"calls":[{"name":"x",'
        '"arguments":{"a":1,"a":2}}]}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError):
        read_recordings(path, suite_label="demo")


@pytest.mark.parametrize("version", [0, 2, 1.0, True, False, "1", None])
def test_rejects_wrong_schema_version(tmp_path, version):
    doc = _minimal_doc()
    doc["schema_version"] = version
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_missing_schema_version(tmp_path):
    doc = _minimal_doc()
    del doc["schema_version"]
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_missing_config(tmp_path):
    doc = _minimal_doc()
    del doc["config"]
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_missing_records(tmp_path):
    doc = _minimal_doc()
    del doc["records"]
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_empty_records(tmp_path):
    doc = _minimal_doc()
    doc["records"] = []
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_unknown_root_field(tmp_path):
    doc = _minimal_doc()
    doc["mystery_root"] = 1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_unknown_config_field(tmp_path):
    doc = _minimal_doc()
    doc["config"]["mystery_config"] = 1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_unknown_record_field(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["mystery_record"] = 1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_unknown_completion_field(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"]["mystery_completion"] = 1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_unknown_call_field(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {
        "calls": [{"name": "x", "mystery_call_field": 1}],
    }
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_missing_required_record_completion(tmp_path):
    doc = _minimal_doc()
    del doc["records"][0]["completion"]
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_missing_required_call_name(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {"calls": [{"arguments": {}}]}
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("field,value", [
    ("schema_version", True),
    ("schema_version", 1.0),
])
def test_schema_version_is_strict(tmp_path, field, value):
    doc = _minimal_doc()
    doc[field] = value
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("field", ["repeats", "max_tokens"])
def test_rejects_boolean_in_config_int(tmp_path, field):
    doc = _minimal_doc()
    doc["config"][field] = True
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("field", ["pad", "repeat"])
def test_rejects_boolean_in_record_coordinate(tmp_path, field):
    doc = _minimal_doc()
    doc["records"][0][field] = True
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_rejects_boolean_in_completion_counters(tmp_path, field):
    doc = _minimal_doc()
    doc["records"][0]["completion"][field] = True
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_boolean_pad_in_config_pads(tmp_path):
    doc = _minimal_doc()
    doc["config"]["pads"] = [True]
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("value", ["", 0, 1.0])
def test_rejects_invalid_model(tmp_path, value):
    doc = _minimal_doc()
    doc["config"]["model"] = value
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("pads", [[], [-1], [0, 0], [0, 1, 1]])
def test_rejects_invalid_pads(tmp_path, pads):
    doc = _minimal_doc()
    doc["config"]["pads"] = pads
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("value", [0, -1])
def test_rejects_non_positive_repeats(tmp_path, value):
    doc = _minimal_doc()
    doc["config"]["repeats"] = value
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("value", [0, -5])
def test_rejects_non_positive_max_tokens(tmp_path, value):
    doc = _minimal_doc()
    doc["config"]["max_tokens"] = value
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_negative_temperature(tmp_path):
    doc = _minimal_doc()
    doc["config"]["temperature"] = -0.1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_string_temperature(tmp_path):
    doc = _minimal_doc()
    doc["config"]["temperature"] = "0"
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("value", [[], [""], ["x", "x"]])
def test_rejects_invalid_selected_task_ids(tmp_path, value):
    doc = _minimal_doc()
    doc["config"]["selected_task_ids"] = value
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_negative_record_pad(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["pad"] = -1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_negative_record_repeat(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["repeat"] = -1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_blank_task_id(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["task_id"] = ""
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


@pytest.mark.parametrize("task_id", [123, None, [], {}])
def test_rejects_non_string_task_id(tmp_path, task_id):
    doc = _minimal_doc()
    doc["records"][0]["task_id"] = task_id
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_negative_prompt_tokens(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"]["prompt_tokens"] = -1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_negative_latency_ms(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"]["latency_ms"] = -0.1
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_non_object_completion(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = []
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_non_list_calls(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {"calls": "not a list"}
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_non_object_call(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {"calls": ["string instead of object"]}
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_rejects_non_object_arguments(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {
        "calls": [{"name": "x", "arguments": "not an object"}],
    }
    with pytest.raises(ValueError):
        read_recordings(_write(tmp_path, doc), suite_label="demo")


def test_diagnostics_hide_user_keys_values_and_private_internals(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {
        "secret_user_key": "secret_payload_value",
    }
    with pytest.raises(ValueError) as excinfo:
        read_recordings(_write(tmp_path, doc), suite_label="demo")
    message = str(excinfo.value)
    for forbidden in (
        "secret_user_key",
        "secret_payload_value",
        "_Document",
        "_ConfigModel",
        "_Record",
        "_Completion",
        "_Call",
        "_DuplicateKey",
        "_InvalidNumber",
    ):
        assert forbidden not in message


def test_duplicate_key_diagnostic_hides_user_key(tmp_path):
    text = (
        '{"schema_version":1,'
        '"config":{"model":"m","pads":[0],"repeats":1,"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{"calls":[{"name":"x",'
        '"arguments":{"super_secret_arg":1,"super_secret_arg":2}}]}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError) as excinfo:
        read_recordings(path, suite_label="demo")
    assert "super_secret_arg" not in str(excinfo.value)


def test_nonfinite_diagnostic_hides_user_values(tmp_path):
    text = (
        '{"schema_version":1,'
        '"config":{"model":"m","pads":[0],"repeats":1,"temperature":0,"max_tokens":1},'
        '"records":[{"task_id":"t","completion":{"calls":[{"name":"x",'
        '"arguments":{"radius":NaN}}]}}]}'
    )
    path = _write_raw(tmp_path, text)
    with pytest.raises(ValueError) as excinfo:
        read_recordings(path, suite_label="demo")
    message = str(excinfo.value)
    assert "radius" not in message
    assert "NaN" not in message


def test_preserves_arguments_without_coercion(tmp_path):
    doc = _minimal_doc()
    doc["records"][0]["completion"] = {
        "calls": [{
            "name": "x",
            "arguments": {"a": 1, "b": "two", "c": [3, 4], "d": None, "e": True},
        }],
    }
    _, records = read_recordings(_write(tmp_path, doc), suite_label="demo")
    args = records[0].completion.calls[0].arguments
    assert args == {"a": 1, "b": "two", "c": [3, 4], "d": None, "e": True}
    # Booleans survive as booleans, not coerced to 1.
    assert args["e"] is True
    assert args["d"] is None


def test_many_records_preserve_order_and_identity(tmp_path):
    doc = _minimal_doc()
    doc["config"]["pads"] = [0, 4]
    doc["config"]["repeats"] = 3
    doc["records"] = [
        {"task_id": f"t-{i}", "pad": pad, "repeat": repeat, "completion": {}}
        for i, (pad, repeat) in enumerate([(0, 0), (4, 1), (0, 2)])
    ]
    _, records = read_recordings(_write(tmp_path, doc), suite_label="demo")
    assert [(r.task_id, r.pad, r.repeat) for r in records] == [
        ("t-0", 0, 0), ("t-1", 4, 1), ("t-2", 0, 2),
    ]


def test_runconfig_has_recorded_endpoint_regardless_of_suite_label(tmp_path):
    config, _ = read_recordings(_write(tmp_path, _minimal_doc()), suite_label="anything")
    assert config.endpoint == "recorded://local"
    assert config.suite == "anything"



def test_excessively_nested_json_is_a_safe_value_error(tmp_path):
    path = _write_raw(tmp_path, '[' * 2000 + '"PRIVATE_VALUE"' + ']' * 2000)
    with pytest.raises(ValueError, match="recording document") as caught:
        read_recordings(path, suite_label="demo")
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize("value", [" ", "\t\n"])
def test_whitespace_only_model_is_rejected(tmp_path, value):
    doc = _minimal_doc()
    doc['config']['model'] = value
    with pytest.raises(ValueError, match="schema validation"):
        read_recordings(_write(tmp_path, doc), suite_label="demo")
