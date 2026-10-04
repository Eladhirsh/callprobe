"""Exercise malformed JSON field shapes offline; record containment, not accuracy."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    for source in (repo / "src", repo / "packages/didyoureally/src"):
        sys.path.insert(0, str(source))
    from callprobe.cli import main as cli_main

    helpers_path = repo / "tests/test_agent_compare.py"
    helpers = runpy.run_path(str(helpers_path))
    args.out.mkdir(parents=True, exist_ok=False)
    records = []
    values = [None, [], {}, False, 0, "wrong"]
    blocks = [
        (),
        ("config",),
        ("source_sha256",),
        ("episodes", 0),
        ("episodes", 0, "audit"),
        ("episodes", 0, "completions", 0),
        ("episodes", 0, "decisions", 0),
    ]
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="agent-shape-sweep-") as folder:
        path, report = helpers["evidence"](Path(folder))
        (args.out / "baseline-report.json").write_text(json.dumps(report, indent=2) + "\n")
        shutil.copyfile(path.parent / "suite.json", args.out / "suite.json")
        for block in blocks:
            original = report
            for part in block:
                original = original[part]
            for key in original:
                for value in values:
                    candidate = copy.deepcopy(report)
                    target = candidate
                    for part in block:
                        target = target[part]
                    target[key] = value
                    path.write_text(json.dumps(candidate))
                    stdout, stderr = io.StringIO(), io.StringIO()
                    record = {"path": [*block, key], "replacement": value}
                    try:
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            code = cli_main(
                                [
                                    "agent",
                                    "compare",
                                    str(path),
                                    str(path),
                                    "--fail-on-regression",
                                    "--format",
                                    "json",
                                ]
                            )
                        record["exit_code"] = code
                        if code in (0, 1, 3) and stdout.getvalue():
                            result = json.loads(stdout.getvalue())
                            record["gate_passed"] = result["gate_passed"]
                    except Exception as exc:
                        record["uncaught_exception"] = type(exc).__name__
                        record["exception_message"] = str(exc)
                    record["stderr"] = stderr.getvalue()
                    records.append(record)
    counts = Counter(str(r.get("exit_code", "uncaught")) for r in records)
    uncaught = sum("uncaught_exception" in r for r in records)
    result = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_sha256": report["source_sha256"],
        "fixture_sha256": hashlib.sha256(helpers_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": len(records),
        "uncaught_exceptions": uncaught,
        "exit_counts": dict(counts),
        "interpretation": "This tests exception containment and records exit codes. Some replacements remain valid. It does not assert every replacement is invalid, measure detection accuracy, or prove authenticity.",
        "records": records,
    }
    (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    shutil.copyfile(__file__, args.out / "agent_compare_shape_sweep.py")
    print(json.dumps({key: result[key] for key in ("cases", "uncaught_exceptions", "exit_counts")}, indent=2))
    return int(uncaught != 0)


if __name__ == "__main__":
    raise SystemExit(main())
