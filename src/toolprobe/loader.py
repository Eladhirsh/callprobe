"""Load a suite directory into memory.

A suite directory looks like:

    suites/core/
        tools.yaml        # named bundles of tools
        distractors.yaml  # plausible but irrelevant tools used for padding
        tasks.yaml        # the tasks themselves
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import Bundle, Suite, Task, Tool


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_suite(directory: str | Path) -> Suite:
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"suite directory not found: {root}")

    raw_tools = _read(root / "tools.yaml")
    bundles: dict[str, Bundle] = {}
    for name, tools in (raw_tools.get("bundles") or {}).items():
        bundles[name] = Bundle(
            name=name, tools=[Tool(**tool) for tool in tools]
        )

    raw_distractors = _read(root / "distractors.yaml")
    distractors = [Tool(**tool) for tool in (raw_distractors.get("tools") or [])]

    raw_tasks = _read(root / "tasks.yaml")
    tasks: list[Task] = []
    seen: set[str] = set()
    for entry in raw_tasks.get("tasks") or []:
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
        task.depth = sum(1 for m in task.messages if m.get("role") == "user")
        tasks.append(task)

    return Suite(
        name=raw_tasks.get("name") or root.name,
        bundles=bundles,
        distractors=distractors,
        tasks=tasks,
    )
