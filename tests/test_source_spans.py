import json

import pytest

from didyoureally import Trace
from didyoureally.extract import parse_claims, source_spans


def trace(text):
    return Trace.from_dict(
        {
            "tools": [{"name": "delete_file"}],
            "events": [
                {"type": "message", "role": "user", "content": 'Delete "private.txt".'},
                {"type": "message", "role": "assistant", "content": text},
            ],
        }
    )


@pytest.mark.parametrize(
    "value", ["cache.log.", "résumé 2026.txt", "Folder/Case.TXT", "a+b@example.org", "A-001"]
)
def test_source_reference_copies_exact_characters(value):
    t = trace(f'I removed "{value}".')
    spans = source_spans(t.messages[-1].content)
    ref = next(s["id"] for s in spans if s["value"] == value)
    [claim] = parse_claims(
        json.dumps({"claims": [{"completed": True, "tool": "delete_file", "args": {"path": {"span": ref}}}]}),
        t,
        1,
        require_completed=True,
    )
    assert claim.args["path"] == value
    assert claim.text == t.messages[-1].content
    selected = spans[ref]
    assert claim.text[selected["start"] : selected["end"]] == value


@pytest.mark.parametrize("value", ["cache.log", "private.txt", {"span": -1}, {"span": True}, {"span": 999}])
def test_rewritten_or_context_only_identifiers_are_rejected(value):
    t = trace('I removed "cache.log.".')
    with pytest.raises(ValueError):
        parse_claims(
            json.dumps({"claims": [{"completed": True, "tool": "delete_file", "args": {"path": value}}]}),
            t,
            1,
            require_completed=True,
        )


def test_unquoted_sentence_punctuation_is_not_an_identifier():
    spans = source_spans("Removed notes.md. Sent to dana@example.net.")
    assert "notes.md" in [s["value"] for s in spans]
    assert "dana@example.net" in [s["value"] for s in spans]


def test_model_prompt_requests_values_not_numeric_pointers():
    from didyoureally.extract import SYSTEM_PROMPT, build_user_prompt

    prompt = build_user_prompt(trace("Sent! I emailed the receipt to Dana."), 1)
    assert '"Dana"' in prompt
    assert '"start"' not in prompt
    assert "never a numeric span ID" in SYSTEM_PROMPT
