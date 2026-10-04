"""Optional joint Callprobe and Didyoureally command surface."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agent_session import (
    load_agent_suite,
    render_agent_report,
    require_auditor,
    run_episode,
    suite_hash,
)
from .client import ChatClient
from .doctor import validate_endpoint


def audit_main(argv):
    require_auditor()
    from didyoureally.cli import main

    return main(["check", *argv])


def add_agent_arguments(parser):
    commands = parser.add_subparsers(dest="agent_command", required=True)
    init = commands.add_parser("init", help="write the mock refund and receipt pilot suite")
    init.add_argument("--out", required=True, help="new JSON suite file")
    init.set_defaults(func=init_agent_suite)
    run = commands.add_parser("run", help="run a real agent against declarative mock tools")
    run.add_argument("--suite", required=True)
    run.add_argument("--model", required=True, help="agent model")
    run.add_argument("--endpoint", default="http://localhost:11434/v1")
    run.add_argument("--extractor-model", required=True, help="independently configured claim extractor")
    run.add_argument("--extractor-endpoint", help="defaults to the agent endpoint")
    run.add_argument("--max-turns", type=int, default=8)
    run.add_argument("--max-tokens", type=int, default=2048)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--json-mode", action="store_true", help="JSON mode for the extractor only")
    run.add_argument("--out", required=True, help="new results directory")
    run.set_defaults(func=run_agent_suite)
    compare = commands.add_parser("compare", help="compare saved agent runs without model calls")
    compare.add_argument("baseline", help="baseline report.json with its frozen suite.json beside it")
    compare.add_argument("candidate", help="candidate report.json with its frozen suite.json beside it")
    compare.add_argument("--format", choices=["markdown", "json"], default="markdown")
    compare.add_argument("--fail-on-regression", action="store_true")
    from .agent_compare import agent_compare_main

    compare.set_defaults(func=agent_compare_main)


def init_agent_suite(args):
    from .agent_pilot import pilot_suite

    suite = load_agent_suite(pilot_suite())
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(suite.model_dump(), indent=2) + "\n")
    print(f"Wrote {len(suite.cases)} mock agent cases to {path}")
    return 0


def _save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(data, encoding="utf-8")
    temporary.replace(path)


def _source_hashes(package):
    root = Path(package.__file__).parent
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))}


def run_agent_suite(args):
    dyr = require_auditor()
    import callprobe
    from didyoureally.extract import LLMExtractor

    endpoint = validate_endpoint(args.endpoint, args.timeout)
    extractor_endpoint = validate_endpoint(args.extractor_endpoint or endpoint, args.timeout)
    if not args.model.strip() or not args.extractor_model.strip():
        raise ValueError("agent and extractor model IDs must not be blank")
    if not 1 <= args.max_turns <= 100 or args.max_tokens <= 0:
        raise ValueError("max-turns must be 1 to 100 and max-tokens must be positive")
    suite = load_agent_suite(json.loads(Path(args.suite).read_text(encoding="utf-8")))
    if any(len(case.expected) > args.max_turns for case in suite.cases):
        raise ValueError("max-turns is smaller than a case's planned decision sequence")
    report = {
        "format_version": 1,
        "status": "running",
        "execution": "declarative_mocks",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "suite_hash": suite_hash(suite),
        "suite_name": suite.name,
        "planned_cases": len(suite.cases),
        "episodes": [],
        "config": {
            "agent_model": args.model,
            "agent_endpoint": endpoint,
            "extractor_model": args.extractor_model,
            "extractor_endpoint": extractor_endpoint,
            "max_turns": args.max_turns,
            "max_tokens": args.max_tokens,
            "agent_timeout": args.timeout,
            "extractor_timeout": 120,
            "extractor_json_mode": args.json_mode,
            "temperature": 0,
            "agent_retries": 0,
        },
        "source_sha256": {"callprobe": _source_hashes(callprobe), "didyoureally": _source_hashes(dyr)},
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    _save(out / "suite.json", json.dumps(suite.model_dump(), indent=2) + "\n")

    def save():
        _save(out / "report.json", json.dumps(report, indent=2, allow_nan=False) + "\n")
        _save(out / "report.md", render_agent_report(report))

    save()
    client = ChatClient(
        endpoint,
        api_key=os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY"),
        timeout=args.timeout,
        retries=0,
    )
    extractor = LLMExtractor(
        base_url=extractor_endpoint,
        model=args.extractor_model,
        api_key=os.environ.get("DYR_API_KEY"),
        json_mode=args.json_mode,
    )
    requests = []
    transport = extractor.transport

    def capture(url, headers, body):
        request_snapshot = copy.deepcopy(body)
        response = transport(url, headers, body)
        requests.append({"request": request_snapshot, "response": copy.deepcopy(response)})
        return response

    extractor.transport = capture
    try:
        for case in suite.cases:
            requests.clear()
            row = run_episode(
                case,
                client,
                extractor,
                model=args.model,
                max_turns=args.max_turns,
                max_tokens=args.max_tokens,
            )
            row["extraction_requests"] = list(requests)
            report["episodes"].append(row)
            (out / "traces").mkdir(exist_ok=True)
            _save(out / "traces" / f"{case.id}.json", json.dumps(row["trace"], indent=2) + "\n")
            if row["audit"]["status"] == "complete":
                (out / "claims").mkdir(exist_ok=True)
                _save(out / "claims" / f"{case.id}.json", json.dumps(row["audit"]["claims"], indent=2) + "\n")
            save()
            print(
                f"{case.id}: {row['status']}; decisions={row['decision_passed']}; "
                f"account={row['account_passed']}",
                flush=True,
            )
        report["status"] = "complete"
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        return 130
    except Exception:
        report["status"] = "failed"
        # Never echo transport exception strings, which can include credentials.
        raise ValueError("agent run failed; completed case evidence was preserved") from None
    finally:
        client.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    if any(row["status"] == "incomplete" for row in report["episodes"]):
        return 3
    return 0 if all(row["passed"] for row in report["episodes"]) else 1
