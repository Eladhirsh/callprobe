"""Exhaustively check grouped reservation against independent enumeration.

Run with PYTHONPATH pointing to Didyoureally's src directory. No network calls,
repository writes, language models, or private benchmark labels are involved.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
from pathlib import Path

from didyoureally import matcher, schema


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify():
    checked = 0
    failures = []
    by_status_pattern = {}
    for edges in itertools.product((0, 1), repeat=9):
        for statuses in itertools.product(("ok", "error"), repeat=3):
            calls = [
                schema.ToolCall(
                    str(j),
                    "send_email",
                    {str(i): edges[i * 3 + j] for i in range(3)},
                    status=statuses[j],
                    index=j,
                )
                for j in range(3)
            ]
            claims = [
                schema.Claim(
                    "completed",
                    "send_email",
                    {str(i): 1},
                    message_index=3,
                    group_id="g",
                )
                for i in range(3)
            ]
            trace = schema.Trace("oracle", {"send_email": schema.ToolSpec("send_email")}, calls)
            assigned = matcher._reserve_group_calls(trace, list(enumerate(claims)), set())
            measured = (sum(c.status == "ok" for c in assigned.values()), len(assigned))

            # Enumerate every injective partial assignment directly from the
            # input graph. This does not use the matcher's comparison helper or
            # augmenting-path algorithm to establish the expected optimum.
            best = (0, 0)
            for mapping in itertools.product((None, 0, 1, 2), repeat=3):
                used = [j for j in mapping if j is not None]
                if len(used) != len(set(used)):
                    continue
                if any(j is not None and not edges[i * 3 + j] for i, j in enumerate(mapping)):
                    continue
                best = max(best, (sum(statuses[j] == "ok" for j in used), len(used)))

            valid_edges = all(edges[i * 3 + int(call.id)] for i, call in assigned.items())
            unique_calls = len({call.id for call in assigned.values()}) == len(assigned)
            if measured != best or not valid_edges or not unique_calls:
                failures.append(
                    {
                        "edges_row_major": edges,
                        "statuses": statuses,
                        "measured": measured,
                        "optimum": best,
                        "valid_edges": valid_edges,
                        "unique_calls": unique_calls,
                    }
                )
            checked += 1
            key = ",".join(statuses)
            by_status_pattern[key] = by_status_pattern.get(key, 0) + 1
    return {
        "kind": "exhaustive_group_allocation_oracle",
        "status": "passed" if not failures else "failed",
        "scope": {
            "claims": 3,
            "calls": 3,
            "compatibility_graphs": 512,
            "status_patterns": 8,
            "objective": "Maximize successful compatible assignments, then all compatible assignments.",
            "invariants": [
                "Every assigned edge is compatible.",
                "Each call is assigned at most once.",
            ],
            "limitations": "Exhaustive only for three claims and three calls; no model extraction or production accuracy claim.",
        },
        "configurations_checked": checked,
        "configurations_per_status_pattern": by_status_pattern,
        "failures_count": len(failures),
        "failures": failures,
        "provenance": {
            "python_version": platform.python_version(),
            "script_sha256": sha256(__file__),
            "matcher_sha256": sha256(matcher.__file__),
            "schema_sha256": sha256(schema.__file__),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = verify()
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"{report['configurations_checked']} configurations, {report['failures_count']} failures; {args.out}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
