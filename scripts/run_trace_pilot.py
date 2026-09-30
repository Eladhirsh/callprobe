"""Audit explicitly sanitized, labeled application captures using a pilot manifest.

Manifest: {"sanitized": true, "cases": [{"id": "...", "application": "...",
"trace": "relative-trace.json", "claims": "relative-claims.json", "expected": [...]}]}.
The trace is retained in its original supported format. Labels are never sent to the model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def prepare(manifest: Path, output: Path):
    data = json.loads(manifest.read_text())
    if data.get("sanitized") is not True or not data.get("cases"):
        raise ValueError("Provide a nonempty manifest explicitly marked sanitized: true")
    prepared = []
    seen = set()
    for entry in data["cases"]:
        cid = entry["id"]
        if (
            not isinstance(cid, str)
            or not cid
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in cid)
            or cid in seen
        ):
            raise ValueError("Case IDs must be unique safe filenames")
        seen.add(cid)
        if not entry.get("application") or not isinstance(entry.get("expected"), list):
            raise ValueError("Each capture needs its application and reviewed expected findings")
        trace = json.loads((manifest.parent / entry["trace"]).read_text())
        claims = json.loads((manifest.parent / entry["claims"]).read_text())
        if not isinstance(claims, list):
            raise ValueError("Reviewed claims must be a list")
        prepared.append(
            {
                "id": cid,
                "description": f"Sanitized capture from {entry['application']}",
                "application": entry["application"],
                "trace": trace,
                "claims": claims,
                "expected": entry["expected"],
            }
        )
    output.mkdir(parents=True, exist_ok=False)
    for case in prepared:
        (output / (case["id"] + ".json")).write_text(json.dumps(case, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--endpoint", nargs=2, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.manifest, args.out / "cases")
    command = [
        sys.executable,
        str(Path(__file__).with_name("run_llm_bench.py")),
        "--json-mode",
        "--cases",
        str(args.out / "cases"),
        "--out",
        str(args.out / "evaluation"),
    ]
    for base, model in args.endpoint:
        command += ["--endpoint", base, model]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
