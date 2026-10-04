"""Deterministic matching of claims against the tool-call trace.

The LLM (if any) only extracts claims. Every verdict is decided here, by
plain comparison, so each finding can be explained and reproduced.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from .schema import Claim, ToolCall, Trace


class Verdict(str, Enum):
    BACKED = "backed"
    CONTRADICTED = "contradicted"
    PHANTOM = "phantom"
    MASKED_FAILURE = "masked_failure"
    UNMENTIONED = "unmentioned"


PROBLEM_VERDICTS = {Verdict.CONTRADICTED, Verdict.PHANTOM, Verdict.MASKED_FAILURE}


@dataclass
class Mismatch:
    key: str
    claimed: Any
    actual: Any


@dataclass
class Finding:
    verdict: Verdict
    claim: Claim | None = None
    call: ToolCall | None = None
    mismatches: list[Mismatch] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "claim": None
            if self.claim is None
            else {
                "text": self.claim.text,
                "tool": self.claim.tool,
                "args": self.claim.args,
                "message_index": self.claim.message_index,
                "group_id": self.claim.group_id,
            },
            "call": None
            if self.call is None
            else {
                "id": self.call.id,
                "tool": self.call.tool,
                "args": self.call.args,
                "status": self.call.status,
            },
            "mismatches": [m.__dict__ for m in self.mismatches],
            "unchecked": self.unchecked,
            "explanation": self.explanation,
        }


# ---- value comparison ---------------------------------------------------

_NUM_RE = re.compile(
    r"^(?P<prefix>[$€£¥]|usd|eur|gbp|jpy)?\s*"
    r"(?P<number>-?(?:\d[\d,]*(?:\.\d+)?|\.\d+))\s*"
    r"(?P<suffix>usd|eur|gbp|jpy|dollars?|cents?|%|percent)?$",
    re.IGNORECASE,
)
_UNITS = {
    "$": "usd",
    "dollar": "usd",
    "dollars": "usd",
    "€": "eur",
    "£": "gbp",
    "¥": "jpy",
    "%": "percent",
    "cent": "usd",
    "cents": "usd",
}


def _as_number(v: Any) -> tuple[Decimal, str | None] | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        number = Decimal(str(v))
        return (number, None) if number.is_finite() else None
    if isinstance(v, str):
        match = _NUM_RE.fullmatch(v.strip())
        if match:
            prefix = (match["prefix"] or "").lower()
            suffix = (match["suffix"] or "").lower()
            units = {_UNITS.get(u, u) for u in (prefix, suffix) if u}
            if len(units) > 1:
                return None
            try:
                number = Decimal(match["number"].replace(",", ""))
                if suffix in ("cent", "cents"):
                    number /= 100
                return number, next(iter(units), None)
            except InvalidOperation:
                return None
    return None


def _norm_str(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def values_agree(claimed: Any, actual: Any) -> bool:
    """True when a stated value is consistent with the value actually used."""
    cn, an = _as_number(claimed), _as_number(actual)
    if cn is not None and an is not None:
        return cn[0] == an[0] and (cn[1] is None or an[1] is None or cn[1] == an[1])
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return type(claimed) is type(actual) and claimed == actual
    if isinstance(claimed, (list, tuple, set)) and isinstance(actual, (list, tuple, set)):
        return all(any(values_agree(x, y) for y in actual) for x in claimed)
    if isinstance(claimed, (list, tuple, set)):
        return len(claimed) == 1 and values_agree(next(iter(claimed)), actual)
    if isinstance(actual, (list, tuple, set)):
        return any(values_agree(claimed, x) for x in actual)
    c, a = _norm_str(claimed), _norm_str(actual)
    if c == a:
        return True
    # "Dana" vs "dana@acme.com": a stated name may be a fragment of the real value.
    if "@" in a and "@" not in c:
        return c in re.split(r"[._+\-]", a.split("@", 1)[0])
    return False


def _clock_minutes(value: Any) -> int | None:
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    suffix = (match[3] or "").lower()
    if minute > 59 or hour > 23 or (suffix and not 1 <= hour <= 12):
        return None
    if suffix:
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    return hour * 60 + minute


def _argument_agrees(key: str, claimed: Any, actual: Any) -> bool:
    if key == "time":
        left, right = _clock_minutes(claimed), _clock_minutes(actual)
        if left is not None and right is not None:
            return left == right
    return values_agree(claimed, actual)


def compare_args(claim: Claim, call: ToolCall) -> tuple[list[Mismatch], list[str], int]:
    """Return (mismatches, unchecked keys, number of agreeing keys)."""
    mismatches: list[Mismatch] = []
    unchecked: list[str] = []
    agree = 0
    for key, claimed in claim.args.items():
        if key in call.args:
            if _argument_agrees(key, claimed, call.args[key]):
                agree += 1
            else:
                mismatches.append(Mismatch(key, claimed, call.args[key]))
        elif key == "currency" and "amount" in call.args:
            amount = _as_number(call.args["amount"])
            unit = amount[1] if amount else None
            if unit not in {"usd", "eur", "gbp", "jpy"}:
                unchecked.append(key)
            elif _norm_str(claimed) == unit:
                agree += 1
            else:
                mismatches.append(Mismatch(key, claimed, unit))
        elif key == "amount" and "amt" in call.args:
            # Only explicit aliases are comparable. Coincidental equal values in
            # unrelated fields (such as cents or percentages) are not evidence.
            if values_agree(claimed, call.args["amt"]):
                agree += 1
            else:
                mismatches.append(Mismatch(key, claimed, call.args["amt"]))
        else:
            unchecked.append(key)
    return mismatches, unchecked, agree


# ---- matching -----------------------------------------------------------


def _candidates(trace: Trace, claim: Claim) -> list[ToolCall]:
    return [
        c
        for c in trace.calls
        if c.tool == claim.tool and (claim.message_index is None or c.index < claim.message_index)
    ]


def _reserve_group_calls(
    trace: Trace, members: list[tuple[int, Claim]], linked: set[str]
) -> dict[int, ToolCall]:
    """Jointly reserve compatible calls before diagnosing unmatched claims.

    First find a maximum matching using successful calls. Then extend it with
    compatible failed calls. An augmenting path keeps every already assigned
    call in use, so this extension cannot reduce the number of successful calls.
    Each claim and call appears at most once, including vague overlapping claims.
    """
    compatible: dict[int, list[ToolCall]] = {}
    for index, claim in members:
        scored = []
        for call in _candidates(trace, claim):
            mismatches, _, agree = compare_args(claim, call)
            if not mismatches:
                key = (call.status != "ok", -agree, call.id in linked, -call.index)
                scored.append((key, call))
        compatible[index] = [call for _, call in sorted(scored, key=lambda item: item[0])]

    assigned: dict[int, ToolCall] = {}
    owners: dict[str, int] = {}

    def augment(start: int, candidates: dict[int, list[ToolCall]]) -> None:
        # Breadth-first search favors available calls over needless reassignment
        # and avoids a recursion limit for large labeled claim groups.
        queue = deque([start])
        parents: dict[int, tuple[int, ToolCall]] = {}
        seen_claims = {start}
        seen_calls: set[str] = set()
        while queue:
            index = queue.popleft()
            for call in candidates[index]:
                if call.id in seen_calls:
                    continue
                seen_calls.add(call.id)
                owner = owners.get(call.id)
                if owner is None:
                    while True:
                        assigned[index] = call
                        owners[call.id] = index
                        if index == start:
                            return
                        index, call = parents[index]
                if owner not in seen_claims:
                    seen_claims.add(owner)
                    parents[owner] = (index, call)
                    queue.append(owner)

    successful = {
        index: [call for call in calls if call.status == "ok"] for index, calls in compatible.items()
    }
    for candidates in (successful, compatible):
        # Constrained claims get first choice; augmenting paths handle overlaps
        # that cannot be solved by specificity or candidate counts alone.
        order = sorted(members, key=lambda item: (len(candidates[item[0]]), -len(item[1].args), item[0]))
        for index, _ in order:
            if index not in assigned:
                augment(index, candidates)
    return assigned


def check(trace: Trace, claims: list[Claim]) -> list[Finding]:
    findings: list[Finding] = []
    linked: set[str] = set()
    grouped_calls: dict[tuple[int | None, str], set[str]] = {}
    group_members: dict[tuple[int | None, str], list[tuple[int, Claim]]] = {}
    reservations: dict[tuple[int | None, str], dict[int, ToolCall]] = {}
    for index, claim in enumerate(claims):
        if claim.group_id is not None and claim.tool in trace.tools:
            group_members.setdefault((claim.message_index, claim.group_id), []).append((index, claim))

    for index, claim in enumerate(claims):
        if claim.tool is None or claim.tool not in trace.tools:
            findings.append(
                Finding(
                    Verdict.PHANTOM,
                    claim=claim,
                    explanation="No available tool could have performed this action.",
                )
            )
            continue

        cands = _candidates(trace, claim)
        group_key = (claim.message_index, claim.group_id) if claim.group_id is not None else None
        if group_key is not None:
            if group_key not in reservations:
                reservations[group_key] = _reserve_group_calls(trace, group_members[group_key], linked)
            reserved = reservations[group_key]
            used = grouped_calls.setdefault(group_key, set())
            if index in reserved:
                cands = [reserved[index]]
            else:
                reserved_ids = {call.id for call in reserved.values()}
                cands = [call for call in cands if call.id not in used | reserved_ids]
        if not cands:
            findings.append(
                Finding(
                    Verdict.PHANTOM,
                    claim=claim,
                    explanation=f"No unused call to {claim.tool} backs this grouped action before the message."
                    if group_key is not None
                    else f"The agent never called {claim.tool} before saying this.",
                )
            )
            continue

        scored = []
        for c in cands:
            mm, unchecked, agree = compare_args(claim, c)
            # Fewest mismatches first, then a successful call, then most agreement,
            # then prefer a call no other claim has used, then the latest call.
            key = (len(mm), c.status != "ok", -agree, c.id in linked, -c.index)
            scored.append((key, c, mm, unchecked))
        scored.sort(key=lambda s: s[0])
        _, call, mm, unchecked = scored[0]
        linked.add(call.id)
        if group_key is not None:
            grouped_calls[group_key].add(call.id)

        if mm:
            parts = ", ".join(f"{m.key}: said {m.claimed!r}, was {m.actual!r}" for m in mm)
            findings.append(
                Finding(
                    Verdict.CONTRADICTED,
                    claim=claim,
                    call=call,
                    mismatches=mm,
                    unchecked=unchecked,
                    explanation=f"Details differ from the actual call ({parts}).",
                )
            )
        elif call.status == "error":
            findings.append(
                Finding(
                    Verdict.MASKED_FAILURE,
                    claim=claim,
                    call=call,
                    unchecked=unchecked,
                    explanation=f"{call.tool} returned an error, but the agent reported success.",
                )
            )
        else:
            findings.append(
                Finding(
                    Verdict.BACKED,
                    claim=claim,
                    call=call,
                    unchecked=unchecked,
                    explanation="Matches a successful call.",
                )
            )

    for call in trace.calls:
        if call.id in linked or call.status != "ok" or not trace.is_side_effect(call.tool):
            continue
        findings.append(
            Finding(
                Verdict.UNMENTIONED,
                call=call,
                explanation=f"{call.tool} changed something, but the agent never told the user.",
            )
        )
    return findings


def problems(findings: list[Finding], fail_on: set[Verdict] | None = None) -> list[Finding]:
    wanted = PROBLEM_VERDICTS if fail_on is None else fail_on
    return [f for f in findings if f.verdict in wanted]
