import json

import pytest
import yaml

from callprobe.init import generate_suite_files
from callprobe.loader import load_suite
from callprobe.validate import validate_suite

TOOLS_ARRAY = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Current conditions for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
]


def test_accepts_raw_array():
    files = generate_suite_files(TOOLS_ARRAY, "myapp")
    assert set(files) == {"tools.yaml", "distractors.yaml", "suite.yaml", "tasks.yaml"}
    tools_doc = yaml.safe_load(files["tools.yaml"])
    names = {t["name"] for t in tools_doc["bundles"]["main"]}
    assert names == {"get_weather", "set_reminder"}


def test_accepts_wrapped_object():
    files = generate_suite_files({"tools": TOOLS_ARRAY}, "myapp")
    tools_doc = yaml.safe_load(files["tools.yaml"])
    assert len(tools_doc["bundles"]["main"]) == 2


def test_rejects_empty_or_malformed_input():
    with pytest.raises(ValueError):
        generate_suite_files({"not_tools": []}, "myapp")
    with pytest.raises(ValueError):
        generate_suite_files([], "myapp")


def test_skeleton_has_one_commented_example_per_tool_and_a_no_call_stub():
    files = generate_suite_files(TOOLS_ARRAY, "myapp")
    tasks_text = files["tasks.yaml"]
    assert tasks_text.count("# - id: call-") == 2
    assert "no-call-main" in tasks_text
    assert "Abstention matters" in tasks_text


def test_generated_suite_loads_with_zero_active_tasks(tmp_path):
    files = generate_suite_files(TOOLS_ARRAY, "myapp")
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    suite = load_suite(tmp_path)
    assert suite.tasks == []
    assert "main" in suite.bundles
    assert not validate_suite(suite)


def test_filled_in_stub_passes_validate(tmp_path):
    files = generate_suite_files(TOOLS_ARRAY, "myapp")
    files["tasks.yaml"] = """\
name: myapp
tasks:
  - id: call-get_weather
    category: select
    bundle: main
    messages:
      - role: user
        content: What is the weather in Boston?
    expect:
      type: call
      tool: get_weather
      args: {city: Boston}

  - id: no-call-main
    category: abstain
    bundle: main
    messages:
      - role: user
        content: Thanks, that's all.
    expect:
      type: no_call
"""
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    suite = load_suite(tmp_path)
    assert len(suite.tasks) == 2
    assert not validate_suite(suite)
    assert json.dumps(suite.model_dump()) or True  # round-trips without error
