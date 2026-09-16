"""Scaffold a new suite from an existing OpenAI-format tools array.

Turns a tools.json you already have (the same array you'd pass as the
`tools` argument to a chat completion) into a suite directory: tools.yaml,
an empty distractors.yaml, suite.yaml, and a tasks.yaml skeleton with one
commented example per tool.
"""

from __future__ import annotations

from typing import Any

import yaml

BUNDLE_NAME = "main"


def _extract_tool(entry: dict[str, Any]) -> dict[str, Any]:
    if "function" in entry:
        entry = entry["function"]
    return {
        "name": entry["name"],
        "description": entry.get("description") or "TODO: describe this tool.",
        "parameters": entry.get("parameters") or {"type": "object", "properties": {}},
    }


def load_tools_json(data: Any) -> list[dict[str, Any]]:
    """Accept either a raw tools array or an object with a "tools" key."""
    if isinstance(data, dict):
        data = data.get("tools")
    if not isinstance(data, list) or not data:
        raise ValueError(
            'expected a non-empty JSON array of tools, or an object with a "tools" key'
        )
    return [_extract_tool(entry) for entry in data]


def render_tools_yaml(tools: list[dict[str, Any]]) -> str:
    doc = {"bundles": {BUNDLE_NAME: tools}}
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


def render_distractors_yaml() -> str:
    return (
        "# Plausible but irrelevant tools, used to pad the tool count sweep.\n"
        "# Leave empty until you have some, or --pad has nothing to add.\n"
        "tools: []\n"
    )


def render_suite_yaml(name: str) -> str:
    return f"name: {name}\nversion: 1\n"


def render_tasks_yaml(name: str, tools: list[dict[str, Any]]) -> str:
    lines = [f"name: {name}", "tasks:"]
    for tool in tools:
        tool_name = tool["name"]
        lines += [
            f"  # Example call task for `{tool_name}`. Fill in a realistic user",
            "  # message and the expected arguments, then uncomment.",
            f"  # - id: call-{tool_name}",
            "  #   category: select",
            f"  #   bundle: {BUNDLE_NAME}",
            "  #   messages:",
            "  #     - role: user",
            f'  #       content: "TODO: a message that should trigger {tool_name}"',
            "  #   expect:",
            "  #     type: call",
            f"  #     tool: {tool_name}",
            "  #     args: {}  # TODO: fill in the arguments you expect",
            "",
        ]
    lines += [
        "  # Abstention matters: a model that calls a tool whenever one is",
        "  # technically available looks great on paper and fails in",
        "  # production. At least one task per bundle should describe a",
        "  # situation where no tool applies, so the suite also rewards",
        "  # correctly doing nothing.",
        f"  # - id: no-call-{BUNDLE_NAME}",
        "  #   category: abstain",
        f"  #   bundle: {BUNDLE_NAME}",
        "  #   messages:",
        "  #     - role: user",
        '  #       content: "TODO: a message with no correct tool to call"',
        "  #   expect:",
        "  #     type: no_call",
        "",
    ]
    return "\n".join(lines)


def generate_suite_files(tools_data: Any, name: str) -> dict[str, str]:
    tools = load_tools_json(tools_data)
    return {
        "tools.yaml": render_tools_yaml(tools),
        "distractors.yaml": render_distractors_yaml(),
        "suite.yaml": render_suite_yaml(name),
        "tasks.yaml": render_tasks_yaml(name, tools),
    }
