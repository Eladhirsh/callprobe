import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture
def replay_module(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    return runpy.run_path(str(root / "scripts/replay_extraction.py"))


def case():
    return {
        "id": "replay",
        "claims": [],
        "expected": [],
        "trace": {
            "tools": [{"name": "send_email"}],
            "events": [
                {"type": "message", "role": "user", "content": "Email private@example.com."},
                {"type": "message", "role": "assistant", "content": "Done."},
            ],
        },
    }


def test_recorded_reply_replays_without_network(replay_module):
    response = {"choices": [{"message": {"content": '{"claims": []}'}}]}
    saved = replay_module["evaluate"](case(), "unused", "model", transport=lambda *args: response)
    assert replay_module["replay"](case(), saved)["outcome"] == "unchanged"
    saved["claims"] = [{"tool": "wrong"}]
    assert replay_module["replay"](case(), saved)["outcome"] == "changed"


def test_replay_stops_before_consuming_later_message_reply_for_recovery(replay_module):
    replies = [
        json.dumps(
            {"claims": [{"completed": True, "tool": "send_email", "args": {"to": "private@example.com"}}]}
        ),
        '{"claims": [{"completed": true, "tool": null, "args": {}}]}',
        "must not consume",
    ]
    saved = {"model": "model", "raw_responses": replies, "responses": [{}] * 3}
    assert replay_module["replay"](case(), saved)["outcome"] == "recovery_required"


def test_replay_does_not_invent_missing_provider_reply(replay_module):
    saved = {"model": "model", "raw_responses": [], "responses": []}
    assert replay_module["replay"](case(), saved)["outcome"] == "missing_saved_reply"


def inputs(tmp_path, module):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "case.json").write_text(json.dumps(case()))
    response = {"choices": [{"message": {"content": '{"claims": []}'}}]}
    saved = module["evaluate"](case(), "unused", "model", transport=lambda *args: response)
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps(saved) + "\n")
    out = tmp_path / "replayed"
    return cases, records, out, saved


def run(module, cases, records, out):
    return module["main"](["--cases", str(cases), "--records", str(records), "--out", str(out)])


@pytest.mark.parametrize(
    "problem",
    [
        "empty_records",
        "empty_cases",
        "duplicate_case",
        "duplicate_record",
        "unknown_case",
        "staged",
        "baseline_error",
        "short_metadata",
        "long_metadata",
        "bad_metadata",
        "bad_reply",
        "missing_claims",
        "wrong_labels",
        "bad_model",
        "bool_repeat",
        "bad_endpoint",
        "duplicate_json_keys",
        "nonfinite",
        "invalid_utf8",
    ],
)
def test_bad_replay_inputs_fail_before_output(replay_module, tmp_path, capsys, problem):
    cases, records, out, saved = inputs(tmp_path, replay_module)
    if problem == "empty_records":
        records.write_text("\n")
    elif problem == "empty_cases":
        (cases / "case.json").unlink()
    elif problem == "duplicate_case":
        (cases / "copy.json").write_text(json.dumps(case()))
    elif problem == "duplicate_record":
        records.write_text((json.dumps(saved) + "\n") * 2)
    elif problem == "duplicate_json_keys":
        records.write_text('{"private":1,"private":2}')
    elif problem == "nonfinite":
        records.write_text('{"private":NaN}')
    elif problem == "invalid_utf8":
        records.write_bytes(b"\xffprivate")
    else:
        field, value = {
            "unknown_case": ("case", "missing"),
            "staged": ("extraction_mode", "staged"),
            "baseline_error": ("error", "private-provider-diagnostic"),
            "short_metadata": ("responses", []),
            "long_metadata": ("responses", [{}, {}]),
            "bad_metadata": ("responses", ["private-response"]),
            "bad_reply": ("raw_responses", [{}]),
            "missing_claims": ("claims", None),
            "wrong_labels": ("labeled_claims", [{"tool": "send_email"}]),
            "bad_model": ("model", None),
            "bool_repeat": ("repeat_index", True),
            "bad_endpoint": ("endpoint_id", []),
        }[problem]
        saved[field] = value
        records.write_text(json.dumps(saved))
    with pytest.raises(SystemExit) as caught:
        run(replay_module, cases, records, out)
    assert caught.value.code == 2
    assert not out.exists()
    captured = capsys.readouterr()
    assert not captured.out
    assert "private" not in captured.err


def test_replay_cli_preserves_repeats_and_endpoint_identity(replay_module, tmp_path):
    cases, records, out, saved = inputs(tmp_path, replay_module)
    rows = [{**saved, "repeat_index": i, "endpoint_id": "endpoint-1"} for i in (1, 2)]
    records.write_text("\n".join(json.dumps(row) for row in rows))
    assert run(replay_module, cases, records, out) == 0
    replayed = [json.loads(line) for line in (out / "records.jsonl").read_text().splitlines()]
    assert [row["repeat_index"] for row in replayed] == [1, 2]
    assert all(row["endpoint_id"] == "endpoint-1" for row in replayed)
    assert "does not establish full planned-run coverage" in (out / "report.md").read_text()


def test_missing_saved_reply_remains_a_failed_replay(replay_module, tmp_path):
    cases, records, out, saved = inputs(tmp_path, replay_module)
    saved.update(raw_responses=[], responses=[])
    records.write_text(json.dumps(saved))
    assert run(replay_module, cases, records, out) == 1
    assert json.loads((out / "records.jsonl").read_text())["outcome"] == "missing_saved_reply"


def test_replay_never_overwrites_existing_output(replay_module, tmp_path):
    cases, records, out, saved = inputs(tmp_path, replay_module)
    out.mkdir()
    sentinel = out / "report.md"
    sentinel.write_text("Keep this result")
    with pytest.raises(SystemExit) as caught:
        run(replay_module, cases, records, out)
    assert caught.value.code == 2
    assert sentinel.read_text() == "Keep this result"


def test_direct_replay_rejects_staged_records(replay_module):
    saved = {"model": "model", "extraction_mode": "staged", "raw_responses": [], "responses": []}
    with pytest.raises(ValueError, match="default extraction only"):
        replay_module["replay"](case(), saved)
