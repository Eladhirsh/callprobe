"""Recompute summary and replay saved evidence, with no model requests."""

import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from callprobe.agent_compare import _replay_episode
from callprobe.agent_session import load_agent_suite

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
meta = json.loads((OUT / "provenance.json").read_text())
if meta["status"] != "finished":
    raise SystemExit("Matrix still running")
env = dict(os.environ, PYTHONPATH="src:packages/didyoureally/src")
rows = []
replays = []
for run in meta["runs"]:
    report_path = OUT / run["directory"] / "report.json"
    report = json.loads(report_path.read_text())
    episodes = report["episodes"]
    suite = load_agent_suite(json.loads((report_path.parent / "suite.json").read_text()))
    cases = {case.id: case for case in suite.cases}
    for episode in episodes:
        _replay_episode(episode, cases[episode["case_id"]], report["config"])
    seen = {episode["case_id"] for episode in episodes}
    row = {
        "model": run["model"],
        "directory": run["directory"],
        "run_status": report["status"],
        "decisions": sum(e["status"] == "complete" and e["decision_passed"] is True for e in episodes),
        "raw_decisions": sum(e["decision_passed"] is True for e in episodes),
        "accounts": sum(e["status"] == "complete" and e["account_passed"] is True for e in episodes),
        "raw_accounts": sum(e["account_passed"] is True for e in episodes),
        "both": sum(e["passed"] is True for e in episodes),
        "complete": sum(e["status"] == "complete" for e in episodes),
        "incomplete": sum(e["status"] == "incomplete" for e in episodes),
        "missing": report["planned_cases"] - len(episodes),
        "checkpointed": len(episodes),
        "planned": report["planned_cases"],
        "monotonic_elapsed_seconds": run["elapsed_seconds"],
        "exit_code": run["exit_code"],
        "complete_episode_findings": dict(
            Counter(
                f["verdict"] for e in episodes if e["status"] == "complete" for f in e["audit"]["findings"]
            )
        ),
        "raw_findings": dict(Counter(f["verdict"] for e in episodes for f in e["audit"]["findings"])),
        "agent_terminal_statuses": dict(Counter(e["agent_status"] for e in episodes)),
        "complete_account_failure_cases": [
            e["case_id"] for e in episodes if e["status"] == "complete" and e["account_passed"] is False
        ],
        "raw_account_failure_cases": [e["case_id"] for e in episodes if e["account_passed"] is False],
        "incomplete_cases": [e["case_id"] for e in episodes if e["status"] == "incomplete"],
        "missing_cases": [case.id for case in suite.cases if case.id not in seen],
        "unchecked_cases": [
            e["case_id"] for e in episodes if any(f["unchecked"] for f in e["audit"]["findings"])
        ],
        "domains": {},
    }
    for name, prefix in [("refund and email", None), ("files", "files-"), ("scheduling", "scheduling-")]:
        selected_ids = {
            case.id
            for case in suite.cases
            if (case.id.startswith(prefix) if prefix else not case.id.startswith(("files-", "scheduling-")))
        }
        subset = [e for e in episodes if e["case_id"] in selected_ids]
        row["domains"][name] = {
            "planned": len(selected_ids),
            "checkpointed": len(subset),
            "complete": sum(e["status"] == "complete" for e in subset),
            **{
                key: sum(e["status"] == "complete" and e[field] is True for e in subset)
                for key, field in [
                    ("decisions", "decision_passed"),
                    ("accounts", "account_passed"),
                    ("both", "passed"),
                ]
            },
            "incomplete": sum(e["status"] == "incomplete" for e in subset),
            "missing": len(selected_ids) - len(subset),
        }
    command = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "callprobe",
        "agent",
        "compare",
        str(report_path),
        str(report_path),
        "--format",
        "json",
        "--fail-on-regression",
    ]
    replay = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    replay_row = {
        "model": run["model"],
        "saved_episodes_replayed": len(episodes),
        "saved_episodes_consistent": True,
        "public_self_comparison_exit_code": replay.returncode,
        "public_self_comparison_stderr": replay.stderr,
        "public_self_comparison": json.loads(replay.stdout) if replay.stdout else None,
    }
    if report["status"] != "complete" or len(episodes) != report["planned_cases"]:
        assert replay.returncode == 2, (run["model"], replay.returncode, replay.stderr)
        replay_row["explanation"] = (
            "The public comparison gate correctly rejects this interrupted, partial report. Each saved episode was replayed individually above; this does not make the full run complete or eligible for model comparison."
        )
        row["eligible_for_full_suite_comparison"] = False
    else:
        assert replay.returncode == (3 if row["incomplete"] else 0), (
            run["model"],
            replay.returncode,
            replay.stderr,
        )
        row["eligible_for_full_suite_comparison"] = True
    replays.append(replay_row)
    rows.append(row)
    print(json.dumps(row, indent=2))
for row in rows[1:]:
    if not row["eligible_for_full_suite_comparison"]:
        row["comparison_skipped_reason"] = (
            "Interrupted report with missing cases; partial evidence is not ranked as a complete run."
        )
        continue
    command = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "callprobe",
        "agent",
        "compare",
        str(OUT / rows[0]["directory"] / "report.json"),
        str(OUT / row["directory"] / "report.json"),
        "--format",
        "json",
    ]
    compared = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert compared.returncode == 0, (row["model"], compared.returncode, compared.stderr)
    (OUT / f"qwen-vs-{row['directory']}.comparison.json").write_text(compared.stdout)
    row["comparison_exit_code"] = compared.returncode
(OUT / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
(OUT / "replay-checks.json").write_text(json.dumps(replays, indent=2) + "\n")
