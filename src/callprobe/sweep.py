"""Run CallProbe against several models already served at one endpoint, one at a time.

Never downloads or pulls a model and never overwrites output. Each model gets a dry run
(all before any real run), then a run at temperature 0, concurrency 1, retries 0. A failed
step is recorded and the sweep moves on. The leaderboard and explain reports use only
result files written by successful runs of this invocation.

    callprobe sweep --models a b --out /tmp/sweep [--suite DIR] [--dry-run]

A leaderboard over a few tasks and repeats is a small sample: it does not show that the
ordering of models is robust, and nothing here repairs or adjusts a score.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1"
SECRET_VARS = ("API_KEY", "OPENAI_API_KEY")
NOTE = ("Small-sample results: this leaderboard does not establish a robust model ranking. "
        "Scores are as the CLI reported them, with no repair.")


def check_endpoint(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("endpoint must be an http(s) URL with a host")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError("endpoint must not embed credentials")
    if parts.query or parts.fragment or "?" in url or "#" in url:
        raise ValueError("endpoint must not contain a query or fragment")
    return url


def check_models(models: list[str]) -> list[str]:
    if len(set(models)) != len(models):
        raise ValueError("model names must be unique")
    for name in models:
        if not name.strip() or any(c in name for c in "\r\n\0"):
            raise ValueError("model names must be non-blank single-line strings")
    return models


def resolve_python(value: str) -> str:
    # Absolute but not symlink-resolved: a venv python must keep its own prefix.
    if os.path.dirname(value):
        return os.path.abspath(os.path.expanduser(value))
    return shutil.which(value) or value


def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}


def redact(text: str) -> str:
    for var in SECRET_VARS:
        secret = os.environ.get(var)
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def as_text(data) -> str:
    if data is None:
        return ""
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else data


class Sweep:
    def __init__(self, args: argparse.Namespace, out: Path):
        self.args, self.out = args, out
        self.python = resolve_python(args.python)
        self.suite = os.path.abspath(args.suite) if args.suite else None
        self.manifest: dict = {
            "note": NOTE, "dry_run": args.dry_run, "endpoint": args.endpoint,
            "suite": self.suite, "pad": args.pad, "repeats": args.repeats,
            "max_tokens": args.max_tokens, "timeout_seconds": args.timeout,
            "request_timeout_seconds": args.request_timeout, "junit": args.junit,
            "total_planned_requests": None, "models": [], "leaderboard": None,
            "failed": False, "status": "running",
        }

    def save(self) -> None:
        # Readers and interrupted writes must retain the last complete manifest.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.out,
                                             prefix=".manifest.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(json.dumps(self.manifest, indent=2) + "\n")
            temporary.replace(self.out / "manifest.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def fail(self, entry: dict) -> None:
        entry["status"] = "failed"
        self.manifest["failed"] = True

    def cli(self, *cli_args: str) -> list[str]:
        return [self.python, "-m", "callprobe.cli", *cli_args]

    def run_args(self, model: str) -> list[str]:
        a = self.args
        base = ["run", f"--model={model}", f"--endpoint={a.endpoint}", f"--pad={a.pad}",
                f"--repeats={a.repeats}", "--temperature=0", f"--max-tokens={a.max_tokens}",
                "--concurrency=1", "--retries=0",
                f"--request-timeout={a.request_timeout}"]
        return base + ([f"--suite={self.suite}"] if self.suite else [])

    def step(self, entry: dict, name: str, command: list[str]):
        """Run one subprocess, save its output, record the outcome. Never raises.

        Returns the completed process on success, else None.
        """
        step = {"name": name, "command": command, "status": "running", "returncode": None}
        entry["steps"].append(step)
        self.save()
        start, stdout, stderr, proc = time.monotonic(), "", "", None
        try:
            proc = subprocess.run(command, cwd=self.out, env=clean_env(), shell=False,
                                  capture_output=True, text=True, timeout=self.args.timeout)
            stdout, stderr, step["returncode"] = proc.stdout, proc.stderr, proc.returncode
            step["status"] = "ok"
            if proc.returncode != 0:
                step["status"] = "failed"
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = as_text(exc.stdout), as_text(exc.stderr)
            step["status"] = "timeout"
        except OSError as exc:
            stderr, step["status"] = f"could not start: {exc}\n", "error"
        step["duration_seconds"] = round(time.monotonic() - start, 3)
        prefix = f"{entry['slot']}-{name}"
        for stream, text in (("stdout", stdout), ("stderr", stderr)):
            path = self.out / f"{prefix}.{stream}.txt"
            path.write_text(redact(as_text(text)))
            step[stream] = path.name
        if step["status"] != "ok":
            self.fail(entry)
        self.save()
        return proc if step["status"] == "ok" else None

    def dry_runs(self) -> None:
        total = 0
        for entry in self.manifest["models"]:
            proc = self.step(entry, "dry-run",
                             self.cli(*self.run_args(entry["model"]), "--dry-run", "--format=json"))
            planned = None
            if proc is not None:
                try:
                    planned = int(json.loads(proc.stdout)["total_requests"])
                except (ValueError, KeyError, TypeError):
                    entry["steps"][-1]["status"] = "unparsable"
                    self.fail(entry)
            entry["planned_requests"] = planned
            total += planned or 0
        self.manifest["total_planned_requests"] = total
        self.save()
        print(f"planned requests: {total} across {len(self.manifest['models'])} model(s)", flush=True)

    def real_runs(self) -> None:
        for entry in self.manifest["models"]:
            if entry["status"] == "failed":  # dry run failed: send no real requests
                print(f"{entry['slot']}: skipped (dry run failed)")
                continue
            print(f"{entry['slot']}: running {entry['model']}", flush=True)
            result = self.out / f"{entry['slot']}-result.json"
            proc = self.step(entry, "run", self.cli(*self.run_args(entry["model"]),
                                                    "--quiet", "--fail-under=0", f"--out={result.name}"))
            if result.is_file():
                entry["raw_result_file"] = result.name
            if proc is not None and result.is_file():
                entry["result_file"] = result.name
                if self.suite:
                    self.step(entry, "explain",
                              self.cli("explain", result.name, f"--suite={self.suite}"))
            elif proc is not None:
                self.fail(entry)
            if self.args.junit and result.is_file():
                self.export_junit(entry)
            print(f"{entry['slot']}: {entry['status']}", flush=True)
            self.save()

    def export_junit(self, entry: dict) -> None:
        """Export per-model JUnit XML from the raw results file. Never calls the model.

        Runs even for failed/timeout runs that still produced a partial file.
        Records ``junit_file`` only after the child command returns zero and the
        expected output exists; a missing file is a failure. Raw results are
        preserved in all cases.
        """
        junit_name = f"{entry['slot']}-junit.xml"
        proc = self.step(entry, "report",
                         self.cli("report", entry["raw_result_file"], "--format=junit", f"--out={junit_name}"))
        if proc is None:
            return
        if (self.out / junit_name).is_file():
            entry["junit_file"] = junit_name
        else:
            entry["steps"][-1]["status"] = "missing-file"
            self.fail(entry)
        self.save()

    def leaderboard(self) -> None:
        ok = [e for e in self.manifest["models"] if e.get("result_file")]
        if not ok:
            return
        board = {"slot": "leaderboard", "status": "ok", "steps": []}
        proc = self.step(board, "board", self.cli("leaderboard", *[e["result_file"] for e in ok]))
        if proc is not None:
            (self.out / "leaderboard.md").write_text(redact(proc.stdout))
            self.manifest["leaderboard"] = {"file": "leaderboard.md",
                                            "models": [e["model"] for e in ok]}
        else:
            self.manifest["leaderboard"] = {"file": None, "status": board["steps"][-1]["status"]}
        self.manifest["leaderboard"]["steps"] = board["steps"]
        self.save()
        print(NOTE)

    def go(self) -> int:
        self.manifest["models"] = [{"slot": f"{i:02d}", "model": m, "status": "ok", "steps": []}
                                   for i, m in enumerate(self.args.models, 1)]
        self.save()
        self.dry_runs()
        if not self.args.dry_run:
            self.real_runs()
            self.leaderboard()
        self.manifest["status"] = "failed" if self.manifest["failed"] else (
            "planned" if self.args.dry_run else "complete")
        self.save()
        return 1 if self.manifest["failed"] else 0


def positive(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def add_arguments(p: argparse.ArgumentParser) -> None:
    """Register the sweep options on a parser or subparser."""
    p.add_argument("--models", nargs="+", required=True,
                   help="unique names of models the endpoint already serves (never downloaded)")
    p.add_argument("--out", required=True, help="new directory; must not exist")
    p.add_argument("--suite", default=None, help="suite directory (enables offline explain)")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--pad", default="0")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-tokens", dest="max_tokens", type=int, default=4096)
    p.add_argument("--timeout", type=positive, default=1800.0, help="seconds per step")
    p.add_argument(
        "--request-timeout", dest="request_timeout", type=positive, default=120.0,
        help="HTTP operation timeout in seconds (positive finite float, default 120); "
             "forwarded to each child `callprobe run`",
    )
    p.add_argument("--junit", action="store_true",
                   help="also export per-model JUnit XML by invoking the child CLI's `report` "
                        "command on each raw result (including partial files); never makes extra "
                        "model calls and no exports happen under --dry-run")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="plan only")


def run_sweep(args: argparse.Namespace) -> int:
    """Validate a parsed namespace and run the sweep. Returns the process exit code."""
    try:
        check_models(args.models)
        check_endpoint(args.endpoint)
        if args.repeats < 1 or args.max_tokens < 1:
            raise ValueError("repeats and max-tokens must be positive")
        out = Path(args.out).absolute()
        out.mkdir(parents=True)  # FileExistsError if present: never overwrite
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return Sweep(args, out).go()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="callprobe sweep", description=__doc__.split("\n\n")[0])
    add_arguments(p)
    return run_sweep(p.parse_args(argv))
