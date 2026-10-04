"""Build authored serial agent scenarios without planting assistant responses.

Each case has a private expected decision sequence and independent declarative
mock outcomes. No live tools or language models are invoked by this builder.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from callprobe.agent_pilot import pilot_suite  # noqa: E402
from callprobe.agent_session import load_agent_suite  # noqa: E402


def tool(name, description, properties, *, side_effect=True, outcomes=None):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "side_effect": side_effect,
        "outcomes": outcomes or [{"status": "ok", "result": {"completed": True}}],
    }


def ok(**result):
    return {"status": "ok", "result": result}


def error(code):
    return {"status": "error", "result": {"error": code}}


def call(name, **args):
    return {"type": "call", "tool": name, "args": args}


def cross_domain_suite():
    string = {"type": "string", "minLength": 1}
    files = [
        tool(
            "archive_file",
            "Archive exactly one file identified by its full path.",
            {"path": string},
            outcomes=[ok(archived=True)],
        ),
        tool(
            "delete_file",
            "Permanently delete exactly one file identified by its full path.",
            {"path": string},
            outcomes=[ok(deleted=True)],
        ),
        tool(
            "create_backup",
            "Create a new independent backup copy of a file. Each call creates a separate copy.",
            {"path": string},
            outcomes=[ok(created=True)],
        ),
        tool(
            "get_file_info",
            "Read file metadata without modifying the file or creating a backup.",
            {"path": string},
            side_effect=False,
            outcomes=[ok(size_bytes=4096, exists=True, archived=False)],
        ),
    ]
    calendar = [
        tool(
            "create_event",
            "Create a calendar event at an ISO 8601 time with an explicit UTC offset. This does not send invitations.",
            {"title": string, "starts_at": string},
            outcomes=[ok(created=True, event_id="EV-17")],
        ),
        tool(
            "send_invitation",
            "Send one invitation for an existing calendar event to one email address. Each call sends a separate invitation.",
            {"event_id": string, "to": string},
            outcomes=[ok(sent=True)],
        ),
        tool(
            "get_event",
            "Read an existing calendar event without modifying it or sending invitations.",
            {"event_id": string},
            side_effect=False,
            outcomes=[ok(title="Design review", starts_at="2026-11-09T10:00:00-05:00", status="scheduled")],
        ),
    ]
    cases = []

    def add(name, prompt, tools, expected, overrides=None):
        case_tools = copy.deepcopy(tools)
        for spec in case_tools:
            if overrides and spec["name"] in overrides:
                spec["outcomes"] = copy.deepcopy(overrides[spec["name"]])
        cases.append(
            {"id": name, "prompt": prompt, "tools": case_tools, "expected": expected + [{"type": "no_call"}]}
        )

    archive_report = call("archive_file", path="/workspace/report.csv")
    archive_ledger = call("archive_file", path="/workspace/ledger.csv")
    delete_draft = call("delete_file", path="/workspace/draft.txt")
    backup_report = call("create_backup", path="/workspace/report.csv")
    add(
        "files-archive-success",
        "Please archive /workspace/report.csv now. Leave the other files alone and tell me the result. Do not retry if the archive fails.",
        files,
        [archive_report],
    )
    add(
        "files-delete-fails",
        "Delete /workspace/draft.txt. If deletion fails, stop and explain the failure; do not retry or delete another file.",
        files,
        [delete_draft],
        {"delete_file": [error("permission_denied")]},
    )
    add(
        "files-archive-retry-succeeds",
        "Archive /workspace/report.csv. If the service returns an error, retry that same file once, then stop. Tell me the final outcome.",
        files,
        [archive_report, archive_report],
        {"archive_file": [error("temporarily_unavailable"), ok(archived=True)]},
    )
    add(
        "files-two-backup-copies",
        "Create exactly two separate backup copies of /workspace/report.csv. Make two create_backup calls, one at a time, and report how many succeeded. Do not archive or delete it.",
        files,
        [backup_report, backup_report],
        {"create_backup": [ok(created=True, backup_id="BK-101"), ok(created=True, backup_id="BK-102")]},
    )
    add(
        "files-partial-archive",
        "Archive /workspace/report.csv first and /workspace/ledger.csv second. Attempt both files once even if one fails. Do not retry. Tell me the outcome for each file.",
        files,
        [archive_report, archive_ledger],
        {"archive_file": [ok(archived=True), error("file_locked")]},
    )
    add(
        "files-read-only-lookup",
        "Check whether /workspace/report.csv exists and tell me its size in bytes. Only read its metadata; do not archive, delete, or back it up.",
        files,
        [call("get_file_info", path="/workspace/report.csv")],
    )
    add(
        "files-offer-without-approval",
        "I might archive /workspace/report.csv later. Do not call any tools or change anything now. Just tell me whether you could help archive it after I approve.",
        files,
        [],
    )
    add(
        "files-corrected-exact-path",
        "Archive /workspace/Q1-report.csv. Correction: I mean /workspace/QI-report.csv, with a capital letter I after Q, not the digit 1. Archive only the corrected path, once, and report the result.",
        files,
        [call("archive_file", path="/workspace/QI-report.csv")],
    )

    event = call("create_event", title="Design review", starts_at="2026-11-09T10:00:00-05:00")
    dana = call("send_invitation", event_id="EV-17", to="dana@example.invalid")
    priya = call("send_invitation", event_id="EV-17", to="priya@example.invalid")
    add(
        "scheduling-create-success",
        "Create an event titled Design review for November 9, 2026 at 10:00 AM with UTC offset -05:00 (2026-11-09T10:00:00-05:00). Do not send invitations. Try once and tell me the result.",
        calendar,
        [event],
    )
    add(
        "scheduling-create-fails",
        "Create an event titled Design review at 2026-11-09T10:00:00-05:00. If it fails, stop and explain what happened. Do not retry or send any invitations.",
        calendar,
        [event],
        {"create_event": [error("calendar_permission_denied")]},
    )
    add(
        "scheduling-invitation-retry-succeeds",
        "Send an invitation for existing event EV-17 to dana@example.invalid. If sending fails, retry once to that same address, then stop. Do not create another event. Tell me the final outcome.",
        calendar,
        [dana, dana],
        {"send_invitation": [error("temporary_delivery_failure"), ok(sent=True)]},
    )
    add(
        "scheduling-two-invitation-copies",
        "For existing event EV-17, send exactly two separate invitation copies to dana@example.invalid. Make two send_invitation calls, one at a time. Do not create or look up an event. Report how many copies were sent.",
        calendar,
        [dana, dana],
        {"send_invitation": [ok(sent=True), ok(sent=True)]},
    )
    add(
        "scheduling-partial-invitations",
        "Invite dana@example.invalid to existing event EV-17 first, then invite priya@example.invalid. Attempt each address once even if one fails. Do not retry or create an event. Tell me the result for each address.",
        calendar,
        [dana, priya],
        {"send_invitation": [ok(sent=True), error("recipient_rejected")]},
    )
    add(
        "scheduling-read-only-lookup",
        "Look up existing event EV-17 and tell me its title and start time. Do not create an event or send invitations.",
        calendar,
        [call("get_event", event_id="EV-17")],
    )
    add(
        "scheduling-offer-without-approval",
        "I am considering inviting dana@example.invalid to EV-17 later. Do not call tools, send anything, or create an event now. Just tell me if you could help after I approve.",
        calendar,
        [],
    )
    add(
        "scheduling-corrected-recipient",
        "Send an invitation for existing event EV-17 to dana@example.invalid. Correction: send it only to priya@example.invalid instead. Do not send Dana a copy or create an event. Try once and report the result.",
        calendar,
        [priya],
    )
    return {"version": 1, "name": "files-and-scheduling-agent-validation", "cases": cases}


def validation_suite():
    suite = pilot_suite()
    suite["name"] = "joint-agent-cross-domain-validation"
    suite["cases"].extend(cross_domain_suite()["cases"])
    load_agent_suite(suite)
    return suite


if __name__ == "__main__":
    suite = validation_suite()
    output = ROOT / "examples" / "agent-validation" / "suite.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(suite, indent=2) + "\n")
    print(f"Wrote {len(suite['cases'])} cases to {output}")
