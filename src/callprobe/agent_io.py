"""Strict JSON input for mock agent suites and saved comparison evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path


def read_agent_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("agent input contains duplicate JSON keys")
            result[key] = value
        return result

    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("agent input contains nonfinite JSON numbers")
        return number

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_float=finite,
            parse_constant=finite,
        )
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("invalid agent input JSON") from exc
