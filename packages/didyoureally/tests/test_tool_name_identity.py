"""Unavailable-tool aliases must not replace literal available tool names."""

import json
import runpy
from pathlib import Path

import pytest

from didyoureally import Trace, bench, check
from didyoureally.extract import LLMExtractor
from didyoureally.staged import StagedExtractor


@pytest.mark.parametrize("name", ["null", "none"])
@pytest.mark.parametrize("extractor", [LLMExtractor, StagedExtractor])
def test_available_alias_named_tool_keeps_its_identity(name, extractor):
    trace = Trace.from_dict(
        {
            "tools": [{"name": name, "side_effect": True}],
            "events": [
                {"type": "tool_call", "id": "one", "tool": name, "args": {}, "status": "ok"},
                {"type": "message", "role": "assistant", "content": "Done."},
            ],
        }
    )
    replies = [{"claims": [{"completed": True, "tool": name, "args": {}}]}]
    if extractor is StagedExtractor:
        replies.append({"details": [{"action_id": 0, "args": {}}]})
    stream = iter(replies)
    requests = []

    def transport(url, headers, body):
        requests.append(body)
        return {"choices": [{"message": {"content": json.dumps(next(stream))}}]}

    [claim] = extractor(transport=transport).extract(trace)
    assert claim.tool == name
    assert claim.message_index == 1
    assert check(trace, [claim])[0].verdict.value == "backed"
    assert len(requests) == (2 if extractor is StagedExtractor else 1)
    if extractor is StagedExtractor:
        assert json.loads(requests[1]["messages"][1]["content"])["actions"][0]["tool"] == name


@pytest.mark.parametrize("alias", ["null", "none", ""])
def test_unavailable_alias_still_maps_to_null_when_not_a_tool_name(alias):
    trace = Trace.from_dict(
        {
            "events": [{"type": "message", "role": "assistant", "content": "Escalated it."}],
        }
    )
    payload = {"claims": [{"completed": True, "tool": alias, "args": {}}]}
    extractor = LLMExtractor(
        transport=lambda *args: {
            "choices": [{"message": {"content": json.dumps(payload)}}],
        }
    )
    [claim] = extractor.extract(trace)
    assert claim.tool is None
    assert check(trace, [claim])[0].verdict.value == "phantom"


def test_json_null_stays_unavailable_when_a_literal_null_tool_exists():
    trace = Trace.from_dict(
        {
            "tools": [{"name": "null", "side_effect": True}],
            "events": [{"type": "message", "role": "assistant", "content": "Escalated it."}],
        }
    )
    payload = {"claims": [{"completed": True, "tool": None, "args": {}}]}
    [claim] = LLMExtractor(
        transport=lambda *args: {"choices": [{"message": {"content": json.dumps(payload)}}]}
    ).extract(trace)
    assert claim.tool is None
    assert check(trace, [claim])[0].verdict.value == "phantom"


@pytest.mark.parametrize("name", ["null", "none"])
def test_literal_alias_named_read_only_tool_is_still_excluded(name):
    trace = Trace.from_dict(
        {
            "tools": [{"name": name, "side_effect": False}],
            "events": [{"type": "message", "role": "assistant", "content": "I looked it up."}],
        }
    )
    payload = {"claims": [{"completed": True, "tool": name, "args": {}}]}
    assert not LLMExtractor(
        transport=lambda *args: {"choices": [{"message": {"content": json.dumps(payload)}}]}
    ).extract(trace)


@pytest.mark.parametrize("name", ["null", "none"])
def test_frozen_tool_identity_controls_match_the_generator(name):
    source = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "build_tool_identity_validation.py")
    )
    cases = [case for case in source["cases"]() if case["trace"]["tools"][0]["name"] == name]
    assert len(cases) == 2
    assert {case["expected"][0]["verdict"] for case in cases} == {"backed", "phantom"}
    for case in cases:
        assert bench.run_case(case, None).passed
        assert json.loads((source["OUT"] / f"{case['id']}.json").read_text()) == case
