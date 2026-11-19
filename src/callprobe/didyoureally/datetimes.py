"""Bounded comparison of explicitly stated calendar timestamps.

No relative dates, locale guesses, inferred years, or inferred time zones.
Keep the local date, clock time, and offset as separate asserted details:
the same UTC instant expressed with a different offset is not identical evidence.
"""

from __future__ import annotations

import re
from datetime import datetime

DATETIME_KEYS = {"starts_at", "ends_at", "start_time", "end_time", "datetime", "timestamp"}
_MONTHS = "January February March April May June July August September October November December".split()
_ZONE = r"(?P<zone>Z|[+-]\d{2}:\d{2})"
_CLOCK = r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
_ISO = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T" + _CLOCK + _ZONE,
    re.IGNORECASE | re.ASCII,
)
_PROSE = re.compile(
    r"(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<day>\d{1,2}),?\s+"
    r"(?P<year>\d{4})\s+at\s+"
    + _CLOCK
    + r"(?:\s*(?P<ampm>AM|PM))?\s+(?:with\s+)?UTC(?:\s+offset)?\s*"
    + _ZONE,
    re.IGNORECASE | re.ASCII,
)
_BOUNDARY = r"[\w:+.\-]"


def _parts(match: re.Match) -> tuple[int, ...] | None:
    data = match.groupdict()
    month = data["month"]
    if not month.isdigit():
        month = str(next(i for i, name in enumerate(_MONTHS, 1) if name.lower() == month.lower()))
    hour = int(data["hour"])
    ampm = data.get("ampm")
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
    zone = data["zone"]
    offset = 0
    if zone.upper() != "Z":
        hours, minutes = int(zone[1:3]), int(zone[4:6])
        # RFC 3339 -00:00 means an unknown local offset, not a known UTC zone.
        if hours > 23 or minutes > 59 or zone == "-00:00":
            return None
        offset = (hours * 60 + minutes) * (-1 if zone[0] == "-" else 1)
    try:
        date = datetime(
            int(data["year"]),
            int(month),
            int(data["day"]),
            hour,
            int(data["minute"]),
            int(data["second"] or 0),
        )
    except ValueError:
        return None
    return date.year, date.month, date.day, date.hour, date.minute, date.second, offset


def explicit_datetime(value: object) -> tuple[int, ...] | None:
    """Parse one supported full timestamp, requiring an explicit UTC offset."""
    if not isinstance(value, str):
        return None
    for pattern in (_ISO, _PROSE):
        match = pattern.fullmatch(value.strip())
        if match:
            return _parts(match)
    return None


def _source_datetimes(text: str):
    for pattern in (_ISO, _PROSE):
        for match in pattern.finditer(text):
            before = text[match.start() - 1 : match.start()] if match.start() else ""
            after = text[match.end() : match.end() + 1]
            # Sentence punctuation can follow a timestamp; decimals and identifier
            # suffixes cannot. Reject prefixes too, rather than extracting a substring.
            if before and re.fullmatch(_BOUNDARY, before):
                continue
            if after and re.fullmatch(r"[\w:+\-]", after):
                continue
            if after == "." and text[match.end() + 1 : match.end() + 2].isdigit():
                continue
            parts = _parts(match)
            if parts is not None:
                yield match.group(), parts


def datetime_in_source(key: str, value: object, text: str) -> bool:
    """Allow a timestamp representation only when all details occur together."""
    expected = explicit_datetime(value) if key in DATETIME_KEYS else None
    return expected is not None and any(parts == expected for _, parts in _source_datetimes(text))


def sole_datetime_source(key: str, text: str) -> str | None:
    """Retain a single unambiguous full source timestamp during field repair.

    The caller must already have identified a timestamp argument. This does not
    choose an action or introduce a field absent from the proposed extraction.
    """
    if key not in DATETIME_KEYS:
        return None
    values = {parts: literal for literal, parts in _source_datetimes(text)}
    return next(iter(values.values())) if len(values) == 1 else None
