"""Separate wrong-type from wrong-value."""
from __future__ import annotations
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any

TRUE = {"true", "yes", "1"}
FALSE = {"false", "no", "0"}

# Python 3.11+ refuses int(str)/str(int) conversions past this many digits
# (the default of sys.set_int_max_str_digits) to stop quadratic-time DoS on
# huge digit strings; earlier supported versions have no such limit and would
# happily materialize an arbitrarily large int. Enforcing the same bound
# ourselves, before ever calling int(), keeps coercion outcomes identical
# across supported Python versions instead of depending on which one is
# running, and keeps a hostile "1e999999" from being expanded into a
# thousands-of-digits integer at all.
MAX_INTEGER_DIGITS = 4300


def _bounded_exact_integer(text: str) -> int | None:
    """The exact integer value of `text`, or None if it isn't an integral
    decimal/exponent value, or is too large to materialize safely."""
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    if value.is_zero():
        return 0
    integral = value.to_integral_value()
    if integral != value:
        return None
    digits, exponent = integral.as_tuple().digits, integral.as_tuple().exponent
    if len(digits) + max(exponent, 0) > MAX_INTEGER_DIGITS:
        return None
    return int(integral)


def _coerce_scalar(value, kind):
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        if kind == "integer":
            result = _bounded_exact_integer(text)
            return value if result is None else result
        if kind == "number":
            result = float(text)
            if not math.isfinite(result):
                return value
            return result
        if kind == "boolean":
            low = text.lower()
            if low in TRUE:
                return True
            if low in FALSE:
                return False
    except (TypeError, ValueError, OverflowError):
        return value
    return value

def _types(schema):
    declared = schema.get("type")
    if isinstance(declared, str):
        return [declared]
    if isinstance(declared, list):
        return [t for t in declared if isinstance(t, str)]
    return []

def _json_number(text: str):
    """Encoded containers use the same finite/size limits as scalar coercion."""
    if any(marker in text for marker in ".eE"):
        number = float(text)
        if math.isfinite(number):
            return number
    else:
        number = _bounded_exact_integer(text)
        if number is not None:
            return number
    raise ValueError("nonfinite or oversized JSON number")


def coerce(value, schema):
    if not isinstance(schema, dict):
        return value
    kinds = _types(schema)
    if isinstance(value, str) and ({"array", "object"} & set(kinds)):
        text = value.strip()
        if text[:1] in "[{":
            try:
                value = json.loads(text, parse_int=_json_number, parse_float=_json_number,
                                   parse_constant=_json_number)
            except ValueError:
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
