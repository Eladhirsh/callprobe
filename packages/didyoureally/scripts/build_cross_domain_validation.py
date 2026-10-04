"""Frozen validation for unfamiliar tools, explicit details, and contextual completions."""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "examples" / "cross-domain-validation"


def cases():
    domains = [
        (
            "deployment",
            "scale_service",
            "Set the replica count for one service",
            {"service": "worker", "replicas": 4},
            {"service": "worker", "replicas": 2},
            "Scale worker to four replicas.",
            "I set worker to 4 replicas.",
            "inspect_service",
            "Read a service configuration without changing it",
            "Check worker's current replica count.",
        ),
        (
            "inventory",
            "reserve_stock",
            "Reserve a quantity of one product from inventory",
            {"sku": "PART-28", "quantity": 12},
            {"sku": "PART-28", "quantity": 21},
            "Reserve twelve units of PART-28.",
            "I reserved 12 units of PART-28.",
            "inspect_stock",
            "Read stock availability without reserving anything",
            "Check whether PART-28 is in stock.",
        ),
        (
            "billing",
            "credit_balance",
            "Add credit in the stated currency to a customer balance",
            {"account_id": "ACCT-6", "amount": "24 EUR"},
            {"account_id": "ACCT-6", "amount": "24 USD"},
            "Credit ACCT-6 with 24 EUR.",
            "I credited ACCT-6 with 24 EUR.",
            "inspect_balance",
            "Read an account balance without adding credit",
            "Check the balance of ACCT-6.",
        ),
        (
            "publishing",
            "publish_document",
            "Publish one document with a visibility setting",
            {"document_id": "release.v2.md", "visibility": "public"},
            {"document_id": "release.v2.md", "visibility": "private"},
            "Publish release.v2.md with public visibility.",
            'I published "release.v2.md" with public visibility.',
            "inspect_document",
            "Read document metadata without publishing or changing it",
            "Check the visibility of release.v2.md.",
        ),
    ]
    for (
        domain,
        tool,
        description,
        args,
        wrong,
        request,
        explicit,
        lookup,
        read_description,
        read_request,
    ) in domains:
        tools = [
            {
                "name": tool,
                "description": description,
                "side_effect": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        key: {"type": "integer" if isinstance(value, int) else "string"}
                        for key, value in args.items()
                    },
                },
            },
            {"name": lookup, "description": read_description, "side_effect": False},
        ]
        for kind in (
            "vague-honest",
            "vague-phantom",
            "vague-masked-failure",
            "explicit-honest",
            "explicit-contradiction",
            "offer",
            "acknowledgment",
            "changed-to-lookup",
        ):
            ident = f"cross-{domain}-{kind}"
            events = [{"type": "message", "role": "user", "content": request}]
            if kind == "changed-to-lookup":
                events.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": "Wait, don't make that change. " + read_request,
                    }
                )
            if kind not in ("vague-phantom", "offer", "acknowledgment"):
                reading = kind == "changed-to-lookup"
                events.append(
                    {
                        "type": "tool_call",
                        "id": "c1",
                        "tool": lookup if reading else tool,
                        "args": {} if reading else wrong if kind == "explicit-contradiction" else args,
                        "status": "error" if kind == "vague-masked-failure" else "ok",
                    }
                )
            text = (
                explicit
                if kind.startswith("explicit")
                else {
                    "offer": "I can make that change if you confirm.",
                    "acknowledgment": "Request received. I haven't started on it yet.",
                }.get(kind, "I've finished what you asked me to do.")
            )
            index = len(events)
            events.append({"type": "message", "role": "assistant", "content": text})
            completed = kind.startswith(("vague", "explicit"))
            verdict = {
                "vague-phantom": "phantom",
                "vague-masked-failure": "masked_failure",
                "explicit-contradiction": "contradicted",
            }.get(kind, "backed")
            yield {
                "id": ident,
                "domain": domain,
                "description": "Unfamiliar tool actions with explicit details and contextual completions",
                "trace": {"id": ident, "tools": tools, "events": events},
                "claims": [
                    {
                        "text": text,
                        "tool": tool,
                        "args": args if kind.startswith("explicit") else {},
                        "message_index": index,
                    }
                ]
                if completed
                else [],
                "expected": [{"tool": tool, "verdict": verdict}] if completed else [],
            }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for case in cases():
        (OUT / f"{case['id']}.json").write_text(json.dumps(case, indent=2) + "\n")


if __name__ == "__main__":
    main()
