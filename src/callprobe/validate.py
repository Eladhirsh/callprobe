"""Check that task expectations agree with the tool schemas they reference.

The loader already checks structural things (duplicate ids, unknown
bundles, distractor references). This checks the part that only makes
sense once you know the schema: does every asserted argument key actually
exist on the tool, and is every asserted value legal for it. A typo here
would otherwise fail every model silently.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator

from .models import Suite


def validate_suite(suite: Suite) -> list[str]:
    problems: list[str] = []
    for task in suite.tasks:
        if task.expect.type != "call":
            continue
        tool = suite.bundles[task.bundle].by_name(task.expect.tool)
        properties = (tool.parameters or {}).get("properties", {})
        for key in task.expect.args:
            if key.split(".")[0] not in properties:
                problems.append(f"{task.id}: args key {key}")
        for check in task.expect.arg_checks:
            if check.path.split(".")[0] not in properties:
                problems.append(f"{task.id}: check path {check.path}")

        if not task.expect.args:
            continue
        schema = dict(tool.parameters or {})
        schema.pop("required", None)  # partial expectations are fine
        errors = Draft202012Validator(schema).iter_errors(task.expect.args)
        problems += [f"{task.id}: {e.message}" for e in errors]
    return problems
