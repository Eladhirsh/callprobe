"""Offline OpenAPI 3.0/3.1 to tool-schema import with explicit diagnostics.

This imports the model-facing argument contract, not an HTTP executor.
No references, API servers, or security schemes are contacted.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator, SchemaError

from .init import generate_suite_files

METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
LOCATIONS = {"path": "path", "query": "query", "header": "headers", "cookie": "cookies"}
RESERVED_HEADERS = {"accept", "content-type", "authorization"}
BASE_DIALECT = "https://spec.openapis.org/oas/3.1/dialect/base"

MAX_DOCUMENT_BYTES = 20_000_000
MAX_VISITS = 1_000_000
MAX_NESTING = 200
MAX_REF_CHAIN = 32
MAX_SCHEMA_NODES = 20_000
MAX_SCHEMA_DEPTH = 64

SCALAR_KEYS = {
    "type", "title", "description", "enum", "const", "default", "examples",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "format", "minItems", "maxItems",
    "uniqueItems", "minProperties", "maxProperties", "deprecated", "writeOnly",
}
MAP_KEYS = {"properties", "patternProperties", "dependentSchemas"}
LIST_KEYS = {"allOf", "anyOf", "oneOf", "prefixItems"}
SCHEMA_KEYS = {"items", "additionalProperties", "not", "if", "then", "else", "contains"}
V31_ONLY_KEYS = {"const", "prefixItems", "patternProperties", "dependentSchemas",
                 "if", "then", "else", "contains"}
IGNORED_KEYS = {"xml", "externalDocs", "$comment"}


class Unsupported(ValueError):
    """An operation cannot be translated without losing its contract."""


@dataclass
class ImportResult:
    tools: list[dict] = field(default_factory=list)
    operations: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    filtered: int = 0


# ---------------------------------------------------------------- loading


def check_json(value: Any) -> None:
    """Reject non-JSON values, cycles (recursive YAML aliases), and alias bombs."""
    budget = [MAX_VISITS]
    active: set[int] = set()
    trail: list[str] = []

    def where() -> str:
        return "/" + "/".join(trail) if trail else "document root"

    def walk(node: Any, depth: int) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("document expands beyond the size limit (possible YAML alias expansion)")
        if depth > MAX_NESTING:
            raise ValueError("document is nested too deeply")
        if node is None or isinstance(node, (bool, str, int)):
            return
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError(f"{where()}: non-finite number is not valid JSON")
            return
        if isinstance(node, (dict, list)):
            if id(node) in active:
                raise ValueError(f"{where()}: recursive YAML alias is not supported")
            active.add(id(node))
            try:
                items = node.items() if isinstance(node, dict) else enumerate(node)
                for key, child in items:
                    if isinstance(node, dict) and not isinstance(key, str):
                        raise ValueError(f"{where()}: object keys must be strings, got {key!r}")
                    trail.append(str(key))
                    walk(child, depth + 1)
                    trail.pop()
            finally:
                active.discard(id(node))
            return
        raise ValueError(
            f"{where()}: {type(node).__name__} value is not plain JSON data (quote it to keep it a string)"
        )

    walk(value, 0)


class _Loader(yaml.SafeLoader):
    """YAML 1.2-like scalars: only true/false are booleans, dates stay strings."""


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag not in {
        "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int",
        "tag:yaml.org,2002:float", "tag:yaml.org,2002:timestamp"}]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"), list("-+0123456789"))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
               r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"), list("-+0123456789."))


def _construct_int(loader, node):
    text = loader.construct_scalar(node)
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    if text.startswith("0o"):
        return sign * int(text[2:], 8)
    if text.startswith("0x"):
        return sign * int(text[2:], 16)
    return sign * int(text)


def _construct_float(loader, node):
    return float(loader.construct_scalar(node).lower().replace(".inf", "inf").replace(".nan", "nan"))


def _construct_mapping(loader, node, deep=False):
    if isinstance(node, yaml.MappingNode):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = loader.construct_object(key_node, deep=True)
            try:
                hash(key)
            except TypeError:
                continue
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_Loader.add_constructor("tag:yaml.org,2002:int", _construct_int)
_Loader.add_constructor("tag:yaml.org,2002:float", _construct_float)
_Loader.construct_mapping = _construct_mapping


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def load_openapi_file(path: str | Path) -> Any:
    """Parse a local JSON/YAML OpenAPI file into plain JSON data, or raise ValueError."""
    source = Path(path)
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"{source} is larger than {MAX_DOCUMENT_BYTES // 1_000_000} MB")
    text = source.read_text(encoding="utf-8-sig")
    try:
        if source.suffix.lower() == ".json":
            data = json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
        else:
            data = yaml.load(text, Loader=_Loader)  # noqa: S506 - restricted SafeLoader subclass
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {source}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}: {exc}") from None
    except RecursionError:
        raise ValueError(f"{source} is nested too deeply") from None
    check_json(data)
    return data


# --------------------------------------------------------------- importing


def _reason(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= 300 else text[:297] + "..."


class Importer:
    def __init__(self, document: Any):
        if not isinstance(document, dict):
            raise ValueError("OpenAPI document must be an object")
        check_json(document)
        version = document.get("openapi")
        if not isinstance(version, str) or not re.fullmatch(r"3\.[01]\.\d+", version):
            raise ValueError(
                f"expected OpenAPI 3.0.x or 3.1.x, found {version!r} "
                "(Swagger 2.0 and other versions are not supported; quote the version string)"
            )
        self.v30 = version.startswith("3.0.")
        if not self.v30 and document.get("jsonSchemaDialect") not in (None, BASE_DIALECT):
            raise ValueError("custom jsonSchemaDialect is not supported")
        self.document = document
        self.result = ImportResult()
        self.nodes = 0
        self.ro_names: set[str] = set()
        self.foreign_required: set[str] = set()

    def resolve(self, value: Any, trail: tuple[str, ...] = (), *, schema=False):
        if not isinstance(value, dict) or "$ref" not in value:
            return value, trail
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise Unsupported(f"only local '#/...' JSON Pointer references are supported: {ref!r}")
        if ref in trail:
            raise Unsupported(f"recursive reference is not supported: {ref}")
        if len(trail) >= MAX_REF_CHAIN:
            raise Unsupported("reference nesting is too deep")
        target: Any = self.document
        try:
            for raw in unquote(ref[2:]).split("/"):
                part = raw.replace("~1", "/").replace("~0", "~")
                if isinstance(target, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", part):
                        raise KeyError(part)
                    target = target[int(part)]
                elif isinstance(target, dict):
                    target = target[part]
                else:
                    raise KeyError(part)
        except (KeyError, IndexError):
            raise Unsupported(f"unresolved reference: {ref}") from None
        target, resolved_trail = self.resolve(target, (*trail, ref), schema=schema)
        siblings = {k: v for k, v in value.items() if k != "$ref"}
        if siblings:
            if self.v30:
                self.result.warnings.append(f"{ref}: OpenAPI 3.0 ignores $ref siblings")
            elif schema:
                target = {"allOf": [target, siblings]}
            elif set(siblings) <= {"summary", "description"} and isinstance(target, dict):
                target = {**target, **siblings}
            else:
                raise Unsupported(f"unsupported reference siblings at {ref}")
        return target, resolved_trail

    def is_read_only(self, value: Any, trail: tuple[str, ...], depth=0) -> bool:
        if depth > 16:
            raise Unsupported("schema nesting is too deep")
        value, trail = self.resolve(value, trail, schema=True)
        if not isinstance(value, dict):
            return False
        if value.get("readOnly") is True:
            return True
        branches = value.get("allOf")
        return isinstance(branches, list) and any(
            self.is_read_only(b, trail, depth + 1) for b in branches)

    def schema(self, value: Any, trail=(), depth=0):
        self.nodes += 1
        if self.nodes > MAX_SCHEMA_NODES or depth > MAX_SCHEMA_DEPTH:
            raise Unsupported("schema expansion exceeds the size/depth limit")
        value, trail = self.resolve(value, trail, schema=True)
        if isinstance(value, bool) and not self.v30:
            return value
        if not isinstance(value, dict):
            raise Unsupported("schema must be an object (or a boolean in OpenAPI 3.1)")
        if value.get("readOnly") is True:
            raise Unsupported("a readOnly schema outside an object property cannot be part of a request")
        out: dict[str, Any] = {}
        read_only: set[str] = set()
        local_names: set[str] = set()
        for key, child in value.items():
            if self.v30 and key in V31_ONLY_KEYS:
                raise Unsupported(f"{key} is not an OpenAPI 3.0 schema keyword")
            if key == "required":
                if not isinstance(child, list) or not all(isinstance(n, str) for n in child):
                    raise Unsupported("required must be an array of strings")
                out[key] = list(child)
            elif key == "readOnly":
                if not isinstance(child, bool):
                    raise Unsupported("readOnly must be boolean")
            elif key == "type" and self.v30 and not isinstance(child, str):
                raise Unsupported("type must be a single string in OpenAPI 3.0")
            elif key == "examples" and self.v30:
                continue
            elif key == "pattern":
                self._check_pattern(child)
                out[key] = child
            elif key in SCALAR_KEYS:
                out[key] = child
            elif key in MAP_KEYS:
                if not isinstance(child, dict):
                    raise Unsupported(f"{key} must be an object")
                converted = {}
                for name, item in child.items():
                    if key == "patternProperties":
                        self._check_pattern(name)
                    if key == "properties":
                        local_names.add(name)
                        if self.is_read_only(item, trail):
                            read_only.add(name)
                            continue
                    converted[name] = self.schema(item, trail, depth + 1)
                out[key] = converted
            elif key in LIST_KEYS:
                if not isinstance(child, list):
                    raise Unsupported(f"{key} must be an array")
                out[key] = [self.schema(item, trail, depth + 1) for item in child]
            elif key in SCHEMA_KEYS:
                if key == "additionalProperties" and isinstance(child, bool):
                    out[key] = child
                else:
                    out[key] = self.schema(child, trail, depth + 1)
            elif key == "nullable":
                if not self.v30:
                    raise Unsupported("nullable is not valid in OpenAPI 3.1; use type: [T, 'null']")
                if not isinstance(child, bool):
                    raise Unsupported("nullable must be boolean")
            elif key == "example":
                out.setdefault("examples", [child])
            elif key == "discriminator":
                self.result.warnings.append("schema discriminator is ignored; oneOf/anyOf are kept as written")
            elif key in IGNORED_KEYS or key.startswith("x-"):
                continue
            else:
                raise Unsupported(f"unsupported schema keyword: {key}")
        if "required" in out:
            self.foreign_required.update(n for n in out["required"] if n not in local_names)
            if read_only:
                out["required"] = [n for n in out["required"] if n not in read_only]
        if read_only:
            if "minProperties" in out or "maxProperties" in out:
                raise Unsupported("readOnly properties combined with minProperties/maxProperties cannot be preserved")
            self.ro_names |= read_only
        if self.v30:
            if value.get("nullable") is True:
                if not isinstance(out.get("type"), str):
                    raise Unsupported("nullable requires an explicit type in OpenAPI 3.0")
                out["type"] = [out["type"], "null"]
            for bound in ("minimum", "maximum"):
                exclusive = "exclusive" + bound.title()
                if exclusive in out:
                    flag = out.pop(exclusive)
                    if not isinstance(flag, bool):
                        raise Unsupported(f"OpenAPI 3.0 {exclusive} must be boolean")
                    if flag:
                        if bound not in out:
                            raise Unsupported(f"{exclusive} requires {bound}")
                        out[exclusive] = out.pop(bound)
        return out

    @staticmethod
    def _check_pattern(pattern: Any) -> None:
        if not isinstance(pattern, str):
            raise Unsupported("pattern must be a string")
        try:
            re.compile(pattern)
        except (re.error, RecursionError, OverflowError) as exc:
            raise Unsupported(f"invalid regular expression {pattern!r}: {exc}") from None

    def parameters(self, values):
        if not isinstance(values, list):
            raise Unsupported("parameters must be an array")
        indexed = {}
        for raw in values:
            value, _ = self.resolve(raw)
            if not isinstance(value, dict) or not isinstance(value.get("name"), str):
                raise Unsupported("each parameter must be an object with a name")
            location = value.get("in")
            if not isinstance(location, str) or location not in LOCATIONS:
                raise Unsupported(f"unsupported parameter location: {location!r}")
            name = value["name"].lower() if location == "header" else value["name"]
            key = (location, name)
            if key in indexed:
                raise Unsupported(f"duplicate parameter: {location}.{value['name']}")
            indexed[key] = value
        return indexed

    def operation(self, path, method, path_item, operation):
        if not isinstance(operation, dict):
            raise Unsupported("operation must be an object")
        self.nodes = 0
        self.ro_names = set()
        self.foreign_required = set()
        label = f"{method.upper()} {path}"
        op_tags = operation.get("tags", [])
        if not isinstance(op_tags, list) or not all(isinstance(t, str) for t in op_tags):
            raise Unsupported("tags must be an array of strings")
        for key in ("summary", "description", "operationId"):
            if key in operation and not isinstance(operation[key], str):
                raise Unsupported(f"{key} must be a string")
        params = {**self.parameters(path_item.get("parameters", [])),
                  **self.parameters(operation.get("parameters", []))}
        properties: dict[str, Any] = {}
        required: list[str] = []
        declared_paths = {name for (loc, name) in params if loc == "path"}
        if set(re.findall(r"\{([^{}]+)\}", path)) != declared_paths:
            raise Unsupported("path placeholders and declared path parameters must match")
        for (location, _), parameter in params.items():
            name = parameter["name"]
            if location == "header" and name.lower() in RESERVED_HEADERS:
                self.result.warnings.append(f"{label}: ignored reserved header {name}")
                continue
            if "schema" not in parameter or "content" in parameter:
                raise Unsupported(f"{location}.{name}: a schema is required; content parameters are not supported")
            if "required" in parameter and not isinstance(parameter["required"], bool):
                raise Unsupported(f"{location}.{name}: required must be boolean")
            if location == "path" and parameter.get("required") is not True:
                raise Unsupported(f"path parameter {name} must be required")
            group_name = LOCATIONS[location]
            group = properties.setdefault(group_name, {
                "type": "object", "properties": {}, "additionalProperties": False,
            })
            converted = self.schema(parameter["schema"])
            description = parameter.get("description")
            if isinstance(converted, dict) and isinstance(description, str) and description:
                converted = {**converted, "description": description}
            group["properties"][name] = converted
            if parameter.get("required") is True:
                group.setdefault("required", []).append(name)
                if group_name not in required:
                    required.append(group_name)
        if "requestBody" in operation:
            body, _ = self.resolve(operation["requestBody"])
            if not isinstance(body, dict) or not isinstance(body.get("content"), dict):
                raise Unsupported("requestBody requires content")
            if "required" in body and not isinstance(body["required"], bool):
                raise Unsupported("requestBody required must be boolean")
            content = body["content"]
            base = {t: t.split(";")[0].strip().lower() for t in content}
            json_types = [t for t, b in base.items() if b == "application/json" or b.endswith("+json")]
            if not json_types:
                raise Unsupported(
                    "requestBody supports only JSON media types (application/json or +json); "
                    f"found {', '.join(sorted(content)) or 'none'}")
            preferred = [t for t in json_types if base[t] == "application/json"]
            media_type = sorted(preferred or json_types)[0]
            if len(content) > 1:
                self.result.warnings.append(f"{label}: selected {media_type}; other media types omitted")
            media = content[media_type]
            if not isinstance(media, dict) or "schema" not in media or media.get("encoding"):
                raise Unsupported("JSON requestBody requires a schema and cannot use encoding")
            properties["body"] = self.schema(media["schema"])
            if body.get("required") is True:
                required.append("body")
        clash = self.foreign_required & self.ro_names
        if clash:
            raise Unsupported(
                f"required list names readOnly properties defined elsewhere ({', '.join(sorted(clash))}); "
                "the request contract cannot be preserved")
        schema = {"type": "object", "properties": properties, "additionalProperties": False}
        if required:
            schema["required"] = required
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise Unsupported(f"invalid argument schema: {_reason(exc)}") from None
        raw_name = operation.get("operationId") or f"{method}_{path}"
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", raw_name):
            name = raw_name
        else:
            base_name = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name).strip("_") or method
            digest = hashlib.sha256(f"{method} {path}".encode()).hexdigest()[:8]
            name = f"{base_name[:55]}_{digest}"
        description = "\n\n".join(operation[k] for k in ("summary", "description") if operation.get(k))
        description = f"{description}\n\n{label}".strip()
        return {"name": name, "description": description, "parameters": schema}

    def run(self, *, tags: list[str] | None = None, skip_unsupported=False):
        paths = self.document.get("paths")
        if not isinstance(paths, dict):
            raise ValueError("OpenAPI document requires a paths object (webhooks are not imported)")
        wanted = set(tags or [])
        failures: list[dict] = []
        used: dict[str, str] = {}
        operation_ids: dict[str, str] = {}
        seen_tags: set[str] = set()
        total = 0
        for path, raw_item in paths.items():
            if path.startswith("x-"):
                continue
            if not path.startswith("/"):
                raise ValueError(f"invalid API path: {path}")
            try:
                item, _ = self.resolve(raw_item)
                if not isinstance(item, dict):
                    raise Unsupported("path item must be an object")
            except Unsupported as exc:
                failures.append({"method": "*", "path": path, "reason": _reason(exc)})
                continue
            for key in item:
                if key.lower() in METHODS and key not in METHODS:
                    failures.append({"method": key, "path": path,
                                     "reason": "HTTP method keys must be lowercase"})
            for method in METHODS:
                if method not in item:
                    continue
                total += 1
                op = item[method]
                label = f"{method.upper()} {path}"
                op_id = op.get("operationId") if isinstance(op, dict) else None
                if isinstance(op_id, str) and op_id:
                    if op_id in operation_ids:
                        raise ValueError(
                            f"duplicate operationId {op_id!r} at {operation_ids[op_id]} and {label}; "
                            "operationIds must be unique")
                    operation_ids[op_id] = label
                if wanted and isinstance(op, dict):
                    op_tags = op.get("tags", [])
                    if isinstance(op_tags, list) and all(isinstance(t, str) for t in op_tags):
                        seen_tags.update(op_tags)
                        if not wanted.intersection(op_tags):
                            self.result.filtered += 1
                            continue
                try:
                    tool = self.operation(path, method, item, op)
                    if tool["name"] in used:
                        raise ValueError(
                            f"duplicate tool name {tool['name']!r} from {used[tool['name']]} and {label}; "
                            "give operations unique operationIds")
                    used[tool["name"]] = label
                    self.result.tools.append(tool)
                    self.result.operations.append({"tool": tool["name"], "method": method.upper(), "path": path})
                except Unsupported as exc:
                    failures.append({"method": method.upper(), "path": path, "reason": _reason(exc)})
                except RecursionError:
                    failures.append({"method": method.upper(), "path": path,
                                     "reason": "schema nesting is too deep"})
        if wanted:
            missing = sorted(wanted - seen_tags)
            if missing and not self.result.tools and not failures:
                available = ", ".join(sorted(seen_tags)) or "none"
                raise ValueError(f"no operations match tag(s) {', '.join(sorted(wanted))}; available tags: {available}")
            for tag in missing:
                self.result.warnings.append(f"tag {tag!r} matched no operations")
        if failures and not skip_unsupported:
            detail = "\n".join(f"  {r['method']} {r['path']}: {r['reason']}" for r in failures)
            raise ValueError(
                f"OpenAPI import failed:\n{detail}\n"
                "Fix the document or pass --skip-unsupported to explicitly omit these operations.")
        if not self.result.tools:
            detail = "; ".join(r["reason"] for r in failures)
            raise ValueError("no supported operations selected" + (f": {detail}" if detail else ""))
        self.result.skipped = failures
        self.result.warnings = list(dict.fromkeys(self.result.warnings))
        return self.result


def import_openapi(document, *, tags=None, skip_unsupported=False) -> ImportResult:
    return Importer(document).run(tags=tags, skip_unsupported=skip_unsupported)


def generate_openapi_suite(document, name, *, tags=None, skip_unsupported=False):
    result = import_openapi(document, tags=tags, skip_unsupported=skip_unsupported)
    files = generate_suite_files(result.tools, name)
    report = {"openapi_version": document["openapi"], "operations": result.operations,
              "skipped": result.skipped, "filtered_operations": result.filtered,
              "warnings": result.warnings}
    files["import-report.json"] = json.dumps(report, indent=2) + "\n"
    rows = ["# Your imported API suite", "", "## Imported tools", "",
            "| Tool | Operation |", "| --- | --- |"]
    rows += [f"| `{r['tool']}` | `{r['method']} {r['path']}` |" for r in result.operations]
    rows += ["", "## Write your first tests", "",
             "1. Open `tasks.yaml`. Uncomment a call task and an abstention task.",
             "2. Replace the draft message and argument placeholders with your own expected behavior.",
             "3. Run `callprobe validate --suite .` from this directory.",
             "   It fails until at least one task is active, so this suite is not ready to run yet.",
             "4. Run `callprobe run --suite . --model YOUR_MODEL --pad 0 --out baseline.json`.",
             "5. Repeat with `--out candidate.json`, then run",
             "   `callprobe compare baseline.json candidate.json --fail-on-regression`.", "",
             "Arguments are grouped under `path`, `query`, `headers`, `cookies`, and `body`.",
             "For partial assertions use `arg_checks`, such as `path: body.amount_cents`.",
             "Draft shapes are editing aids, not automatically verified expected answers.", "",
             "## Import scope", "",
             "This imports tool definitions only. It never executes API operations.",
             "Authentication, HTTP serialization, responses, callbacks, links, and webhooks",
             "are not imported. Format annotations are retained but are not asserted by",
             "the scorer; add explicit argument checks where needed.",
             "Read-only properties are omitted from request schemas. Review the argument",
             "mapping against your application's real tool adapter before using this suite.",
             "See `import-report.json` for renamed tools, selected operations, and diagnostics.", ""]
    if result.skipped:
        rows += ["## Skipped operations", ""]
        rows += [f"- {r['method']} {r['path']}: {r['reason']}" for r in result.skipped]
    if result.warnings:
        rows += ["", "## Warnings", "", *[f"- {w}" for w in result.warnings]]
    files["README.md"] = "\n".join(rows) + "\n"
    return files, result
