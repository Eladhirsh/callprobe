import json

import pytest

from didyoureally import Trace, check
from didyoureally.datetimes import datetime_in_source, explicit_datetime
from didyoureally.extract import ExtractionError, LLMExtractor, parse_claims
from didyoureally.matcher import _argument_agrees
from didyoureally.staged import StagedExtractor

ISO = "2026-11-09T10:00:00-05:00"
PROSE = "November 9, 2026 at 10:00 AM with UTC offset -05:00"


def trace(text=None, actual=ISO):
    return Trace.from_dict(
        {
            "tools": [
                {
                    "name": "create_event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "starts_at": {"type": "string"},
                        },
                    },
                }
            ],
            "events": [
                {"type": "message", "role": "user", "content": "Create it for " + PROSE},
                {
                    "type": "tool_call",
                    "id": "c1",
                    "tool": "create_event",
                    "status": "ok",
                    "args": {"title": "Design review", "starts_at": actual},
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": text or f'Created "Design review" for {PROSE}.',
                },
            ],
        }
    )


def claims(args):
    return {"claims": [{"completed": True, "tool": "create_event", "args": args}]}


def extractor(mode, args, repaired=None):
    if mode == "default":
        replies = [claims(args)]
        if repaired is not None:
            replies.extend([claims(repaired), claims(repaired)])
        cls = LLMExtractor
    else:
        replies = [claims({}), {"details": [{"action_id": 0, "args": args}]}]
        if repaired is not None:
            replies.append({"details": [{"action_id": 0, "args": repaired}]})
        cls = StagedExtractor
    iterator = iter(replies)

    def transport(*_):
        return {"choices": [{"message": {"content": json.dumps(next(iterator))}}]}

    return cls(transport=transport)


@pytest.mark.parametrize("mode", ["default", "staged"])
@pytest.mark.parametrize("stated", [ISO, PROSE])
@pytest.mark.parametrize(
    "actual,verdict",
    [
        (ISO, "backed"),
        ("2026-11-10T10:00:00-05:00", "contradicted"),
        ("2026-11-09T11:00:00-05:00", "contradicted"),
        ("2026-11-09T10:00:00-04:00", "contradicted"),
        ("2026-11-09T15:00:00Z", "contradicted"),  # same instant, different stated clock/offset
    ],
)
def test_explicit_datetime_survives_extraction_and_detects_wrong_details(mode, stated, actual, verdict):
    t = trace(actual=actual)
    extracted = extractor(mode, {"title": "Design review", "starts_at": stated}).extract(t)
    assert extracted[0].args["starts_at"] == stated
    assert check(t, extracted)[0].verdict.value == verdict


@pytest.mark.parametrize("mode", ["default", "staged"])
@pytest.mark.parametrize(
    "repaired",
    [
        {"title": "Design review"},
        {"title": "Design review", "starts_at": "10:00 AM"},
    ],
)
def test_repair_cannot_drop_or_shorten_grounded_datetime(mode, repaired):
    first = {"title": "Design review", "starts_at": ISO, "event_id": None}
    with pytest.raises(ExtractionError) as caught:
        extractor(mode, first, repaired).extract(trace())
    assert caught.value.reason == "lost_source_detail"


@pytest.mark.parametrize("mode", ["default", "staged"])
def test_repair_can_switch_equivalent_datetime_representation(mode):
    first = {"title": "Design review", "starts_at": ISO, "event_id": None}
    repaired = {"title": "Design review", "starts_at": PROSE}
    t = trace()
    assert check(t, extractor(mode, first, repaired).extract(t))[0].verdict.value == "backed"


@pytest.mark.parametrize(
    "text",
    [
        "Created it.",  # date exists only in the user message and call, not TARGET
        "Created it November 9 at 10:00 AM UTC-05:00.",  # no year
        "Created it November 9, 2026 at 10:00 AM.",  # no offset
        "Created it 11/09/2026 at 10:00 AM UTC-05:00.",  # ambiguous numeric date
        "Created it November 9, 2026. A different event starts at 10:00 AM UTC-05:00.",
        "Created it November 9, 2026 at 10:00 AM EST.",  # no guessed zone abbreviation
        "Created it November 9, 2026 at 10:00 AM UTC-04:00.",
        "Created it tomorrow at 10:00 AM UTC-05:00.",
        "Created it November 9, 2026 at 10:00 AM UTC-05:00suffix.",
    ],
)
def test_normalized_datetime_requires_all_details_together_in_target(text):
    with pytest.raises(ValueError):
        parse_claims(json.dumps(claims({"starts_at": ISO})), trace(text), 2, require_completed=True)


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-29T10:00:00Z",
        "2026-11-09T24:00:00Z",
        "2026-11-09T10:60:00Z",
        "2026-11-09T10:00:60Z",
        "2026-11-09T10:00:00-24:00",
        "2026-11-09T10:00:00-05:60",
        "2026-11-09T10:00:00-00:00",
        "2026-11-09T10:00:00.123Z",
        "November 9, 2026 at 13:00 PM UTC-05:00",
        "November 9, 2026 at 00:00 AM UTC-05:00",
    ],
)
def test_unsupported_or_invalid_datetime_is_not_normalized(value):
    assert explicit_datetime(value) is None


@pytest.mark.parametrize(
    "prose,iso",
    [
        ("February 29, 2024 at 12:00 AM UTC+00:00", "2024-02-29T00:00:00Z"),
        ("November 9, 2026 at 12:00 PM UTC+05:30", "2026-11-09T12:00:00+05:30"),
        ("november 9 2026 at 14:30:20 UTC-05:00", "2026-11-09T14:30:20-05:00"),
    ],
)
def test_known_calendar_clock_and_offset_forms(prose, iso):
    assert explicit_datetime(prose) == explicit_datetime(iso)
    assert datetime_in_source("starts_at", iso, "Created it for " + prose + ".")
    assert _argument_agrees("starts_at", prose, iso)


def test_datetime_normalization_does_not_relax_identifiers_or_generic_text():
    for key in ["event_id", "path", "title", "body"]:
        assert not datetime_in_source(key, ISO, PROSE)
        assert not _argument_agrees(key, PROSE, ISO)
    assert not datetime_in_source("starts_at", ISO, "x" + ISO)
    assert not datetime_in_source("starts_at", ISO, ISO + ".123")


@pytest.mark.parametrize("mode", ["default", "staged"])
@pytest.mark.parametrize(
    "repaired", [{"title": "Design review"}, {"title": "Design review", "starts_at": PROSE}]
)
def test_partial_datetime_repair_must_retain_full_unambiguous_source(mode, repaired):
    first = {"title": "Design review", "starts_at": "November 9, 2026 10:00 AM"}
    ex = extractor(mode, first, repaired)
    if "starts_at" in repaired:
        assert check(trace(), ex.extract(trace()))[0].verdict.value == "backed"
    else:
        with pytest.raises(ExtractionError) as caught:
            ex.extract(trace())
        assert caught.value.reason == "lost_source_detail"


def test_ambiguous_source_dates_do_not_choose_an_argument_value():
    from didyoureally.datetimes import sole_datetime_source

    assert sole_datetime_source("starts_at", PROSE) == PROSE
    assert sole_datetime_source("title", PROSE) is None
    assert sole_datetime_source("starts_at", PROSE + " and 2026-11-10T10:00:00-05:00") is None
    assert explicit_datetime("Aprİl 1, 2026 at 10:00 AM UTC+00:00") is None
