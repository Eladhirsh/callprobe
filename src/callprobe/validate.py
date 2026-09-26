"""Check that task expectations agree with the tool schemas they reference.

The loader already checks structural things (duplicate ids, unknown
bundles, distractor references). This checks the part that only makes
sense once you know the schema: is every tool/distractor schema itself
valid, does every asserted argument key actually exist on the tool, and
is every asserted value legal for it. A typo here would otherwise fail
every model silently.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable

from .models import Suite, Tool


def _forbid_remote_retrieve(uri: str):
    """Passed to `referencing.Registry` as its only way to fetch a
    resource; raising here instead of fetching is what makes the
    registry incapable of network I/O, independent of any pre-check.
    """
    raise LookupError("schema retrieval is disabled during offline validation")


# A registry with nothing pre-loaded and a `retrieve` that always raises:
# no remote `$ref` can ever be resolved through it. Refs within the same
# document (e.g. "#/$defs/foo") still resolve, since that needs no retrieval.
_NO_RETRIEVAL_REGISTRY = Registry(retrieve=_forbid_remote_retrieve)


def _schema_problems(label: str, schema: dict) -> list[str]:
    """Diagnostics for a single tool's parameter schema, or [] if it's a
    valid JSON Schema. Does not attempt to resolve any `$ref` inside it;
    `check_schema` only validates the schema against the meta-schema.
    """
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        location = ".".join(str(part) for part in exc.path) or "(root)"
        return [f"{label}: invalid schema at {location} ({exc.validator} constraint)"]
    except (ValueError, TypeError, RecursionError) as exc:
        return [f"{label}: invalid schema ({type(exc).__name__})"]
    return []


def validate_suite(suite: Suite) -> list[str]:
    problems: list[str] = []
    invalid: set[int] = set()

    def check_tool(namespace: str, tool: Tool) -> None:
        errors = _schema_problems(f"{namespace}/{tool.name}", tool.parameters or {})
        if errors:
            invalid.add(id(tool))
            problems.extend(errors)

    for bundle_name, bundle in suite.bundles.items():
        for tool in bundle.tools:
            check_tool(bundle_name, tool)
    for tool in suite.distractors:
        check_tool("distractors", tool)

    for task in suite.tasks:
        if task.expect.type != "call":
            continue
        tool = suite.bundles[task.bundle].by_name(task.expect.tool)
        if id(tool) in invalid:
            continue
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
        validator = Draft202012Validator(schema, registry=_NO_RETRIEVAL_REGISTRY)
        try:
            errors = list(validator.iter_errors(task.expect.args))
        except (Unresolvable, RecursionError):
            problems.append(
                f"{task.id}: cannot validate offline (unresolved schema reference in {tool.name})"
            )
            continue
        problems += [f"{task.id}: {e.message}" for e in errors]
    return problems
