import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = runpy.run_path(str(ROOT / "scripts" / "run_llm_bench.py"))


def valid_case(case_id="valid"):
    return {
        "id": case_id,
        "trace": {
            "tools": [{"name": "send", "side_effect": True}],
            "events": [{"type": "message", "role": "assistant", "content": "Sent it."}],
        },
        "claims": [{"text": "Sent it.", "tool": "send", "args": {}, "message_index": 0}],
        "expected": [{"verdict": "phantom", "tool": "send"}],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("trace", None),
        ("trace", {"events": [{"type": "private-invalid-event"}]}),
        ("claims", None),
        ("claims", {}),
        ("claims", [None]),
        ("claims", [{"text": "Sent it.", "tool": "send", "message_index": 10}]),
        ("claims", [{"text": "Sent it.", "tool": "send", "args": []}]),
        ("expected", None),
        ("expected", {}),
        ("expected", [None]),
        ("expected", [{"tool": "send"}]),
        ("expected", [{"tool": "send", "verdict": "private-invalid-verdict"}]),
        ("expected", [{"tool": [], "verdict": "phantom"}]),
        ("expected", [{"tool": " ", "verdict": "phantom"}]),
        ("expected", [{"tool": "send", "verdict": "backed"}]),
        ("expected", []),
        ("domain", []),
        ("domain", 1),
    ],
)
def test_all_cases_are_checked_before_model_requests_or_output(tmp_path, monkeypatch, capsys, field, value):
    main = RUNNER["main"]

    def unexpected(*args, **kwargs):
        raise AssertionError("Invalid fixture reached model evaluation")

    monkeypatch.setitem(main.__globals__, "evaluate", unexpected)
    folder = tmp_path / "cases"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps(valid_case()))
    invalid = valid_case("private-invalid-case")
    invalid[field] = value
    (folder / "b.json").write_text(json.dumps(invalid))
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as caught:
        main(["--endpoint", "http://unused", "local", "--cases", str(folder), "--out", str(out)])
    assert caught.value.code == 2
    assert not out.exists()
    captured = capsys.readouterr()
    assert not captured.out
    assert "Invalid benchmark fixture" in captured.err
    assert "private" not in captured.err and "Traceback" not in captured.err


@pytest.mark.parametrize("missing", ["trace", "claims", "expected"])
def test_required_fixture_fields_are_not_silently_defaulted(missing):
    case = valid_case()
    del case[missing]
    with pytest.raises((KeyError, ValueError)):
        RUNNER["validate_case"](case)


def test_preflight_accepts_frozen_cases_and_preserves_source_data():
    # Every bundled fixture and every generated example fixture goes through the
    # same deterministic preflight without inference or rewriting the evidence.
    paths = sorted((ROOT / "src/didyoureally/benchmark").glob("*.json"))
    paths += sorted((ROOT / "examples").glob("**/*.json"))
    count = 0
    for path in paths:
        case = json.loads(path.read_text())
        if not isinstance(case, dict) or not {"trace", "claims", "expected"} <= case.keys():
            continue
        original = copy.deepcopy(case)
        RUNNER["validate_case"](case)
        assert case == original, path
        count += 1
    assert count >= 102


def test_case_filter_preflights_only_selected_fixtures(tmp_path, monkeypatch):
    main = RUNNER["main"]
    calls = []

    def evaluate(case, base_url, model, **kwargs):
        calls.append(case["id"])
        return {
            "case": case["id"],
            "model": model,
            "domain": "email",
            "expected": case["expected"],
            "got": case["expected"],
            "passed": True,
        }

    monkeypatch.setitem(main.__globals__, "evaluate", evaluate)
    folder = tmp_path / "cases"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps(valid_case()))
    (folder / "b.json").write_text(json.dumps({"id": "unselected"}))
    assert (
        main(
            [
                "--endpoint",
                "http://unused",
                "local",
                "--cases",
                str(folder),
                "--case",
                "valid",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 0
    )
    assert calls == ["valid"]
