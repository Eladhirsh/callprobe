"""Load a suite directory into memory.

A suite directory looks like:

    suites/core/
        suite.yaml         # name and version, optional
        tools.yaml         # named bundles of tools
        distractors.yaml   # plausible but irrelevant tools used for padding
        tasks.yaml         # the tasks themselves
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .models import Bundle, Suite, Task, Tool

# A suite root can be a real Path (a git checkout or --suite argument) or an
# importlib.resources Traversable (the suite packaged inside the wheel).
# Both support is_dir(), the / operator, open(), and read_bytes(), so we
# duck type it.
SuiteRoot = Any

# Files whose contents determine whether two suites can be compared.
SUITE_FILES = ("tools.yaml", "distractors.yaml", "tasks.yaml")


def _read(path: SuiteRoot) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a YAML mapping")
    return data


def _entries(value, label: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label}: expected a list")
    for index, entry in enumerate(value, start=1):
        if not isinstance(entry, dict) or not all(isinstance(key, str) for key in entry):
            raise ValueError(f"{label}: item {index} must be a mapping with string keys")
    return value


def _suite_hash(root: SuiteRoot) -> str:
    """A stable hash over the files that define a suite's content.

    Used to catch mixing results from suites that have silently diverged
    even when their version numbers agree.
    """
    digest = hashlib.sha256()
    for name in SUITE_FILES:
        path = root / name
        content = path.read_bytes() if path.is_file() else b""
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()[:16]


def _check_unique_tool_names(tools: list[Tool], label: str) -> None:
    seen: set[str] = set()
    for tool in tools:
        if tool.name in seen:
            raise ValueError(f"{label}: duplicate tool name: {tool.name}")
        seen.add(tool.name)


def load_suite(directory: str | SuiteRoot) -> Suite:
    root = Path(directory) if isinstance(directory, str) else directory
    if not root.is_dir():
        raise FileNotFoundError(f"suite directory not found: {root}")

    raw_suite = _read(root / "suite.yaml")

    raw_tools = _read(root / "tools.yaml")
    bundles: dict[str, Bundle] = {}
    raw_bundles = raw_tools.get("bundles")
    if raw_bundles is None:
        raw_bundles = {}
    if not isinstance(raw_bundles, dict):
        raise ValueError("tools.yaml: bundles must be a mapping")
    for name, tools in raw_bundles.items():
        bundles[name] = Bundle(
            name=name, tools=[Tool(**tool) for tool in _entries(tools, f"tools.yaml bundle {name}")]
        )

    raw_distractors = _read(root / "distractors.yaml")
    distractors = [Tool(**tool) for tool in _entries(raw_distractors.get("tools"), "distractors.yaml tools")]

    for name, bundle in bundles.items():
        _check_unique_tool_names(bundle.tools, f"bundle {name}")
    _check_unique_tool_names(distractors, "distractors")

    raw_tasks = _read(root / "tasks.yaml")
    tasks: list[Task] = []
    seen: set[str] = set()
    for entry in _entries(raw_tasks.get("tasks"), "tasks.yaml tasks"):
        task = Task(**entry)
        if task.id in seen:
            raise ValueError(f"duplicate task id: {task.id}")
        seen.add(task.id)
        if task.bundle not in bundles:
            raise ValueError(f"task {task.id} references unknown bundle {task.bundle}")
        if task.expect.type == "call":
            if task.expect.tool is None:
                raise ValueError(f"task {task.id} expects a call but names no tool")
            if bundles[task.bundle].by_name(task.expect.tool) is None:
                raise ValueError(
                    f"task {task.id} expects {task.expect.tool}, "
                    f"absent from bundle {task.bundle}"
                )
        known = {d.name for d in distractors}
        for name in task.exclude_distractors:
            if name not in known:
                raise ValueError(
                    f"task {task.id} excludes {name}, which is not a distractor"
                )
        task.depth = sum(1 for m in task.messages if m.get("role") == "user")
        tasks.append(task)

    return Suite(
        name=raw_suite.get("name") or raw_tasks.get("name") or root.name,
        version=raw_suite.get("version") or 1,
        hash=_suite_hash(root),
        bundles=bundles,
        distractors=distractors,
        tasks=tasks,
    )
