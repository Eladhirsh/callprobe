"""Separate wrong-type from wrong-value."""
from __future__ import annotations
import json
from typing import Any

TRUE = {"true", "yes", "1"}
FALSE = {"false", "no", "0"}

def _coerce_scalar(value, kind):
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        if kind == "integer":
            return int(text, 10) if text.lstrip("-").isdigit() else int(float(text))
        if kind == "number":
            return float(text)
        if kind == "boolean":
            low = text.lower()
            if low in TRUE:
                return True
            if low in FALSE:
                return False
    except (TypeError, ValueError):
        return value
    return value

def _types(schema):
    declared = schema.get("type")
    if isinstance(declared, str):
        return [declared]
    if isinstance(declared, list):
        return [t for t in declared if isinstance(t, str)]
    return []

def coerce(value, schema):
    if not isinstance(schema, dict):
        return value
    kinds = _types(schema)
    if isinstance(value, str) and ({"array", "object"} & set(kinds)):
        text = value.strip()
        if text[:1] in "[{":
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return value
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        return {k: coerce(v, properties.get(k)) for k, v in value.items()}
    if isinstance(value, list):
        items = schema.get("items")
        return [coerce(v, items) for v in value]
    for kind in kinds:
        if kind in ("integer", "number", "boolean"):
            return _coerce_scalar(value, kind)
    return value

def coerce_arguments(arguments, parameters):
    if not isinstance(arguments, dict):
        return arguments, False
    coerced = coerce(arguments, parameters or {})
    return coerced, coerced != arguments
