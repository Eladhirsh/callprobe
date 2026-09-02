"""Command line interface.

    canitcall run --model qwen3:8b --endpoint http://localhost:11434/v1
    canitcall run --model llama3.1:8b --pad 0,8,16 --repeats 3 --quant q4_K_M
    canitcall leaderboard results/*.json > LEADERBOARD.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .client import ChatClient
from .loader import load_suite
from .models import Run, RunConfig
from .report import failure_digest, render_markdown, render_text
from .runner import interrupted_run, run_suite

DEFAULT_SUITE = Path(__file__).resolve().parents[2] / "suites" / "core"


def _run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    pads = [int(p) for p in args.pad.split(",") if p.strip()]
    config = RunConfig(
        model=args.model,
        endpoint=args.endpoint,
        suite=str(args.suite),
        pads=pads,
        repeats=args.repeats,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        quantization=args.quant,
        notes=args.notes,
    )
    client = ChatClient(args.endpoint, api_key=args.api_key or os.getenv("API_KEY"))

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


def _leaderboard(args: argparse.Namespace) -> int:
    runs = []
    for path in args.results:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        runs.append(Run(**data))
    runs.sort(key=lambda r: r.config.model)
    print(render_markdown(runs))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canitcall")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="score a model against a suite")
    run_cmd.add_argument("--model", required=True)
    run_cmd.add_argument("--endpoint", default="http://localhost:11434/v1")
    run_cmd.add_argument("--api-key", default=None)
    run_cmd.add_argument("--suite", default=str(DEFAULT_SUITE))
    run_cmd.add_argument("--pad", default="0,8,16")
    run_cmd.add_argument("--repeats", type=int, default=1)
    run_cmd.add_argument("--temperature", type=float, default=0.0)
    run_cmd.add_argument("--max-tokens", type=int, default=2048)
    run_cmd.add_argument("--quant", default=None, help="label only, e.g. q4_K_M")
    run_cmd.add_argument("--notes", default=None)
    run_cmd.add_argument("--out", default=None, help="write raw results as JSON")
    run_cmd.add_argument("--quiet", action="store_true")
    run_cmd.set_defaults(func=_run)

    board = sub.add_parser("leaderboard", help="build a markdown table from runs")
    board.add_argument("results", nargs="+")
    board.set_defaults(func=_leaderboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
