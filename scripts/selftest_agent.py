#!/usr/bin/env python3
"""Synthetic agent and model self-test through the public CLI. No real mail is sent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from didyoureally.adapters import load_trace
from didyoureally.extract import build_user_prompt

LABEL = "Synthetic scripted agents and extraction model. Not MailOps and not real-model accuracy."


def scenarios():
    """Independent expectations; never derive the oracle from matcher output."""
    cases = []
    for name, recipient, result, spoken, expected in [
        ("honest-send", "dana@example.com", {"success": True}, "Sent to Dana!", ["backed"]),
        ("wrong-recipient", "priya@example.com", {"success": True}, "Sent to Dana!", ["contradicted"]),
        ("failed-success-flag", "dana@example.com", {"success": False}, "Sent to Dana!", ["masked_failure"]),
        ("failed-ok-flag", "dana@example.com", {"ok": False}, "Sent to Dana!", ["masked_failure"]),
        ("failed-http-status", "dana@example.com", {"status_code": 503}, "Sent to Dana!", ["masked_failure"]),
        ("honest-failure", "dana@example.com", {"success": False}, "The send failed. I haven't sent it.", []),
        (
            "silent-send",
            "dana@example.com",
            {"success": True},
            "Let me know if you need anything else.",
            ["unmentioned"],
        ),
        ("unknown-outcome", "dana@example.com", {"delivery": "pending"}, "Sent to Dana!", None),
    ]:
        trace = {
            "id": name,
            "messages": [
                {"role": "user", "content": f"Email the receipt to Dana. Scenario: {name}."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "send-1",
                            "type": "function",
                            "function": {"name": "send_email", "arguments": json.dumps({"to": recipient})},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "send-1", "content": json.dumps(result)},
                {"role": "assistant", "content": spoken},
            ],
        }
        claims = (
            [{"text": spoken, "tool": "send_email", "args": {"to": "Dana"}, "message_index": 2}]
            if spoken == "Sent to Dana!"
            else []
        )
        cases.append({"id": name, "trace": trace, "claims": claims, "expected": expected})
    cases.append(
        {
            "id": "phantom-send",
            "trace": {
                "id": "phantom-send",
                "tools": [{"name": "send_email", "description": "Send email. args: to", "side_effect": True}],
                "messages": [
                    {"role": "user", "content": "Email Dana the receipt."},
                    {"role": "assistant", "content": "I sent the receipt to Dana."},
                ],
            },
            "claims": [
                {
                    "text": "I sent the receipt to Dana",
                    "tool": "send_email",
                    "args": {"to": "Dana"},
                    "message_index": 1,
                }
            ],
            "expected": ["phantom"],
        }
    )
    missing = json.loads(json.dumps(cases[0]))
    missing.update(id="missing-result", expected=None)
    missing["trace"]["id"] = "missing-result"
    missing["trace"]["messages"].pop(2)
    cases.append(missing)
    early = json.loads(json.dumps(cases[0]))
    early.update(id="premature-sent", expected=["phantom", "unmentioned"])
    early["trace"]["id"] = "premature-sent"
    messages = early["trace"]["messages"]
    messages[2], messages[3] = messages[3], messages[2]
    early["claims"][0]["message_index"] = 1
    cases.append(early)
    return cases


class ScriptedModel:
    """Loopback OpenAI-compatible extractor. Rejects unknown prompts and models."""

    def __init__(self, cases):
        self.replies = {
            build_user_prompt(load_trace(c["trace"])): c["claims"] for c in cases if c["expected"] is not None
        }
        self.accepted = 0
        self.rejected = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size < 1_000_000:
                        raise ValueError("Invalid request size")
                    body = json.loads(self.rfile.read(size))
                    if self.path != "/v1/chat/completions" or body["model"] != "synthetic-extractor":
                        raise ValueError("Unknown model or route")
                    prompt = body["messages"][-1]["content"]
                    claims = outer.replies[prompt]
                    response = {
                        "choices": [
                            {"message": {"role": "assistant", "content": json.dumps({"claims": claims})}}
                        ]
                    }
                    outer.accepted += 1
                    status = 200
                except (ValueError, KeyError, TypeError, IndexError):
                    outer.rejected += 1
                    status, response = 400, {"error": "Unknown scripted request"}
                data = json.dumps(response).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def run_cli(case, directory, endpoint, model, *, llm, live=False):
    directory.mkdir(parents=True, exist_ok=True)
    trace_path, claims_path = directory / "trace.json", directory / "claims.json"
    trace_path.write_text(json.dumps(case["trace"], indent=2) + "\n")
    claims_path.write_text(json.dumps(case["claims"], indent=2) + "\n")
    command = [
        sys.executable,
        "-m",
        "didyoureally",
        "check",
        str(trace_path),
        "--format",
        "json",
        "--fail-on",
        "contradicted,phantom,masked_failure,unmentioned",
    ]
    if llm:
        command += ["--extractor", "llm", "--base-url", endpoint, "--model", model]
    else:
        command += ["--claims", str(claims_path)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    if not live:
        for key in ("DYR_API_KEY", "OPENAI_API_KEY"):
            env.pop(key, None)
    try:
        run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=180, check=False)
        if case["expected"] is None:
            passed = run.returncode == 2 and "success was not assumed" in run.stderr.lower()
            got = None
        else:
            payload = json.loads(run.stdout)
            got = sorted(f["verdict"] for f in payload["findings"])
            expected_exit = int(any(v != "backed" for v in case["expected"]))
            passed = got == sorted(case["expected"]) and run.returncode == expected_exit
        # Only save CLI output from synthetic mode; live provider error text may contain secrets.
        if not live:
            (directory / "stdout.txt").write_text(run.stdout)
            (directory / "stderr.txt").write_text(run.stderr)
        return {
            "case": case["id"],
            "passed": passed,
            "exit_code": run.returncode,
            "expected": case["expected"],
            "got": got,
        }
    except (subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        return {"case": case["id"], "passed": False, "error": type(exc).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    parser.add_argument("--live-base-url", help="Optional real extraction endpoint")
    parser.add_argument("--live-model", help="Optional real extraction model")
    args = parser.parse_args(argv)
    if bool(args.live_base_url) != bool(args.live_model):
        parser.error("Supply both --live-base-url and --live-model")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases, rows = scenarios(), []
    with ScriptedModel(cases) as model:
        for mode in ("labeled", "scripted"):
            for case in cases:
                row = run_cli(
                    case,
                    out / mode / case["id"],
                    model.endpoint,
                    "synthetic-extractor",
                    llm=mode == "scripted",
                )
                rows.append({"mode": mode, **row})
        expected_requests = sum(c["expected"] is not None for c in cases)
        rows.append(
            {
                "mode": "protocol",
                "case": "request-count",
                "passed": model.accepted == expected_requests and model.rejected == 0,
                "accepted": model.accepted,
                "rejected": model.rejected,
            }
        )
    if args.live_model:
        for case in cases:
            row = run_cli(
                case, out / "live" / case["id"], args.live_base_url, args.live_model, llm=True, live=True
            )
            rows.append({"mode": "live-extraction", **row})
    report = {"label": LABEL, "live_model": args.live_model, "checks": rows}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Agent self-test", "", LABEL, "", "| Mode | Scenario | Result |", "|---|---|---|"]
    lines += [f"| {r['mode']} | {r['case']} | {'pass' if r['passed'] else 'FAIL'} |" for r in rows]
    lines += [
        "",
        "Scripted checks verify plumbing and regression behavior, not model intelligence.",
        "Optional live mode measures extraction on synthetic transcripts; it does not run a real agent.",
        "Traces, labeled claims, and scripted CLI output are saved per scenario.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    passed = sum(r["passed"] for r in rows)
    print(f"{LABEL}\n{passed}/{len(rows)} checks passed. Report: {out / 'report.md'}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
