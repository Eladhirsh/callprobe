from pathlib import Path

import pytest

from callprobe.run_config import load_run_config


def _write(tmp_path, text, name="run.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_full_valid_config_round_trips(tmp_path):
    path = _write(tmp_path, """
model: qwen2.5:7b
endpoint: http://localhost:11434/v1
suite: my-suite
pads: [0, 8, 16]
repeats: 3
temperature: 0.2
max_tokens: 4096
quant: q4_K_M
notes: nightly sweep
retries: 5
concurrency: 4
out: results/run.json
""")
    config, config_dir = load_run_config(str(path))
    assert config_dir == tmp_path
    assert config.model == "qwen2.5:7b"
    assert config.pads == [0, 8, 16]
    assert config.repeats == 3
    assert config.temperature == 0.2
    assert config.max_tokens == 4096
    assert config.retries == 5
    assert config.concurrency == 4
    assert config.out == "results/run.json"


def test_all_keys_optional(tmp_path):
    path = _write(tmp_path, "model: stub\n")
    config, _ = load_run_config(str(path))
    assert config.model == "stub"
    assert config.endpoint is None
    assert config.pads is None


def test_missing_file_is_actionable(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_run_config(str(tmp_path / "missing.yaml"))


@pytest.mark.parametrize("text", ["", "\n", "  \n"])
def test_empty_document_is_rejected(tmp_path, text):
    path = _write(tmp_path, text)
    with pytest.raises(ValueError, match="mapping"):
        load_run_config(str(path))


def test_nonmapping_document_is_rejected(tmp_path):
    path = _write(tmp_path, "- a\n- b\n")
    with pytest.raises(ValueError, match="mapping"):
        load_run_config(str(path))


def test_duplicate_keys_are_rejected(tmp_path):
    path = _write(tmp_path, "model: a\nmodel: b\n")
    with pytest.raises(ValueError, match="duplicate key"):
        load_run_config(str(path))


def test_unknown_field_is_rejected(tmp_path):
    path = _write(tmp_path, "model: stub\nweird_field: 1\n")
    with pytest.raises(ValueError, match="weird_field"):
        load_run_config(str(path))


@pytest.mark.parametrize("field", ["api_key", "target", "resume", "fail_under", "format", "quiet"])
def test_secret_or_out_of_scope_fields_are_rejected(tmp_path, field):
    path = _write(tmp_path, f"model: stub\n{field}: super-secret-value\n")
    with pytest.raises(ValueError) as excinfo:
        load_run_config(str(path))
    assert "super-secret-value" not in str(excinfo.value)
    assert field in str(excinfo.value)


def test_wrong_type_error_does_not_echo_value(tmp_path):
    path = _write(tmp_path, "model: stub\nmax_tokens: not-a-secret-but-a-string\n")
    with pytest.raises(ValueError) as excinfo:
        load_run_config(str(path))
    assert "not-a-secret-but-a-string" not in str(excinfo.value)
    assert "max_tokens" in str(excinfo.value)


@pytest.mark.parametrize("text", [
    "model: stub\nmax_tokens: 0\n",
    "model: stub\nmax_tokens: -1\n",
    "model: stub\nrepeats: 0\n",
    "model: stub\nconcurrency: 0\n",
    "model: stub\nretries: -1\n",
    "model: stub\npads: []\n",
    "model: stub\npads: [0, 0]\n",
    "model: stub\npads: [-1]\n",
    "model: stub\npads: [1.5]\n",
])
def test_invalid_ranges_are_rejected(tmp_path, text):
    path = _write(tmp_path, text)
    with pytest.raises(ValueError):
        load_run_config(str(path))


@pytest.mark.parametrize("text", [
    "model: stub\nmax_tokens: true\n",
    "model: stub\nrepeats: false\n",
    "model: stub\ntemperature: true\n",
    "model: stub\npads: [true]\n",
])
def test_booleans_are_rejected_for_numeric_fields(tmp_path, text):
    path = _write(tmp_path, text)
    with pytest.raises(ValueError):
        load_run_config(str(path))


@pytest.mark.parametrize("text", [
    "model: stub\ntemperature: .nan\n",
    "model: stub\ntemperature: .inf\n",
    "model: stub\ntemperature: -.inf\n",
])
def test_nan_and_infinity_are_rejected(tmp_path, text):
    path = _write(tmp_path, text)
    with pytest.raises(ValueError, match="finite"):
        load_run_config(str(path))


def test_model_must_be_a_string(tmp_path):
    path = _write(tmp_path, "model: 123\n")
    with pytest.raises(ValueError, match="model"):
        load_run_config(str(path))


def test_endpoint_not_coerced_from_number(tmp_path):
    path = _write(tmp_path, "model: stub\nendpoint: 4\n")
    with pytest.raises(ValueError, match="endpoint"):
        load_run_config(str(path))


@pytest.mark.parametrize("text", [
    "model: stub\n1: value\n",
    "model: stub\ntrue: value\n",
    "? [a, b]\n: value\n",
    "temperature: " + "9" * 400 + "\n",
])
def test_malformed_keys_and_oversized_number_raise_actionable_errors(tmp_path, text):
    with pytest.raises(ValueError, match="--config"):
        load_run_config(str(_write(tmp_path, text)))


@pytest.mark.parametrize("field", ["model", "endpoint", "suite", "out", "pads", "repeats", "temperature"])
def test_null_is_not_a_typed_setting(tmp_path, field):
    with pytest.raises(ValueError, match=field):
        load_run_config(str(_write(tmp_path, f"{field}: null\n")))


@pytest.mark.parametrize("field", ["model", "endpoint", "suite", "out"])
def test_required_string_values_cannot_be_blank(tmp_path, field):
    with pytest.raises(ValueError, match="blank"):
        load_run_config(str(_write(tmp_path, f'{field}: "  "\n')))


def test_unsupported_yaml_tag_does_not_echo_input(tmp_path):
    with pytest.raises(ValueError) as exc:
        load_run_config(str(_write(tmp_path, "notes: !secret-token private-value\n")))
    assert "secret-token" not in str(exc.value)
    assert "private-value" not in str(exc.value)
    assert "line 1" in str(exc.value)
