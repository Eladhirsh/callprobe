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
import tempfile
from pathlib import Path

import yaml

from . import __version__
from .client import ChatClient, probe_server_version
from .compare import category_deltas, flipped_tasks, render_compare
from .gates import evaluate_gate, load_policy, render_gate
from .init import generate_suite_files
from .loader import load_suite
from .openapi import generate_openapi_suite, load_openapi_file
from .models import Run, RunConfig
from .report import failure_digest, render_markdown, render_text, summarize
from .runner import prepare_config, run_suite, validate_resume
from .validate import validate_suite

# Sentinel meaning "use the suite packaged inside callprobe itself", resolved
# lazily so a git checkout and a pip install both find suites/core.
DEFAULT_SUITE = None


def _read_run(path: str) -> Run:
    return Run.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _write_run(path: str, run: Run) -> None:
    """An interrupted write must not destroy a resumable checkpoint."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out.parent,
                                         prefix=f".{out.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(run.model_dump_json(indent=2))
        temporary.replace(out)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _resolve_suite(suite_arg: str | None):
    if suite_arg is None:
        suite_path = importlib.resources.files("callprobe") / "suites" / "core"
        suite_label = "callprobe/suites/core (packaged)"
    else:
        suite_path = suite_arg
        suite_label = suite_arg
    return load_suite(suite_path), suite_label


def _json_safe(value):
    """inf shows up as tokens/seconds per success with no successes.

    json.dumps emits it as a bare Infinity token, which is not valid JSON
    per the spec and trips up strict parsers like jq. Map it to null.
    """
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


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
    config = prepare_config(suite, config)

    resume_run = None
    if args.resume:
        resume_run = _read_run(args.resume)
        validate_resume(config, resume_run)

    client = ChatClient(args.endpoint, api_key=api_key, retries=args.retries)

    total = len(suite.tasks) * len(pads) * args.repeats
    state = {"done": 0}

    def progress(result) -> None:
        state["done"] += 1
        if not args.quiet:
            mark = "." if result.success else "x"
            sys.stderr.write(mark)
            if state["done"] % 50 == 0:
                sys.stderr.write(f" {state['done']}/{total}\n")
            sys.stderr.flush()

    def write_partial(partial_run: Run) -> None:
        if args.out:
            _write_run(args.out, partial_run)

    try:
        run = run_suite(
            suite,
            client,
            config,
            on_result=progress,
            on_progress=write_partial if args.out else None,
            concurrency=args.concurrency,
            resume=resume_run,
        )
    finally:
        client.close()
    if not args.quiet:
        sys.stderr.write("\n\n")

    summary = summarize(run)
    if args.format == "json":
        print(json.dumps(_json_safe(summary), indent=2))
    else:
        print(render_text(run))
        print()
        print(failure_digest(run))

    if args.out:
        _write_run(args.out, run)
        if args.format != "json":
            print(f"\nwrote {args.out}")

    if args.fail_under is not None:
        if summary["errors"] or len(run.results) != total or not summary["n"]:
            sys.stderr.write("CI gate failed: run is incomplete or contains request errors\n")
            return 1
        if summary["overall"]["success"] < args.fail_under:
            return 1
    return 0


def _validate(args: argparse.Namespace) -> int:
    suite, suite_label = _resolve_suite(args.suite)
    problems = validate_suite(suite)
    print(f"suite: {suite_label}  ({len(suite.tasks)} tasks)")
    if not suite.tasks:
        print(
            "  no active tasks: open tasks.yaml, uncomment and edit at least one task\n"
            "  (a call task and a no_call abstention task are both recommended), then re-run validate"
        )
        return 1
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("no problems found")
    return 0


def _write_files(out: Path, files: dict[str, str], force: bool) -> None:
    """Preflight every target, then write each file via temp + rename."""
    if out.exists() and not out.is_dir():
        raise ValueError(f"{out} exists and is not a directory")
    conflicts = [name for name in files if os.path.lexists(out / name)]
    if any((out / name).is_dir() for name in conflicts):
        raise ValueError(f"cannot overwrite directory in {out}: {', '.join(conflicts)}")
    if conflicts and not force:
        raise ValueError(
            f"refusing to overwrite existing file(s) in {out}: {', '.join(conflicts)} "
            "(pass --force to replace them)"
        )
    out.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out,
                                             prefix=f".{filename}.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
            temporary.replace(out / filename)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _init(args: argparse.Namespace) -> int:
    out = Path(args.out)
    name = out.resolve().name or "suite"
    openapi = args.from_openapi is not None
    source = args.from_openapi if openapi else args.from_file
    try:
        if openapi:
            document = load_openapi_file(source)
            files, result = generate_openapi_suite(
                document, name, tags=args.tag, skip_unsupported=args.skip_unsupported
            )
        else:
            files = generate_suite_files(json.loads(Path(source).read_text(encoding="utf-8")), name)
            result = None
        _write_files(out, files, args.force)
    except FileNotFoundError:
        sys.stderr.write(f"error: {source} not found\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    print(f"wrote {len(files)} files to {out}/")
    if result is not None:
        print(f"imported {len(result.tools)} operation(s) as tools")
        for item in result.skipped:
            print(f"  skipped {item['method']} {item['path']}: {item['reason']}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        print("no tasks are active yet: uncomment and edit the drafts in tasks.yaml, then run:")
    else:
        print("uncomment and fill in the example tasks in tasks.yaml, then run:")
    print(f"  callprobe validate --suite {out}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    a, b = _read_run(args.a), _read_run(args.b)
    gate = None
    if args.fail_on_regression or args.policy:
        policy = load_policy(args.policy)
        if args.fail_on_regression:
            policy.fail_on_regression = True
        gate = evaluate_gate(a, b, policy)
    if a.config.suite_hash != b.config.suite_hash:
        sys.stderr.write(
            f"warning: suite hashes differ (a={a.config.suite_hash}, "
            f"b={b.config.suite_hash}); some of this delta may be the suite "
            "changing, not the model\n"
        )
    if a.config.scoring_version != b.config.scoring_version:
        sys.stderr.write("warning: scoring versions differ; scores are not directly comparable\n")
    if args.format == "json":
        regressions, improvements = flipped_tasks(a, b)
        print(json.dumps({"by_category": category_deltas(a, b),
                          "regressed_tasks": regressions, "improved_tasks": improvements,
                          "gate": gate}, indent=2))
    else:
        print(render_compare(a, b))
        if gate is not None:
            print("\n" + render_gate(gate))
    return 1 if gate is not None and not gate["passed"] else 0


def _leaderboard(args: argparse.Namespace) -> int:
    runs = []
    for path in args.results:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        runs.append(Run(**data))
    runs.sort(key=lambda r: r.config.model)

    keys = {(r.config.suite_version, r.config.suite_hash, r.config.scoring_version) for r in runs}
    if len(keys) > 1 and not args.allow_mixed:
        sys.stderr.write("these runs come from different suites or scoring versions:\n")
        for r in runs:
            sys.stderr.write(
                f"  {r.config.model}: version={r.config.suite_version} "
                f"hash={r.config.suite_hash} scoring={r.config.scoring_version}\n"
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
    run_cmd.add_argument("--format", choices=["text", "json"], default="text")
    run_cmd.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="exit 1 if overall success is below this fraction, e.g. 0.7",
    )
    run_cmd.add_argument(
        "--concurrency", type=int, default=1, help="parallel requests via a thread pool"
    )
    run_cmd.add_argument(
        "--resume",
        default=None,
        help="skip (task, pad, repeat) combinations already in this results file",
    )
    run_cmd.set_defaults(func=_run)

    init_cmd = sub.add_parser(
        "init", help="scaffold a suite from an OpenAI-format tools.json or a local OpenAPI file"
    )
    source = init_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--from", dest="from_file", help="path to a tools.json")
    source.add_argument("--from-openapi", dest="from_openapi",
                        help="path to a local OpenAPI 3.0/3.1 YAML or JSON file (no network)")
    init_cmd.add_argument("--out", default="suite", help="directory to write the suite to")
    init_cmd.add_argument("--tag", action="append", default=None,
                          help="OpenAPI only: import just operations with this tag (repeatable)")
    init_cmd.add_argument("--skip-unsupported", action="store_true",
                          help="OpenAPI only: skip operations that cannot be imported instead of failing")
    init_cmd.add_argument("--force", action="store_true",
                          help="overwrite existing generated files")
    init_cmd.set_defaults(func=_init)

    validate_cmd = sub.add_parser(
        "validate", help="check task expectations against tool schemas, no model needed"
    )
    validate_cmd.add_argument(
        "--suite", default=DEFAULT_SUITE, help="suite directory, defaults to the packaged core suite"
    )
    validate_cmd.set_defaults(func=_validate)

    compare_cmd = sub.add_parser(
        "compare", help="diff two runs: per-category deltas and which tasks flipped"
    )
    compare_cmd.add_argument("a")
    compare_cmd.add_argument("b")
    compare_cmd.add_argument("--fail-on-regression", action="store_true",
                             help="fail if any matched passing case regresses; requires complete runs")
    compare_cmd.add_argument("--policy", help="YAML CI policy; enables gating")
    compare_cmd.add_argument("--format", choices=["text", "json"], default="text")
    compare_cmd.set_defaults(func=_compare)

    board = sub.add_parser("leaderboard", help="build a markdown table from runs")
    board.add_argument("results", nargs="+")
    board.add_argument(
        "--allow-mixed",
        action="store_true",
        help="build the table even if runs come from different suite versions or content",
    )
    board.set_defaults(func=_leaderboard)

    args = parser.parse_args(argv)
    if args.command == "init" and args.from_openapi is None and (args.tag or args.skip_unsupported):
        parser.error("--tag and --skip-unsupported require --from-openapi")
    try:
        if args.command == "run":
            if args.concurrency < 1 or args.max_tokens < 1 or args.retries < 0:
                raise ValueError("concurrency/max-tokens must be positive and retries nonnegative")
            if args.fail_under is not None and not 0 <= args.fail_under <= 1:
                raise ValueError("fail-under must be between 0 and 1")
        return args.func(args)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
