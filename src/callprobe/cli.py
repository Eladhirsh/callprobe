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
import shlex
import sys
import tempfile
from pathlib import Path

import yaml

from . import __version__
from .client import ChatClient, probe_server_version
from .compare import category_deltas, flipped_tasks, render_compare, render_compare_markdown
from .demo import INSPECT_TASK, REGRESSED_TASKS, SUITE_DIRNAME, generate_demo_files
from .examples import EXAMPLES, generate_example_suite, list_examples
from .explain import explain_run, render_explain_text
from .gates import evaluate_gate, load_policy, render_gate
from .init import generate_suite_files
from .loader import load_suite
from .openapi import generate_openapi_suite, load_openapi_file
from .models import Run, RunConfig
from .report import failure_digest, render_markdown, render_text, summarize
from .run_config import load_run_config
from .runner import prepare_config, run_suite, validate_resume
from .scoring import SCORING_VERSION
from .validate import validate_suite

# Hardcoded fallbacks used only when neither a CLI flag nor --config supplies
# a value, so a plain `callprobe run --model X` behaves exactly as before.
RUN_DEFAULTS = {
    "endpoint": "http://localhost:11434/v1",
    "pad": "0,8,16",
    "repeats": 1,
    "temperature": 0.0,
    "max_tokens": 2048,
    "retries": 3,
    "concurrency": 1,
}

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


def _same_file_target(a: str, b: str) -> bool:
    """True if two paths name the same file, including via symlink/hardlink.

    Checked before any endpoint request or output write, so `--out` can
    never be pointed at the `--failed-from` evidence it was derived from.
    """
    path_a, path_b = Path(a), Path(b)
    try:
        if path_a.exists() and path_b.exists():
            return path_a.samefile(path_b)
    except OSError:
        pass
    return path_a.resolve() == path_b.resolve()


def _select_failed_task_ids(suite, saved: Run) -> list[str]:
    """Task ids from a saved (possibly partial or interrupted) run that had
    any strict failure, truncation, or request error, in canonical suite
    order. Never merges or reuses the saved observations themselves.
    """
    if not saved.config.suite_hash or saved.config.scoring_version is None:
        raise ValueError("--failed-from: results file has no recorded suite/scoring provenance")
    if saved.config.suite_hash != suite.hash:
        raise ValueError("--failed-from: results file's suite hash does not match --suite")
    if saved.config.scoring_version != SCORING_VERSION:
        raise ValueError("--failed-from: results file's scoring version does not match this callprobe")
    known_ids = {task.id for task in suite.tasks}
    unknown = sorted({r.task_id for r in saved.results} - known_ids)
    if unknown:
        raise ValueError(
            "--failed-from: results file references task id(s) not in --suite: "
            + ", ".join(unknown)
        )
    failed = {r.task_id for r in saved.results if r.error or r.truncated or not r.success}
    return [task.id for task in suite.tasks if task.id in failed]


def _merged_run_settings(args: argparse.Namespace):
    """Resolve model/endpoint/suite/pads/... from CLI flags, --config, then
    hardcoded defaults, in that order. An explicit CLI flag always wins.

    `suite`/`out` paths that come from --config are resolved relative to the
    config file's own directory; CLI-supplied paths keep their normal
    cwd-relative meaning. The whole config file is validated up front, so an
    invalid value fails even if a CLI flag overrides that particular field.
    """
    file_config = config_dir = None
    if args.config is not None:
        file_config, config_dir = load_run_config(args.config)

    def pick(cli_value, field, default=None):
        if cli_value is not None:
            return cli_value
        if file_config is not None:
            file_value = getattr(file_config, field)
            if file_value is not None:
                return file_value
        return default

    model = pick(args.model, "model")
    if not model:
        raise ValueError("--model is required: pass --model or set model in --config")

    if args.pad is not None:
        pads = [int(p) for p in args.pad.split(",") if p.strip()]
    elif file_config is not None and file_config.pads is not None:
        pads = file_config.pads
    else:
        pads = [int(p) for p in RUN_DEFAULTS["pad"].split(",")]

    suite_arg = args.suite
    if suite_arg is None and file_config is not None and file_config.suite is not None:
        suite_arg = str(config_dir / file_config.suite)

    out = args.out
    if out is None and file_config is not None and file_config.out is not None:
        out = str(config_dir / file_config.out)

    if out and args.config and _same_file_target(out, args.config):
        raise ValueError("--out must not alias the --config file")

    return {
        "model": model,
        "endpoint": pick(args.endpoint, "endpoint", RUN_DEFAULTS["endpoint"]),
        "suite": suite_arg,
        "pads": pads,
        "repeats": pick(args.repeats, "repeats", RUN_DEFAULTS["repeats"]),
        "temperature": pick(args.temperature, "temperature", RUN_DEFAULTS["temperature"]),
        "max_tokens": pick(args.max_tokens, "max_tokens", RUN_DEFAULTS["max_tokens"]),
        "quant": pick(args.quant, "quant"),
        "notes": pick(args.notes, "notes"),
        "retries": pick(args.retries, "retries", RUN_DEFAULTS["retries"]),
        "concurrency": pick(args.concurrency, "concurrency", RUN_DEFAULTS["concurrency"]),
        "out": out,
    }


