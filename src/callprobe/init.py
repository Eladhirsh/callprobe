"""Scaffold a new suite from an existing OpenAI-format tools array.

Turns a tools.json you already have (the same array you'd pass as the
`tools` argument to a chat completion) into a suite directory: tools.yaml,
an empty distractors.yaml, suite.yaml, and a tasks.yaml skeleton with one
commented example per tool.
"""

from __future__ import annotations

import json
import re
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
    return yaml.safe_dump({"name": name, "version": 1}, sort_keys=False)


def _scalar(text: str) -> str:
    return json.dumps(text)


def _comment_lines(text: str, prefix: str) -> list[str]:
    return [f"{prefix}{line}".rstrip() for line in str(text).splitlines() or [""]]


def _shape(schema: Any, depth: int = 0) -> Any:
    """A types-only placeholder for a schema. Never contains expected values."""
    if not isinstance(schema, dict):
        return "<any>"
    if depth >= 4:
        return "<...>"
    for combinator in ("oneOf", "anyOf"):
        if isinstance(schema.get(combinator), list):
            return f"<{combinator}: {len(schema[combinator])} alternatives>"
    if isinstance(schema.get("allOf"), list):
        return "<allOf: see tool schema>"
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    if isinstance(schema.get("properties"), dict) and ("object" in kinds or kind is None):
        required = set(schema.get("required") or [])
        shaped = {}
        for index, (key, child) in enumerate(schema["properties"].items()):
            if index >= 12:
                shaped["..."] = "<more properties>"
                break
            mark = " (required)" if key in required else ""
            shaped[key] = _shape(child, depth + 1)
            if isinstance(shaped[key], str):
                shaped[key] += mark
        return shaped
    if "array" in kinds:
        return [_shape(schema.get("items"), depth + 1)]
    if isinstance(schema.get("enum"), list):
        return "<one of: " + "|".join(json.dumps(v) for v in schema["enum"][:6]) + ">"
    return "<" + "|".join(str(k) for k in kinds if k) + ">" if any(kinds) else "<any>"


def render_tasks_yaml(name: str, tools: list[dict[str, Any]]) -> str:
    lines = [
        f"# Draft tasks for {json.dumps(name)}. Everything below is commented out: nothing here",
        "# is a tested expectation until you write it. Uncomment and edit at least one",
        "# draft",
        "# task; `callprobe validate` fails until at least one task is active. A call task",
        "# and an abstention task are both recommended, but only one task is required.",
        yaml.safe_dump({"name": name}, sort_keys=False).rstrip(),
        "tasks:",
    ]
    for tool in tools:
        tool_name = " ".join(str(tool["name"]).split()) if re.search(r"\s", str(tool["name"])) else tool["name"]
        lines += [f"  # Tool `{tool_name}`:"]
        lines += _comment_lines(tool.get("description") or "", "  #   ")
        shape = json.dumps(_shape(tool.get("parameters")), ensure_ascii=False)
        lines += [
            "  # Argument shape (types only, NOT expected values):",
            *_comment_lines(shape, "  #   "),
            "  # `args` values are compared exactly per top-level key, so give each key's",
            "  # complete value. For a partial nested expectation use `arg_checks`",
            "  # (path: body.field) instead of a partial `args` object.",
            f"  # - id: call-{tool_name}",
            "  #   category: select",
            f"  #   bundle: {BUNDLE_NAME}",
            "  #   messages:",
            "  #     - role: user",
            "  #       content: " + json.dumps(f"TODO: a realistic message that should trigger {tool_name}"),
            "  #   expect:",
            "  #     type: call",
            f"  #     tool: {_scalar(tool_name)}",
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
