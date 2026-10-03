#!/usr/bin/env python3
"""Scripted QA agent that exercises the installed public CallProbe CLI.

Everything here is SYNTHETIC: a made-up mail workflow (examples/mail-sandbox)
answered by a scripted loopback server. It is not MailOps, not a model
benchmark, and its pass rates say nothing about any real model.

    python scripts/selftest_agent.py --out /tmp/callprobe-selftest
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

FIXTURES = Path(__file__).resolve().parent.parent / "examples" / "mail-sandbox"
LABEL = ("SYNTHETIC mail workflow self-test. Not MailOps, not a real mail API, "
         "and not a model benchmark: responses are scripted fixtures.")
MODELS = {"synthetic-baseline": "baseline", "synthetic-candidate": "candidate"}
PADS, REPEATS, PAD_ARG = [0, 2, 4], 3, "0,2,4"
TASK_COUNT, OBSERVATIONS = 18, 18 * 3 * 3
# Candidate mode injects exactly these failures; every other call is exact.
INJECTED = {"search-by-subject": "missing", "get-by-id": "missing",
            "get-missing-id": "unexpected", "reply-send": "malformed"}
FAILURE_TEXT = {"missing": "no tool call produced", "unexpected": "when no tool applied",
            "malformed": "schema:"}
TIMEOUT, RUN_TIMEOUT, LIVE_TIMEOUT = 120, 600, 1800
SECRET_VARS = ("API_KEY", "OPENAI_API_KEY")
LIMITATIONS = [
    "Fixture responses are scripted from our own expectations; they measure CLI plumbing, "
    "not model ability, and make no claim about MailOps or any real mail system.",
    "Fixed pass rates (162/162, 126/162) are construction checks, never model performance.",
    "Only the public CLI is exercised; scoring internals are checked only through its outputs.",
    "Live mode sends prompts to the given endpoint and never executes any mail operation.",
]


# ------------------------------------------------------------ scripted server


def message_key(messages) -> str:
    return json.dumps(messages, sort_keys=True)


def planned_calls(task: dict, mode: str) -> list[tuple[str, dict]]:
    """Exact calls from the authored expectation, minus injected candidate faults."""
    expect = task["expect"]
    calls = [] if expect["type"] == "no_call" else [(expect["tool"], copy.deepcopy(expect["args"]))]
    kind = INJECTED.get(task["id"]) if mode == "candidate" else None
    if kind == "missing":
        return []
    if kind == "unexpected":
        return [("get_message", {"path": {"message_id": "msg-0000"}})]
    if kind == "malformed":
        calls[0][1]["body"]["text"] = 123
    return calls


def completion_body(model: str, calls: list[tuple[str, dict]]) -> dict:
    message = {"role": "assistant",
               "content": "" if calls else "Synthetic scripted response: no tool call."}
    if calls:
        message["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(calls)]
    return {"object": "chat.completion", "model": model, "system_fingerprint": "synthetic-scripted-fixture",
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


class ScriptedServer:
    """Loopback-only OpenAI-compatible endpoint. Unknown requests are rejected, never guessed."""

    def __init__(self, tasks: list[dict]):
        self.tasks = {message_key(t["messages"]): t for t in tasks}
        self.accepted = self.rejected = self.discovery_requests = 0
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # never log request bodies
                pass

            def _send(self, status: int, body: dict):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # e.g. the CLI's /api/version probe
                with outer.lock:
                    outer.discovery_requests += 1
                if self.path == '/v1/models':
                    return self._send(200, {'data': [{'id': model} for model in MODELS]})
                self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                    model = body["model"]
                    task = outer.tasks.get(message_key(body["messages"]))
                    if self.path != "/v1/chat/completions" or model not in MODELS or task is None:
                        raise KeyError
                    response = completion_body(model, planned_calls(task, MODELS[model]))
                except (KeyError, TypeError, ValueError):
                    with outer.lock:
                        outer.rejected += 1
                    return self._send(400, {"error": "unknown scripted request"})
                with outer.lock:
                    outer.accepted += 1
                self._send(200, response)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=10)


# ------------------------------------------------------------------ the agent


class Abort(Exception):
    """A step ended with an unexpected status; later steps are skipped."""


@dataclass
class Agent:
    out: Path
    python: str
    live: tuple[str, str] | None = None

    def __post_init__(self):
        self.steps, self.assertions, self.notes = [], [], {}
        self.secrets = [os.environ[v] for v in SECRET_VARS if len(os.environ.get(v, "")) >= 4]

    def env(self, live: bool = False) -> dict:
        drop = {"PYTHONPATH", "PYTHONHOME"} | (set() if live else set(SECRET_VARS))
        return {k: v for k, v in os.environ.items() if k not in drop}

    def scrub(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def step(self, name: str, args: list[str], expected: int = 0, *, timeout: int = TIMEOUT,
             live: bool = False):
        """Run `python -m callprobe.cli ARGS` from the output directory; no shell."""
        command = [self.python, "-m", "callprobe.cli", *args]
        started, status = time.monotonic(), None
        stdout = stderr = ""
        try:
            proc = subprocess.run(command, cwd=self.out, env=self.env(live), capture_output=True,
                                  text=True, timeout=timeout, shell=False)
            status, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            stderr = f"timed out after {timeout}s\n{exc.stderr or ''}"
        except OSError as exc:
            stderr = f"could not start: {exc}"
        index = len(self.steps) + 1
        paths = {}
        for stream, text in (("stdout", stdout), ("stderr", stderr)):
            path = self.out / "artifacts" / f"{index:02d}-{name}.{stream}.txt"
            path.write_text(self.scrub(text), encoding="utf-8")
            paths[stream] = str(path.relative_to(self.out))
        ok = status == expected
        self.steps.append({"name": name, "command": self.scrub(shlex.join(command)),
                           "exit_status": status, "expected_status": expected, "ok": ok,
                           "duration_s": round(time.monotonic() - started, 3),
                           "stdout_path": paths["stdout"], "stderr_path": paths["stderr"]})
        if not ok:
            raise Abort(f"step {name}: exit {status}, expected {expected}")
        return stdout, stderr

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.assertions.append({"name": name, "ok": bool(condition), "detail": detail})
        return bool(condition)

    def load_run(self, filename: str) -> dict | None:
        try:
            return json.loads((self.out / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.check(f"{filename} is readable JSON", False, str(exc))
            return None

    def run_args(self, model: str, endpoint: str, *extra: str, pad: str = PAD_ARG,
                 repeats: int = REPEATS, max_tokens: int = 256) -> list[str]:
        return ["run", "--model", model, "--endpoint", endpoint, "--suite", "suite",
                "--pad", pad, "--repeats", str(repeats), "--temperature", "0",
                "--max-tokens", str(max_tokens), "--retries", "0", "--quiet",
                "--format", "json", *extra]

    def check_coverage(self, label: str, run: dict, task_ids: list[str], pads: list[int],
                       repeats: int) -> list[dict]:
        results = run["results"]
        want = {(t, p, r) for t in task_ids for p in pads for r in range(repeats)}
        got = [(r["task_id"], r["pad"], r["repeat"]) for r in results]
        self.check(f"{label}: coverage is exactly {len(want)} observations",
                   len(got) == len(set(got)) == len(want) and set(got) == want, f"{len(got)} rows")
        errors = [r for r in results if r["error"] is not None]
        self.check(f"{label}: no request errors", not errors, f"{len(errors)} errors")
        return results

    # ------------------------------------------------------------- workflow

    def workflow(self, tasks: list[dict]) -> None:
        self.check("authored fixtures: 18 tasks, injected ids exist",
                   len(tasks) == TASK_COUNT and set(INJECTED) <= {t["id"] for t in tasks})
        ids = [t["id"] for t in tasks]
        (self.out / "artifacts").mkdir()

        out, _ = self.step("version", ["--version"])
        self.check("--version prints callprobe version", out.startswith("callprobe "), out.strip())
        out, _ = self.step("init", ["init", "--from-openapi", str(FIXTURES / "openapi.yaml"),
                                    "--out", "suite"])
        self.check("init imported 3 operations", "imported 3 operation(s)" in out, out.strip()[:200])
        for name in ("tasks.yaml", "distractors.yaml"):
            shutil.copyfile(FIXTURES / name, self.out / "suite" / name)
        self.check("authored tasks and distractors copied byte-for-byte", all(
            hashlib.sha256((FIXTURES / n).read_bytes()).digest()
            == hashlib.sha256((self.out / "suite" / n).read_bytes()).digest()
            for n in ("tasks.yaml", "distractors.yaml")))
        out, _ = self.step("validate", ["validate", "--suite", "suite"])
        self.check("validate accepts 18 tasks", "(18 tasks)" in out and "no problems found" in out)

        with ScriptedServer(tasks) as server:
            self.check("mock server is loopback-only", server.httpd.server_address[0] == "127.0.0.1")
            endpoint = server.endpoint
            out, _ = self.step("dry-run", self.run_args("synthetic-baseline", endpoint, "--dry-run"))
            plan = json.loads(out)
            self.check("dry-run plans 162 requests", plan["total_requests"] == OBSERVATIONS
                       and plan["dry_run"] is True, str(plan.get("total_requests")))
            self.check("dry-run made no requests", server.accepted == server.rejected == server.discovery_requests == 0)

            out, _ = self.step('doctor', ['doctor', '--model', 'synthetic-baseline',
                                         '--endpoint', endpoint, '--suite', 'suite', '--format', 'json'])
            setup = json.loads(out)
            self.check('doctor confirms catalog discovery without claiming generation',
                       setup['status'] == 'pass' and setup['model_listed'] is True
                       and setup['generation_tested'] is False)
            self.check('doctor made discovery requests but no completions',
                       server.discovery_requests > 0 and server.accepted == server.rejected == 0)

            config_dir = self.out / 'config'
            config_dir.mkdir()
            (config_dir / 'doctor.yaml').write_text(yaml.safe_dump({
                'model': 'synthetic-baseline', 'endpoint': endpoint, 'suite': '../suite',
                'out': '../doctor-output.json', 'request_timeout': 900,
            }), encoding='utf-8')
            protected_output = self.out / 'doctor-output.json'
            protected_output.write_text('preserve existing output', encoding='utf-8')
            out, _ = self.step('doctor-config', ['doctor', '--config', 'config/doctor.yaml',
                                                '--format', 'json'])
            setup = json.loads(out)
            self.check('doctor config resolves its suite without generating or replacing output',
                       setup['status'] == 'pass' and setup['model_listed'] is True
                       and setup['generation_tested'] is False
                       and server.accepted == server.rejected == 0
                       and protected_output.read_text() == 'preserve existing output')

            self.step("run-baseline", self.run_args("synthetic-baseline", endpoint,
                                                    "--out", "baseline.json"), timeout=RUN_TIMEOUT)
            self.step("run-candidate", self.run_args("synthetic-candidate", endpoint,
                                                     "--out", "candidate.json"), timeout=RUN_TIMEOUT)
            baseline, candidate = self.load_run("baseline.json"), self.load_run("candidate.json")
            if not (baseline and candidate):
                raise Abort("run results missing")
            rows = self.check_coverage("baseline", baseline, ids, PADS, REPEATS)
            self.check("baseline: 162 successes", sum(r["success"] for r in rows) == OBSERVATIONS)
            rows = self.check_coverage("candidate", candidate, ids, PADS, REPEATS)
            failed = {r["task_id"] for r in rows if not r["success"]}
            self.check("candidate: 126 successes", sum(r["success"] for r in rows) == OBSERVATIONS - 36)
            self.check("candidate: exactly the 4 injected tasks fail", failed == set(INJECTED),
                       ", ".join(sorted(failed)))
            for task_id, kind in INJECTED.items():
                texts = " ".join(" ".join(r["failures"]) for r in rows if r["task_id"] == task_id)
                self.check(f"candidate: {task_id} fails as injected ({kind})", FAILURE_TEXT[kind] in texts)

            # Exit 1 here is the regression gate working, not a tool failure.
            out, err = self.step("compare-json", ["compare", "baseline.json", "candidate.json",
                                                  "--fail-on-regression", "--format", "json"], 1)
            compared = json.loads(out)
            regressions = compared["gate"]["regressions"]
            self.check("gate: failed on regression, nothing else",
                       compared["gate"]["passed"] is False and len(compared["gate"]["failures"]) == 1
                       and "regressed" in compared["gate"]["failures"][0])
            self.check("gate: 36 regressed observations across 4 unique tasks",
                       len(regressions) == 36 and {r["task_id"] for r in regressions} == set(INJECTED)
                       and compared["regressed_tasks"] == sorted(INJECTED), f"{len(regressions)} rows")
            self.check("gate exit carried no tool error", "Traceback" not in err and "error:" not in err)
            out, err = self.step("compare-markdown", ["compare", "baseline.json", "candidate.json",
                                                      "--fail-on-regression", "--format", "markdown"], 1)
            self.check("markdown compare shows FAIL gate, 162 scored each, 0 request errors",
                       "**CI gate:** FAIL" in out and "Scored observations: 162 -> 162" in out
                       and "Request errors: 0 -> 0" in out)
            out, _ = self.step("explain", ["explain", "candidate.json", "--suite", "suite",
                                           "--format", "json"])
            self.check("explain (offline) reports failed cases", json.loads(out)["failed_cases"] > 0)

            self.step("targeted-rerun", self.run_args("synthetic-candidate", endpoint, "--failed-from",
                                                      "candidate.json", "--out", "targeted.json",
                                                      pad="0", repeats=1), timeout=RUN_TIMEOUT)
            targeted = self.load_run("targeted.json")
            if targeted:
                rows = self.check_coverage("targeted", targeted, sorted(INJECTED), [0], 1)
                self.check("targeted: 4 rows for the 4 failed task ids",
                           len(rows) == 4 and {r["task_id"] for r in rows} == set(INJECTED))
            _, err = self.step("targeted-as-baseline", ["compare", "targeted.json", "candidate.json",
                                                        "--fail-on-regression", "--format", "json"], 2)
            self.check("targeted run rejected as CI baseline", "targeted debug run" in err, err.strip()[:200])

            self.check("server: 328 scripted requests accepted, none rejected",
                       (server.accepted, server.rejected) == (2 * OBSERVATIONS + 4, 0),
                       f"accepted={server.accepted} rejected={server.rejected}")
            if self.live:
                self.live_steps()

    def live_steps(self) -> None:
        """Same suite at pad 0 / repeats 1 against a user-supplied endpoint.

        Wrong model answers are findings; transport errors fail the self-test.
        """
        model, endpoint = self.live
        self.step("live-run", self.run_args(model, endpoint, "--out", "live.json", pad="0", repeats=1,
                                            max_tokens=4096), timeout=LIVE_TIMEOUT, live=True)
        run = self.load_run("live.json")
        if run:
            rows = self.check_coverage("live", run, [t["id"] for t in yaml.safe_load(
                (FIXTURES / "tasks.yaml").read_text(encoding="utf-8"))["tasks"]], [0], 1)
            self.notes["live_findings"] = {
                "model": model, "observations": len(rows), "successes": sum(r["success"] for r in rows),
                "model_mistakes": {r["task_id"]: r["failures"] for r in rows
                                   if not r["success"] and not r["error"]},
                "note": "Live results are findings about that model on this synthetic suite, "
                        "saved in live.json. They are not part of the fixture assertions."}
        explained, _ = self.step("live-explain", ["explain", "live.json", "--suite", "suite",
                                                   "--format", "json"], live=True)
        diagnostics = json.loads(explained)
        if "live_findings" in self.notes:
            self.notes["live_findings"]["argument_shape_summary"] = diagnostics.get(
                "argument_shape_summary")



# -------------------------------------------------------------------- report


def render_markdown(report: dict) -> str:
    lines = [f"# CallProbe self-test: {report['overall']}", "", f"**{LABEL}**", "",
             f"- Python under test: `{report['python']}`", f"- Live mode: {report['live']}",
             f"- Duration: {report['duration_s']}s", ""]
    if report.get("error"):
        lines += [f"**Runner error:** {report['error']}", ""]
    lines += ["## Steps", "", "| # | Step | Exit | Expected | OK | Seconds | Output |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, s in enumerate(report["steps"], 1):
        lines.append(f"| {i} | {s['name']} | {s['exit_status']} | {s['expected_status']} | "
                     f"{'yes' if s['ok'] else 'NO'} | {s['duration_s']} | "
                     f"`{s['stdout_path']}`, `{s['stderr_path']}` |")
    lines += ["", "Commands:", ""] + [f"{i}. `{s['command']}`" for i, s in enumerate(report["steps"], 1)]
    lines += ["", "## Assertions", ""]
    lines += [f"- [{'x' if a['ok'] else ' '}] {a['name']}" + (f" ({a['detail']})" if a["detail"] and not a["ok"] else "")
              for a in report["assertions"]]
    if "live_findings" in report["notes"]:
        live = report["notes"]["live_findings"]
        lines += ["", "## Live findings (separate from fixtures)", "",
                  f"{live['model']}: {live['successes']}/{live['observations']} at pad 0, repeats 1.",
                  live["note"], ""]
        shape = live.get("argument_shape_summary")
        if shape and shape["affected_observations"]:
            lines += [f"Argument shape hints: {shape['affected_observations']} observations "
                      f"across {shape['unique_tasks']} tasks.",
                      "Inspect the live-explain artifact for proposed arguments. These are advisory; "
                      "values may still be wrong and scores have not changed.", ""]
        lines += [f"- {task}: {'; '.join(why)}" for task, why in live["model_mistakes"].items()]
    lines += ["", "## Known limitations", ""] + [f"- {item}" for item in LIMITATIONS]
    return "\n".join(lines) + "\n"


def write_report(agent: Agent, started: float, error: str | None, python: str) -> dict:
    ok = not error and bool(agent.steps) and all(s["ok"] for s in agent.steps) \
        and all(a["ok"] for a in agent.assertions)
    report = {"overall": "PASS" if ok else "FAIL", "label": LABEL, "python": python,
              "live": "enabled" if agent.live else "disabled",
              "duration_s": round(time.monotonic() - started, 3), "error": error,
              "steps": agent.steps, "assertions": agent.assertions, "notes": agent.notes,
              "limitations": LIMITATIONS}
    for name, text in (("report.json", json.dumps(report, indent=2) + "\n"),
                       ("report.md", render_markdown(report))):
        with open(agent.out / name, "x", encoding="utf-8") as handle:  # never overwrite
            handle.write(agent.scrub(text))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic mail self-test for the CallProbe CLI.")
    parser.add_argument("--out", required=True, help="new or empty output directory")
    parser.add_argument("--python", default=sys.executable, help="interpreter with callprobe installed")
    parser.add_argument("--live-model", help="optional; requires --live-endpoint")
    parser.add_argument("--live-endpoint", help="optional; requires --live-model")
    args = parser.parse_args(argv)
    if bool(args.live_model) != bool(args.live_endpoint):
        parser.error("--live-model and --live-endpoint must be given together")

    # Keep relative virtualenv paths valid after subprocesses change directory.
    args.python = os.path.abspath(os.path.expanduser(args.python)) if os.path.dirname(args.python) else (shutil.which(args.python) or args.python)

    out = Path(args.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print(f"error: refusing to use {out}: it must be a new or empty directory", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    out = out.resolve()

    live = (args.live_model, args.live_endpoint) if args.live_model else None
    agent, started, error = Agent(out, args.python, live), time.monotonic(), None
    try:
        tasks = yaml.safe_load((FIXTURES / "tasks.yaml").read_text(encoding="utf-8"))["tasks"]
        agent.workflow(tasks)
    except Abort as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - any runner bug must still yield a report
        error = f"{type(exc).__name__}: {exc}"
    finally:
        report = write_report(agent, started, error, args.python)
    print(f"{report['overall']}: {sum(a['ok'] for a in agent.assertions)}/{len(agent.assertions)} "
          f"assertions, {len(agent.steps)} steps; report at {out / 'report.md'}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
