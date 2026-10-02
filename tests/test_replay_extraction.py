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
        '{"claims": []}',
        "must not consume",
    ]
    saved = {"model": "model", "raw_responses": replies, "responses": [{}] * 3}
    assert replay_module["replay"](case(), saved)["outcome"] == "recovery_required"


def test_replay_does_not_invent_missing_provider_reply(replay_module):
    saved = {"model": "model", "raw_responses": [], "responses": []}
    assert replay_module["replay"](case(), saved)["outcome"] == "missing_saved_reply"
