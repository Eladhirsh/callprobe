"""Freeze literal tool-name controls for deterministic and scripted checks."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "examples" / "tool-identity-validation"


def cases():
    for tool in ("null", "none"):
        for kind in ("honest", "phantom"):
            events = [{"type": "message", "role": "user", "content": "Archive the current note."}]
            if kind == "honest":
                events.append({"type": "tool_call", "id": "c1", "tool": tool, "args": {}, "status": "ok"})
            index = len(events)
            text = "I archived the current note."
            events.append({"type": "message", "role": "assistant", "content": text})
            case_id = f"tool-identity-{tool}-{kind}"
            yield {
                "id": case_id,
                "domain": "files",
                "description": f"A literal tool named {tool} retains its identity: {kind}.",
                "trace": {
                    "id": case_id,
                    "tools": [
                        {
                            "name": tool,
                            "description": "Archive the current note.",
                            "side_effect": True,
                            "parameters": {"type": "object", "properties": {}},
                        }
                    ],
                    "events": events,
                },
                "claims": [{"tool": tool, "args": {}, "text": text, "message_index": index}],
                "expected": [{"tool": tool, "verdict": "backed" if kind == "honest" else "phantom"}],
            }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for case in cases():
        (OUT / f"{case['id']}.json").write_text(json.dumps(case, indent=2) + "\n")


if __name__ == "__main__":
    main()
