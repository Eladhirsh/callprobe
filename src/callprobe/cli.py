"""Command line interface.

    callprobe run --model qwen3:8b --endpoint http://localhost:11434/v1
    callprobe run --model llama3.1:8b --pad 0,8,16 --repeats 3 --quant q4_K_M
    callprobe leaderboard results/qwen3-8b.json results/llama31-8b.json
"""

from __future__ import annotations

import argparse
import importlib.resources
import json
import os
import sys
from pathlib import Path

from . import __version__
from .client import ChatClient, probe_server_version
from .init import generate_suite_files
from .loader import load_suite
from .models import Run, RunConfig
from .report import failure_digest, render_markdown, render_text
from .runner import interrupted_run, run_suite
from .validate import validate_suite

# Sentinel meaning "use the suite packaged inside callprobe itself", resolved
# lazily so a git checkout and a pip install both find suites/core.
DEFAULT_SUITE = None


def _resolve_suite(suite_arg: str | None):
    if suite_arg is None:
        suite_path = importlib.resources.files("callprobe") / "suites" / "core"
        suite_label = "callprobe/suites/core (packaged)"
    else:
        suite_path = suite_arg
        suite_label = suite_arg
    return load_suite(suite_path), suite_label


def _run(args: argparse.Namespace) -> int:
    suite, suite_label = _resolve_suite(args.suite)

    pads = [int(p) for p in args.pad.split(",") if p.strip()]
    server_name, server_version = probe_server_version(args.endpoint)
    config = RunConfig(
        model=args.model,
        endpoint=args.endpoint,
        suite=suite_label,
        pads=pads,
        repeats=args.repeats,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        quantization=args.quant,
        notes=args.notes,
        callprobe_version=__version__,
        suite_name=suite.name,
        suite_version=suite.version,
        suite_hash=suite.hash,
        server_name=server_name,
        server_version=server_version,
    )
    api_key = args.api_key or os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY")
    client = ChatClient(args.endpoint, api_key=api_key, retries=args.retries)

    total = len(suite.tasks) * len(pads) * args.repeats
    state = {"done": 0}

    def progress(result) -> None:
        state.setdefault("partial", []).append(result)
        state["done"] += 1
        if not args.quiet:
            mark = "." if result.success else "x"
            sys.stderr.write(mark)
            if state["done"] % 50 == 0:
                sys.stderr.write(f" {state['done']}/{total}\n")
            sys.stderr.flush()

    try:
        run = run_suite(suite, client, config, on_result=progress)
    except KeyboardInterrupt:
        sys.stderr.write("\n\ninterrupted, reporting on what finished\n\n")
        run = interrupted_run(config, state.get("partial", []))
    finally:
        client.close()
    if not args.quiet:
        sys.stderr.write("\n\n")

    print(render_text(run))
    print()
    print(failure_digest(run))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


def _validate(args: argparse.Namespace) -> int:
    suite, suite_label = _resolve_suite(args.suite)
    problems = validate_suite(suite)
    print(f"suite: {suite_label}  ({len(suite.tasks)} tasks)")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("no problems found")
    return 0


def _init(args: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.stderr.write(f"error: {args.from_file} not found\n")
        return 1

    out = Path(args.out)
    try:
        files = generate_suite_files(data, out.name)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (out / filename).write_text(content, encoding="utf-8")

    print(f"wrote {len(files)} files to {out}/")
    print("uncomment and fill in the example tasks in tasks.yaml, then run:")
    print(f"  callprobe validate --suite {out}")
    return 0


def _leaderboard(args: argparse.Namespace) -> int:
    runs = []
    for path in args.results:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        runs.append(Run(**data))
    runs.sort(key=lambda r: r.config.model)

    keys = {(r.config.suite_version, r.config.suite_hash) for r in runs}
    if len(keys) > 1 and not args.allow_mixed:
        sys.stderr.write("these runs come from different suite versions or content:\n")
        for r in runs:
            sys.stderr.write(
                f"  {r.config.model}: version={r.config.suite_version} "
                f"hash={r.config.suite_hash}\n"
            )
        sys.stderr.write("pass --allow-mixed to build the table anyway\n")
        return 1

    print(render_markdown(runs))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="callprobe")
    parser.add_argument(
        "--version", action="version", version=f"callprobe {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="score a model against a suite")
    run_cmd.add_argument("--model", required=True)
    run_cmd.add_argument("--endpoint", default="http://localhost:11434/v1")
    run_cmd.add_argument("--api-key", default=None)
    run_cmd.add_argument(
        "--retries", type=int, default=3, help="retries on 429, 5xx, and connection errors"
    )
    run_cmd.add_argument(
        "--suite", default=DEFAULT_SUITE, help="suite directory, defaults to the packaged core suite"
    )
    run_cmd.add_argument("--pad", default="0,8,16")
    run_cmd.add_argument("--repeats", type=int, default=1)
    run_cmd.add_argument("--temperature", type=float, default=0.0)
    run_cmd.add_argument("--max-tokens", type=int, default=2048)
    run_cmd.add_argument("--quant", default=None, help="label only, e.g. q4_K_M")
    run_cmd.add_argument("--notes", default=None)
    run_cmd.add_argument("--out", default=None, help="write raw results as JSON")
    run_cmd.add_argument("--quiet", action="store_true")
    run_cmd.set_defaults(func=_run)

    init_cmd = sub.add_parser(
        "init", help="scaffold a suite from an OpenAI-format tools.json"
    )
    init_cmd.add_argument(
        "--from", dest="from_file", required=True, help="path to a tools.json"
    )
    init_cmd.add_argument("--out", default="suite", help="directory to write the suite to")
    init_cmd.set_defaults(func=_init)

    validate_cmd = sub.add_parser(
        "validate", help="check task expectations against tool schemas, no model needed"
    )
    validate_cmd.add_argument(
        "--suite", default=DEFAULT_SUITE, help="suite directory, defaults to the packaged core suite"
    )
    validate_cmd.set_defaults(func=_validate)

    board = sub.add_parser("leaderboard", help="build a markdown table from runs")
    board.add_argument("results", nargs="+")
    board.add_argument(
        "--allow-mixed",
        action="store_true",
        help="build the table even if runs come from different suite versions or content",
    )
    board.set_defaults(func=_leaderboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