def _run(args: argparse.Namespace) -> int:
    settings = _merged_run_settings(args)
    if settings["concurrency"] < 1 or settings["max_tokens"] < 1 or settings["retries"] < 0:
        raise ValueError("concurrency/max-tokens must be positive and retries nonnegative")

    suite, suite_label = _resolve_suite(settings["suite"])
    pads = settings["pads"]

    selected_task_ids: list[str] | None = None
    if args.task:
        known_ids = {task.id for task in suite.tasks}
        unknown = sorted(set(args.task) - known_ids)
        if unknown:
            raise ValueError("--task: unknown task id(s): " + ", ".join(unknown))
        wanted = set(args.task)
        selected_task_ids = [task.id for task in suite.tasks if task.id in wanted]
    elif args.failed_from:
        if settings["out"] and _same_file_target(settings["out"], args.failed_from):
            raise ValueError("--out must not alias the --failed-from results file")
        saved = _read_run(args.failed_from)
        selected_task_ids = _select_failed_task_ids(suite, saved)
        if not selected_task_ids:
            message = f"no failed observations in {args.failed_from}; nothing to rerun"
            if args.format == "json":
                print(json.dumps({"noop": True, "message": message}, indent=2))
            else:
                print(message)
            return 0

    server_name, server_version = probe_server_version(settings["endpoint"])
    config = RunConfig(
        model=settings["model"],
        endpoint=settings["endpoint"],
        suite=suite_label,
        pads=pads,
        repeats=settings["repeats"],
        temperature=settings["temperature"],
        max_tokens=settings["max_tokens"],
        quantization=settings["quant"],
        notes=settings["notes"],
        callprobe_version=__version__,
        suite_name=suite.name,
        suite_version=suite.version,
        suite_hash=suite.hash,
        server_name=server_name,
        server_version=server_version,
        selected_task_ids=selected_task_ids,
    )
    api_key = args.api_key or os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY")
    config = prepare_config(suite, config)

    resume_run = None
    if args.resume:
        resume_run = _read_run(args.resume)
        validate_resume(config, resume_run)

    client = ChatClient(settings["endpoint"], api_key=api_key, retries=settings["retries"])

    task_count = len(config.selected_task_ids) if config.selected_task_ids is not None else len(suite.tasks)
    total = task_count * len(pads) * settings["repeats"]
    state = {"done": 0}

    def progress(result) -> None:
        state["done"] += 1
        if not args.quiet:
            mark = "." if result.success else "x"
            sys.stderr.write(mark)
            if state["done"] % 50 == 0:
                sys.stderr.write(f" {state['done']}/{total}\n")
            sys.stderr.flush()

    out = settings["out"]

    def write_partial(partial_run: Run) -> None:
        if out:
            _write_run(out, partial_run)

    try:
        run = run_suite(
            suite,
            client,
            config,
            on_result=progress,
            on_progress=write_partial if out else None,
            concurrency=settings["concurrency"],
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

    if out:
        _write_run(out, run)
        if args.format != "json":
            print(f"\nwrote {out}")

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


def _preflight_files(out: Path, files: dict[str, str], force: bool) -> None:
    """Raise if writing `files` into `out` would be unsafe. Never writes."""
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


def _write_files(out: Path, files: dict[str, str], force: bool) -> None:
    """Preflight every target, then write each file via temp + rename."""
    _preflight_files(out, files, force)
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
    example = args.example
    openapi = args.from_openapi is not None
    source = example or (args.from_openapi if openapi else args.from_file)
    try:
        if example is not None:
            files, result = generate_example_suite(example, name)
        elif openapi:
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

    out_display = shlex.quote(str(out))
    print(f"wrote {len(files)} files to {out_display}/")
    if result is not None:
        print(f"imported {len(result.tools)} operation(s) as tools")
        for item in result.skipped:
            print(f"  skipped {item['method']} {item['path']}: {item['reason']}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
    active = len(load_suite(out).tasks) if example is not None else 0
    if active:
        print(f"{active} task(s) are active and ready to run:")
    else:
        print("no tasks are active yet: uncomment and edit the drafts in tasks.yaml, then run:")
    print(f"  callprobe validate --suite {out_display}")
    return 0


def _demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    suite_out = out / SUITE_DIRNAME
    try:
        top_files, suite_files = generate_demo_files()
        # Preflight both targets before writing either: a conflict in the
        # suite subdirectory must not be discovered after top-level files
        # (baseline.json, candidate.json, DEMO.md) have already been written.
        _preflight_files(out, top_files, args.force)
        _preflight_files(suite_out, suite_files, args.force)
        _write_files(out, top_files, args.force)
        _write_files(suite_out, suite_files, args.force)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    baseline = shlex.quote(str(out / "baseline.json"))
    candidate = shlex.quote(str(out / "candidate.json"))
    suite_display = shlex.quote(str(suite_out))
    print(f"wrote {len(top_files) + len(suite_files)} files to {shlex.quote(str(out))}/")
    print()
    print("OFFLINE DEMO: recorded results, no model endpoint or network request was used.")
    print("baseline.json (Qwen2.5 7B) and candidate.json (Qwen3 8B) are byte-identical")
    print("copies of a real, historical run recorded under results/github-issues/ in the")
    print("callprobe repository; this command made no fresh model calls, and neither does")
    print("anything below. See DEMO.md for the full walkthrough.")
    print()
    print("Qwen2.5 7B passed 5/18 cases; Qwen3 8B passed 11/18, a higher aggregate score,")
    print(f"but it regressed {len(REGRESSED_TASKS)} previously passing case(s): "
          + ", ".join(REGRESSED_TASKS) + ".")
    print("That is why the regression gate below is expected to fail (exit 1) despite the")
    print("higher overall number: previously passing cases now fail.")
    print()
    print("Try it:")
    print(f"  callprobe compare {baseline} {candidate} --fail-on-regression")
    print(f"  callprobe explain {candidate} --suite {suite_display}")
    print(f"  callprobe explain {candidate} --suite {suite_display} --task {shlex.quote(INSPECT_TASK)}")
    return 0


def _examples(args: argparse.Namespace) -> int:
    for name, count, description in list_examples():
        print(f"{name}  ({count} tasks)  {description}")
    print("\nuse: callprobe init --example NAME --out DIR")
    return 0


def _compare(args: argparse.Namespace) -> int:
    a, b = _read_run(args.a), _read_run(args.b)
    gate = None
    if args.fail_on_regression or args.policy:
        policy = load_policy(args.policy)
        if args.fail_on_regression:
            policy.fail_on_regression = True
        gate = evaluate_gate(a, b, policy)
    elif a.config.selected_task_ids is not None or b.config.selected_task_ids is not None:
        sys.stderr.write(
            "warning: comparing targeted debug run(s), not full benchmark coverage\n"
        )
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
    elif args.format == "markdown":
        print(render_compare_markdown(a, b, gate))
    else:
        print(render_compare(a, b))
        if gate is not None:
            print("\n" + render_gate(gate))
    return 1 if gate is not None and not gate["passed"] else 0


def _explain(args: argparse.Namespace) -> int:
    run = _read_run(args.results)
    suite = load_suite(args.suite)
    report = explain_run(run, suite, task_id=args.task)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_explain_text(report))
    return 0


def _leaderboard(args: argparse.Namespace) -> int:
    runs = []
    for path in args.results:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        runs.append(Run(**data))
    runs.sort(key=lambda r: r.config.model)

    targeted = [r.config.model for r in runs if r.config.selected_task_ids is not None]
    if targeted:
        sys.stderr.write(
            "targeted debug run(s) cannot be included in a leaderboard "
            "(not a full benchmark), even with --allow-mixed: " + ", ".join(targeted) + "\n"
        )
        return 1

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
    run_cmd.add_argument(
        "--config", default=None,
        help="YAML file of defaults (model, endpoint, suite, pads, repeats, temperature, "
             "max_tokens, quant, notes, retries, concurrency, out); explicit flags win, "
             "never auto-discovered"
    )
    run_cmd.add_argument("--model", default=None, help="required, here or in --config")
    run_cmd.add_argument("--endpoint", default=None)
    run_cmd.add_argument("--api-key", default=None)
    run_cmd.add_argument(
        "--retries", type=int, default=None, help="retries on 429, 5xx, and connection errors"
    )
    run_cmd.add_argument(
        "--suite", default=DEFAULT_SUITE, help="suite directory, defaults to the packaged core suite"
    )
    run_cmd.add_argument("--pad", default=None)
    run_cmd.add_argument("--repeats", type=int, default=None)
    run_cmd.add_argument("--temperature", type=float, default=None)
    run_cmd.add_argument("--max-tokens", type=int, default=None)
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
        "--concurrency", type=int, default=None, help="parallel requests via a thread pool"
    )
    run_cmd.add_argument(
        "--resume",
        default=None,
        help="skip (task, pad, repeat) combinations already in this results file",
    )
    targeting = run_cmd.add_mutually_exclusive_group()
    targeting.add_argument(
        "--task",
        action="append",
        default=None,
        help="run only this task id; repeatable for a targeted debug rerun of exact ids",
    )
    targeting.add_argument(
        "--failed-from",
        dest="failed_from",
        default=None,
        help="targeted debug rerun of every task id with a strict failure, "
             "truncation, or request error in this results file, using the "
             "current pads/repeats/model settings (not the saved observations)",
    )
    run_cmd.set_defaults(func=_run)

    init_cmd = sub.add_parser(
        "init", help="scaffold a suite from an OpenAI-format tools.json, a local OpenAPI file, "
                     "or a bundled example"
    )
    source = init_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--from", dest="from_file", help="path to a tools.json")
    source.add_argument("--from-openapi", dest="from_openapi",
                        help="path to a local OpenAPI 3.0/3.1 YAML or JSON file (no network)")
    source.add_argument("--example", choices=sorted(EXAMPLES),
                        help="a bundled runnable example with authored tasks, see `callprobe examples`")
    init_cmd.add_argument("--out", default="suite", help="directory to write the suite to")
    init_cmd.add_argument("--tag", action="append", default=None,
                          help="OpenAPI only: import just operations with this tag (repeatable)")
    init_cmd.add_argument("--skip-unsupported", action="store_true",
                          help="OpenAPI only: skip operations that cannot be imported instead of failing")
    init_cmd.add_argument("--force", action="store_true",
                          help="overwrite existing generated files")
    init_cmd.set_defaults(func=_init)

    examples_cmd = sub.add_parser(
        "examples", help="list bundled runnable examples for `callprobe init --example`"
    )
    examples_cmd.set_defaults(func=_examples)

    demo_cmd = sub.add_parser(
        "demo", help="build an offline demo of the CI gate and explain, using recorded results, "
                     "no model endpoint or network access required"
    )
    demo_cmd.add_argument("--out", default="callprobe-demo", help="directory to write the demo to")
    demo_cmd.add_argument("--force", action="store_true", help="overwrite existing generated files")
    demo_cmd.set_defaults(func=_demo)

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
    compare_cmd.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    compare_cmd.set_defaults(func=_compare)

    explain_cmd = sub.add_parser(
        "explain", help="offline failure diagnostics for a saved run, no model calls"
    )
    explain_cmd.add_argument("results", help="a results JSON file written by `callprobe run --out`")
    explain_cmd.add_argument(
        "--suite", required=True,
        help="suite directory the run was scored against (must match its recorded suite hash)"
    )
    explain_cmd.add_argument("--task", default=None, help="only explain this task id, all pads/repeats")
    explain_cmd.add_argument("--format", choices=["text", "json"], default="text")
    explain_cmd.set_defaults(func=_explain)

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
    if args.command == "run" and args.fail_under is not None and (args.task or args.failed_from):
        parser.error("--fail-under cannot be combined with --task/--failed-from: "
                      "targeted runs are for debugging, not CI gating")
    try:
        if args.command == "run":
            if args.fail_under is not None and not 0 <= args.fail_under <= 1:
                raise ValueError("fail-under must be between 0 and 1")
        return args.func(args)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
