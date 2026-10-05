"""Suite syntax must fail before mock outcomes or expected decisions can change."""

import json
from pathlib import Path

import pytest

from callprobe.agent_io import read_agent_json
from callprobe.agent_pilot import pilot_suite


def suite_text():
    raw = pilot_suite()
    raw["cases"] = raw["cases"][:1]
    return json.dumps(raw)


def ambiguous_suite(kind):
    text = suite_text()
    before, after = {
        "root": ('"version": 1', '"version": 0, "version": 1'),
        "escaped": ('"version": 1', '"vers\\u0069on": 0, "version": 1'),
        "outcome": ('"status": "ok"', '"status": "error", "status": "ok"'),
        "decision": ('"type": "call"', '"type": "no_call", "type": "call"'),
        "result": ('"result":', '"result": {"private-marker": "first"}, "result":'),
    }[kind]
    assert before in text
    result = text.replace(before, after, 1)
    # A last-value-wins parser would silently accept the original valid suite.
    assert json.loads(result) == json.loads(text)
    return result.encode()


def nonfinite_suite(token):
    raw = json.loads(suite_text())
    raw["cases"][0]["tools"][0]["outcomes"][0]["result"] = {"metric": "NUMBER_PLACEHOLDER"}
    return json.dumps(raw).replace('"NUMBER_PLACEHOLDER"', token.decode()).encode()


INVALID_SUITES = [
    *[
        (ambiguous_suite(kind), "duplicate JSON keys")
        for kind in ("root", "escaped", "outcome", "decision", "result")
    ],
    *[
        (nonfinite_suite(value), "nonfinite")
        for value in (b"NaN", b"Infinity", b"-Infinity", b"1e999", b"-1e999")
    ],
    (b'\xff{"version":1}', "invalid agent input JSON"),
    (b"[" * 2000 + b"0" + b"]" * 2000, "invalid agent"),
]


@pytest.mark.parametrize(
    "data,reason",
    INVALID_SUITES,
    ids=[
        "root-key",
        "escaped-key",
        "outcome-status",
        "decision-type",
        "nested-result",
        "nan",
        "infinity",
        "negative-infinity",
        "overflow",
        "negative-overflow",
        "invalid-utf8",
        "deep-array",
    ],
)
def test_agent_run_rejects_ambiguous_json_before_requests_or_output(
    tmp_path, monkeypatch, capsys, data, reason
):
    pytest.importorskip("didyoureally")
    from didyoureally import extract

    from callprobe import agent_cli
    from callprobe.cli import main

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid suite must not construct a model client")

    monkeypatch.setattr(agent_cli, "ChatClient", forbidden)
    monkeypatch.setattr(extract, "LLMExtractor", forbidden)
    source = tmp_path / "suite.json"
    source.write_bytes(data)
    out = tmp_path / "new-parent" / "results"
    assert (
        main(
            [
                "agent",
                "run",
                "--suite",
                str(source),
                "--model",
                "scripted-agent",
                "--extractor-model",
                "scripted-extractor",
                "--out",
                str(out),
            ]
        )
        == 2
    )
    assert not out.parent.exists()
    assert source.read_bytes() == data
    error = capsys.readouterr().err
    assert reason in error
    assert "private-marker" not in error
    assert "Traceback" not in error


def test_strict_agent_json_preserves_valid_nested_values(tmp_path):
    raw = {
        "version": 1,
        "values": [None, True, False, -12, 1.25e-3, "NaN", "Infinity", "1e999", "café"],
        "first": {"same_key": 1},
        "second": {"same_key": 2},
    }
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert read_agent_json(path) == raw


def test_valid_agent_suite_hash_is_unchanged(tmp_path):
    from callprobe.agent_session import load_agent_suite, suite_hash

    path = tmp_path / "suite.json"
    path.write_text(suite_text(), encoding="utf-8")
    assert suite_hash(load_agent_suite(read_agent_json(path))) == suite_hash(
        load_agent_suite(json.loads(suite_text()))
    )


def test_missing_agent_input_remains_a_filesystem_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_agent_json(Path(tmp_path / "missing.json"))


def test_decoder_recursion_error_is_an_input_error(tmp_path, monkeypatch):
    from callprobe import agent_io

    path = tmp_path / "nested.json"
    path.write_text("[]")

    def exhausted(*args, **kwargs):
        raise RecursionError("private decoder diagnostic")

    monkeypatch.setattr(agent_io.json, "loads", exhausted)
    with pytest.raises(ValueError, match="^invalid agent input JSON$"):
        read_agent_json(path)
