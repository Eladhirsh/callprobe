import json
import runpy
from pathlib import Path

PILOT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_local_file_pilot.py"))


def test_file_tool_real_success_and_missing_file(tmp_path):
    (tmp_path / "draft.txt").write_text("temporary")
    assert PILOT["execute"](tmp_path, {"path": "draft.txt"})["success"] is True
    assert not (tmp_path / "draft.txt").exists()
    assert PILOT["execute"](tmp_path, {"path": "draft.txt"})["success"] is False


def test_file_tool_rejects_escape_and_arbitrary_names(tmp_path):
    for path in ("../draft.txt", "/tmp/draft.txt", "unknown.txt"):
        assert PILOT["execute"](tmp_path, {"path": path})["success"] is False


def test_agent_loop_exports_observed_tool_result(tmp_path):
    (tmp_path / "draft.txt").write_text("temporary")
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "delete_file", "arguments": '{"path":"draft.txt"}'},
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "Deleted draft.txt."}}]},
        ]
    )
    trace = PILOT["run_agent"](
        tmp_path, "Delete draft.txt", "http://fake", "fake", lambda *args: next(responses)
    )
    assert json.loads(trace["messages"][-2]["content"]) == {"success": True, "deleted": "draft.txt"}
    assert trace["messages"][-1]["content"] == "Deleted draft.txt."
