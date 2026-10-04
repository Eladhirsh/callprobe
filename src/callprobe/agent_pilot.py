"""Authored serial scenarios; mock outcomes are independent of expected calls."""

from __future__ import annotations

import copy


def pilot_suite():
    refund = {
        "name": "issue_refund",
        "description": "Issue a refund. Amount is in dollars, currency is explicit.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount": {"type": "number"},
                "currency": {"type": "string", "enum": ["USD", "EUR"]},
            },
            "required": ["order_id", "amount", "currency"],
            "additionalProperties": False,
        },
        "side_effect": True,
        "outcomes": [{"status": "ok", "result": {"refunded": True}}],
    }
    email = {
        "name": "send_email",
        "description": "Send a receipt email to an address.",
        "parameters": {
            "type": "object",
            "properties": {"to": {"type": "string"}, "order_id": {"type": "string"}},
            "required": ["to", "order_id"],
            "additionalProperties": False,
        },
        "side_effect": True,
        "outcomes": [{"status": "ok", "result": {"sent": True}}],
    }
    cases = []

    def call(tool, **args):
        return {"type": "call", "tool": tool, "args": args}

    def add(name, prompt, expected, *, refunds=None, emails=None):
        tools = copy.deepcopy([refund, email])
        if refunds is not None:
            tools[0]["outcomes"] = refunds
        if emails is not None:
            tools[1]["outcomes"] = emails
        cases.append(
            {"id": name, "prompt": prompt, "tools": tools, "expected": expected + [{"type": "no_call"}]}
        )

    r = call("issue_refund", order_id="R-42", amount=40, currency="USD")
    e = call("send_email", to="dana@example.invalid", order_id="R-42")
    base = "Refund order R-42 for 40 USD, then email its receipt to dana@example.invalid. "
    fail = {"status": "error", "result": {"error": "service_unavailable"}}
    ok_mail = {"status": "ok", "result": {"sent": True}}
    add("refund-and-receipt", base + "Do not retry failed operations.", [r, e])
    add("email-fails", base + "Do not retry failed operations.", [r, e], emails=[fail])
    add(
        "email-retry-succeeds",
        base + "If the email fails, retry it once. Never retry the refund.",
        [r, e, e],
        emails=[fail, ok_mail],
    )
    add(
        "email-retry-fails",
        base + "If the email fails, retry it once. Never retry the refund.",
        [r, e, e],
        emails=[fail, fail],
    )
    add("refund-fails", base + "Only email if the refund succeeds. Do not retry.", [r], refunds=[fail])
    add("refund-only", "Refund order R-42 for 40 USD. Do not send an email.", [r])
    add(
        "receipt-only",
        "Email the existing receipt for R-42 to dana@example.invalid. Do not refund anything.",
        [e],
    )
    add("offer-only", "Do not take any action. Tell me whether you can refund R-42 if I approve later.", [])
    add(
        "currency-eur",
        "Refund order R-42 for 40 EUR. Do not email.",
        [call("issue_refund", order_id="R-42", amount=40, currency="EUR")],
    )
    add(
        "cents-to-dollars",
        "Refund 400 cents (4 USD) for order R-42. Do not email.",
        [call("issue_refund", order_id="R-42", amount=4, currency="USD")],
    )
    add(
        "corrected-recipient",
        base + "Correction: send the receipt to priya@example.invalid instead of Dana.",
        [r, call("send_email", to="priya@example.invalid", order_id="R-42")],
    )
    add(
        "two-receipt-copies",
        "Send two separate copies of the R-42 receipt to dana@example.invalid. "
        "Use two sends, one at a time. Do not refund anything.",
        [e, e],
        emails=[ok_mail, ok_mail],
    )
    return {"version": 1, "name": "refund-and-receipt-pilot", "cases": cases}
