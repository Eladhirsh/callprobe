"""JSON evidence must not contain ambiguous keys or nonfinite numbers."""

from __future__ import annotations

import json
import math
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Evidence contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("Nonfinite JSON numbers are not valid evidence")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON numbers are not valid evidence")
    return number


def loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def ensure_finite_numbers(value: Any) -> None:
    """Check already-decoded API inputs too; duplicate keys are no longer recoverable."""
    pending = [value]
    visited = set()
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Nonfinite JSON numbers are not valid evidence")
        if isinstance(item, (dict, list, tuple)) and id(item) not in visited:
            visited.add(id(item))
            pending.extend(item.values() if isinstance(item, dict) else item)
