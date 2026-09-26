"""Command line interface: ``didyoureally`` (alias ``dyr``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, bench
from .adapters import load_trace
from .extract import GivenClaims, LLMExtractor
from .matcher import PROBLEM_VERDICTS, Verdict, check
from .report import render_json, render_text, use_color
from .schema import load_json

EXIT_OK, EXIT_FINDINGS, EXIT_INPUT = 0, 1, 2


def _parse_fail_on(value: str) -> set[Verdict]:
    try:
        return {Verdict(v.strip()) for v in value.split(",") if v.strip()}
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{exc}. Choose from: {', '.join(v.value for v in Verdict)}"
        ) from None


def _extractor(args: argparse.Namespace, raw: object):
    if args.claims:
        return GivenClaims(load_json(args.claims))
    if isinstance(raw, dict) and "claims" in raw and args.extractor == "auto":
        return GivenClaims(raw["claims"])
    return LLMExtractor(base_url=args.base_url, model=args.model)


def cmd_check(args: argparse.Namespace) -> int:
    worst = EXIT_OK
    for path in args.traces:
        try:
            raw = load_json(path)
            trace = load_trace(raw, Path(path).stem)
            claims = _extractor(args, raw).extract(trace)
        except (OSError, ValueError, KeyError) as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return EXIT_INPUT
        findings = check(trace, claims)
        if args.format == "json":
            print(render_json(trace, findings))
        else:
            print(render_text(trace, findings, color=use_color()))
            print()
        if any(f.verdict in args.fail_on for f in findings):
            worst = EXIT_FINDINGS
    return worst


def cmd_bench(args: argparse.Namespace) -> int:
    extractor = LLMExtractor(base_url=args.base_url, model=args.model) if args.llm else None
    result = bench.run(Path(args.cases) if args.cases else None, extractor)
    print(bench.render(result))
    return EXIT_OK if result.passed == len(result.cases) else EXIT_FINDINGS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="didyoureally",
        description="Check whether an AI agent told the user the truth about what it did.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    llm = argparse.ArgumentParser(add_help=False)
    llm.add_argument("--base-url", help="OpenAI-compatible endpoint (env DYR_BASE_URL)")
    llm.add_argument("--model", help="Model for claim extraction (env DYR_MODEL)")

    c = sub.add_parser("check", parents=[llm], help="Check one or more traces")
    c.add_argument("traces", nargs="+", help="Trace files (native or OpenAI messages JSON)")
    c.add_argument("--claims", help="Use claims from this JSON file instead of extracting")
    c.add_argument(
        "--extractor",
        choices=["auto", "llm"],
        default="auto",
        help="auto uses claims embedded in the file if present, else the LLM",
    )
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.add_argument(
        "--fail-on",
        type=_parse_fail_on,
        default=set(PROBLEM_VERDICTS),
        help="Comma-separated verdicts that make the exit code 1 "
        "(default: contradicted,phantom,masked_failure)",
    )
    c.set_defaults(func=cmd_check)

    b = sub.add_parser("bench", parents=[llm], help="Run the seeded benchmark")
    b.add_argument("--cases", help="Folder of case files (default: bundled benchmark)")
    b.add_argument(
        "--llm",
        action="store_true",
        help="Extract claims with the LLM instead of the labeled ones (end to end)",
    )
    b.set_defaults(func=cmd_bench)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
