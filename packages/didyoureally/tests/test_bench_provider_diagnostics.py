import json
import runpy
from pathlib import Path

import pytest

RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "run_llm_bench.py"))


def case():
    return {
        "id": "provider-diagnostic",
        "claims": [],
        "expected": [],
        "trace": {
            "tools": [{"name": "send_email"}],
            "events": [{"type": "message", "role": "assistant", "content": "Sent!"}],
        },
    }


@pytest.mark.parametrize("mode", ["default", "staged"])
@pytest.mark.parametrize(
    "response,reason",
    [
        (None, "provider_error"),
        ({}, "provider_error"),
        ({"choices": []}, "provider_error"),
        ({"choices": [None]}, "provider_error"),
        ({"choices": [{"message": None}]}, "provider_error"),
        ({"choices": [{"message": {"refusal": "private refusal"}}]}, "provider_refusal"),
        ({"choices": [{"finish_reason": "length"}]}, "unfinished_response"),
        ({"choices": [{"finish_reason": "content_filter", "message": {}}]}, "unfinished_response"),
        ({"error": {"message": "private error"}}, "provider_error"),
    ],
)
def test_recorder_preserves_extractor_diagnostics_and_received_response(mode, response, reason):
    bodies = []

    def transport(url, headers, body):
        bodies.append(body)
        return response

    row = RUNNER["evaluate"](case(), "unused", "model", transport=transport, extraction_mode=mode)
    assert not row["passed"]
    assert row["error"] == "ExtractionError"
    assert row["error_reason"] == reason
    assert row["error_message_index"] == 0
    assert "claims" not in row and "got" not in row
    assert len(bodies) == len(row["responses"]) == 1
    assert row["raw_responses"] == [None]
    assert row["responses"][0]["request_sha256"] == RUNNER["request_digest"](bodies[0])
    assert "private" not in json.dumps(row)


def test_staged_detail_refusal_does_not_save_a_partial_success():
    replies = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"claims": [{"completed": true, "tool": "send_email", "args": {}}]}'
                        }
                    }
                ]
            },
            {"choices": [{"message": {"refusal": "private refusal"}}]},
        ]
    )
    row = RUNNER["evaluate"](
        case(), "unused", "model", extraction_mode="staged", transport=lambda *args: next(replies)
    )
    assert row["error_reason"] == "provider_refusal" and not row["passed"]
    assert "claims" not in row
    assert len(row["responses"]) == len(row["raw_responses"]) == 2
    assert row["raw_responses"][-1] is None
    assert "private" not in json.dumps(row)


def test_transport_failure_is_not_a_received_response():
    def transport(*args):
        raise OSError("private connection error")

    row = RUNNER["evaluate"](case(), "unused", "model", transport=transport)
    assert row["error_reason"] == "provider_error" and not row["passed"]
    assert row["responses"] == row["raw_responses"] == []
    assert "private" not in json.dumps(row)


@pytest.mark.parametrize("mode", ["default", "staged"])
def test_successful_reply_keeps_capture_metadata(mode):
    response = {
        "model": "served-model",
        "usage": {"total_tokens": 12},
        "choices": [{"message": {"content": '{"claims": []}'}, "finish_reason": "stop"}],
    }
    row = RUNNER["evaluate"](
        case(), "unused", "model", extraction_mode=mode, transport=lambda *args: response
    )
    assert row["passed"] and "error" not in row
    assert row["raw_responses"] == ['{"claims": []}']
    assert row["responses"][0]["model"] == "served-model"
    assert row["responses"][0]["usage"] == {"total_tokens": 12}
    assert row["responses"][0]["finish_reason"] == "stop"
