import copy
import dataclasses
import random
from pathlib import Path

import pytest

from callprobe.client import Completion
from callprobe.loader import load_suite
from callprobe.models import Call, RunConfig
from callprobe.recordings import RecordedCompletion, score_recordings
from callprobe.runner import run_suite

SUITE = Path(__file__).resolve().parents[1] / "src" / "callprobe" / "suites" / "core"


@pytest.fixture(scope="module")
def suite():
    return load_suite(SUITE)


def _config(**kwargs):
    base = dict(
        model="caller-assertion",
        endpoint="http://unused",
        suite="stub",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=64,
    )
    base.update(kwargs)
    return RunConfig(**base)


def _no_network(monkeypatch):
    # score_recordings must never construct an HTTP client; make sure of it.
    import httpx

    def _boom(*args, **kwargs):
        raise AssertionError("score_recordings must not touch the network")

    monkeypatch.setattr(httpx, "Client", _boom)
    monkeypatch.setattr(httpx, "get", _boom)


def _canned(task_id: str) -> Completion:
    # Deterministic, caller-asserted metadata the scorer must preserve.
    return Completion(
        content=f"no action for {task_id}",
        prompt_tokens=11,
        completion_tokens=7,
        latency_ms=42.0,
        finish_reason="stop",
    )


class _ByMessages:
    """Deterministic fake client: one canned Completion per task's messages."""

    def __init__(self, suite):
        self._index = {
            tuple((m.get("role"), m.get("content")) for m in task.messages): task.id
            for task in suite.tasks
        }
        self.calls = 0

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        self.calls += 1
        key = tuple((m.get("role"), m.get("content")) for m in messages)
        return _canned(self._index[key])


def _recordings_for(suite, config):
    return [
        RecordedCompletion(
            task_id=task.id, completion=_canned(task.id), pad=pad, repeat=repeat,
        )
        for pad in config.pads
        for repeat in range(config.repeats)
        for task in suite.tasks
    ]


def test_matches_run_suite_output_for_identical_completions(suite, monkeypatch):
    config = _config(pads=[0, 4], repeats=2)
    live = run_suite(suite, _ByMessages(suite), config)
    _no_network(monkeypatch)  # from here on, no HTTP is permitted
    recorded = score_recordings(suite, config, _recordings_for(suite, config))

    live_dump = [r.model_dump() for r in live.results]
    recorded_dump = [r.model_dump() for r in recorded.results]
    assert live_dump == recorded_dump
    assert recorded.config.suite_hash == live.config.suite_hash
    assert recorded.config.scoring_version == live.config.scoring_version
    assert recorded.started_at and recorded.finished_at


def test_canonical_order_regardless_of_input_order(suite, monkeypatch):
    _no_network(monkeypatch)
    config = _config(pads=[8, 0], repeats=2)  # pad config order is [8, 0], not sorted
    records = _recordings_for(suite, config)
    shuffled = list(records)
    random.Random(0).shuffle(shuffled)
    run = score_recordings(suite, config, shuffled)

    actual = [(r.pad, r.repeat, r.task_id) for r in run.results]
    expected = [
        (pad, repeat, task.id)
        for pad in config.pads
        for repeat in range(config.repeats)
        for task in suite.tasks
    ]
    assert actual == expected


def test_partial_input_stays_partial(suite, monkeypatch):
    _no_network(monkeypatch)
    config = _config(pads=[0, 4], repeats=3)
    picks = [suite.tasks[0], suite.tasks[2]]
    records = [
        RecordedCompletion(task_id=t.id, completion=_canned(t.id), pad=0, repeat=0)
        for t in picks
    ]
    run = score_recordings(suite, config, records)
    assert len(run.results) == len(records)
    expected = {(r.task_id, r.pad, r.repeat) for r in records}
    assert {(r.task_id, r.pad, r.repeat) for r in run.results} == expected


def test_targeted_selection_accepts_only_selected_tasks(suite, monkeypatch):
    _no_network(monkeypatch)
    first, second = suite.tasks[0].id, suite.tasks[1].id
    other = suite.tasks[2].id
    config = _config(selected_task_ids=[first, second])

    run = score_recordings(suite, config, [
        RecordedCompletion(task_id=first, completion=_canned(first)),
        RecordedCompletion(task_id=second, completion=_canned(second)),
    ])
    assert [r.task_id for r in run.results] == [first, second]

    with pytest.raises(ValueError, match="outside the current selection"):
        score_recordings(suite, config, [
            RecordedCompletion(task_id=other, completion=_canned(other)),
        ])


def test_rejects_empty_input(suite):
    with pytest.raises(ValueError, match="no recordings"):
        score_recordings(suite, _config(), [])


def test_rejects_duplicate_identity(suite, monkeypatch):
    _no_network(monkeypatch)
    tid = suite.tasks[0].id
    with pytest.raises(ValueError, match="duplicates"):
        score_recordings(suite, _config(), [
            RecordedCompletion(task_id=tid, completion=_canned(tid)),
            RecordedCompletion(task_id=tid, completion=_canned(tid)),
        ])


def test_rejects_unknown_task(suite):
    with pytest.raises(ValueError, match="unknown task"):
        score_recordings(suite, _config(), [
            RecordedCompletion(
                task_id="task-does-not-exist",
                completion=_canned("task-does-not-exist"),
            ),
        ])


def test_rejects_out_of_plan_pad(suite):
    tid = suite.tasks[0].id
    with pytest.raises(ValueError, match="pad is not in"):
        score_recordings(suite, _config(pads=[0]), [
            RecordedCompletion(task_id=tid, completion=_canned(tid), pad=7),
        ])


def test_rejects_out_of_plan_repeat(suite):
    tid = suite.tasks[0].id
    with pytest.raises(ValueError, match="repeat is outside"):
        score_recordings(suite, _config(repeats=2), [
            RecordedCompletion(task_id=tid, completion=_canned(tid), repeat=5),
        ])


@pytest.mark.parametrize("field,value", [
    ("pad", True),
    ("pad", False),
    ("pad", 0.0),
    ("repeat", True),
    ("repeat", 1.0),
])
def test_rejects_boolean_or_noninteger_coordinates(suite, field, value):
    tid = suite.tasks[0].id
    kwargs = {"task_id": tid, "completion": _canned(tid)}
    kwargs[field] = value
    with pytest.raises(ValueError, match="plain integer"):
        score_recordings(suite, _config(), [RecordedCompletion(**kwargs)])


def test_rejects_non_completion_payload(suite):
    tid = suite.tasks[0].id
    # The frozen dataclass is not runtime-validated, so a bogus payload
    # must be rejected before any scoring is attempted.
    bogus = RecordedCompletion(task_id=tid, completion="not a completion")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="payload is not a Completion"):
        score_recordings(suite, _config(), [bogus])


def test_huge_repeat_count_is_bounded_by_recorded_input(suite, monkeypatch):
    _no_network(monkeypatch)
    config = _config(repeats=1_000_000)
    tid = suite.tasks[0].id
    run = score_recordings(suite, config, [
        RecordedCompletion(task_id=tid, completion=_canned(tid), repeat=0),
        RecordedCompletion(task_id=tid, completion=_canned(tid), repeat=999_999),
    ])
    assert len(run.results) == 2
    assert [r.repeat for r in run.results] == [0, 999_999]


def test_malformed_tool_arguments_remain_scored_failures(suite, monkeypatch):
    _no_network(monkeypatch)
    task = next(t for t in suite.tasks if t.id == "select-status-direct")
    broken = Completion(
        calls=[Call(
            name="get_order_status", raw_arguments="{oops",
            parse_error="Expecting property name",
        )],
        prompt_tokens=5, completion_tokens=3, latency_ms=9.0,
        finish_reason="tool_calls",
    )
    run = score_recordings(suite, _config(), [
        RecordedCompletion(task_id=task.id, completion=broken),
    ])
    result = run.results[0]
    assert not result.success and not result.success_lenient
    assert any("did not parse" in f for f in result.failures)
    assert result.calls[0].raw_arguments == "{oops"
    assert result.calls[0].parse_error == "Expecting property name"


@pytest.mark.parametrize("err", ["timeout", ""])
def test_non_null_request_errors_are_preserved_and_excluded_from_success(
    suite, monkeypatch, err,
):
    _no_network(monkeypatch)
    abstain = next(t for t in suite.tasks if t.category == "abstain")
    completion = Completion(error=err, latency_ms=25.0)
    run = score_recordings(suite, _config(), [
        RecordedCompletion(task_id=abstain.id, completion=completion),
    ])
    result = run.results[0]
    assert result.error == err
    assert not result.success and not result.success_lenient
    assert result.failures == [f"request failed: {err}"]
    # The result is present in the Run even for an empty-string error —
    # it is not silently dropped as a no-call abstention success.
    assert len(run.results) == 1


def test_preserves_tokens_latency_truncation_and_all_calls(suite, monkeypatch):
    _no_network(monkeypatch)
    task = next(t for t in suite.tasks if t.id == "select-status-direct")
    completion = Completion(
        calls=[Call(
            id="call_x", name="get_order_status",
            arguments={"order_id": "ORD-448120"},
            raw_arguments='{"order_id":"ORD-448120"}',
        )],
        prompt_tokens=99, completion_tokens=44, latency_ms=123.5,
        finish_reason="length",
    )
    run = score_recordings(suite, _config(), [
        RecordedCompletion(task_id=task.id, completion=completion),
    ])
    result = run.results[0]
    assert result.prompt_tokens == 99 and result.completion_tokens == 44
    assert result.latency_ms == 123.5
    assert result.truncated and result.finish_reason == "length"
    assert result.calls[0].id == "call_x"
    assert result.calls[0].arguments == {"order_id": "ORD-448120"}


def test_preserves_caller_model_label_as_assertion(suite, monkeypatch):
    _no_network(monkeypatch)
    tid = suite.tasks[0].id
    run = score_recordings(suite, _config(model="whatever-the-caller-says"), [
        RecordedCompletion(task_id=tid, completion=_canned(tid)),
    ])
    assert all(r.model == "whatever-the-caller-says" for r in run.results)


def test_recorded_completion_is_frozen():
    rc = RecordedCompletion(task_id="x", completion=Completion())
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.task_id = "y"  # type: ignore[misc]


def test_does_not_mutate_inputs(suite, monkeypatch):
    _no_network(monkeypatch)
    tid = suite.tasks[0].id
    completion = Completion(
        calls=[Call(
            name="get_order_status",
            arguments={"order_id": "ORD-448120"},
            raw_arguments='{"order_id":"ORD-448120"}',
        )],
        prompt_tokens=1, completion_tokens=1, latency_ms=1.0,
        finish_reason="tool_calls",
    )
    completion_snapshot = copy.deepcopy(completion)
    config = _config()
    config_snapshot = config.model_copy(deep=True)
    suite_snapshot = suite.model_dump()

    score_recordings(suite, config, [
        RecordedCompletion(task_id=tid, completion=completion),
    ])
    # Caller's config is unchanged; provenance only lands on the returned Run.
    assert config.model_dump() == config_snapshot.model_dump()
    assert config.task_ids is None and config.suite_hash is None
    # Caller's Completion evidence survives untouched.
    assert completion == completion_snapshot
    assert suite.model_dump() == suite_snapshot


def test_provenance_recorded_via_prepare_config_with_utc_timestamps(
    suite, monkeypatch,
):
    _no_network(monkeypatch)
    tid = suite.tasks[0].id
    run = score_recordings(suite, _config(), [
        RecordedCompletion(task_id=tid, completion=_canned(tid)),
    ])
    assert run.config.suite_hash == suite.hash
    assert run.config.suite_name == suite.name
    assert run.config.scoring_version is not None
    assert run.config.task_ids == [t.id for t in suite.tasks]
    assert run.started_at.endswith("+00:00")
    assert run.finished_at.endswith("+00:00")


@pytest.mark.parametrize("task_id", [[], {}, None, 12])
def test_invalid_task_id_type_is_a_safe_value_error(suite, task_id):
    with pytest.raises(ValueError, match="task id must be a string"):
        score_recordings(suite, _config(), [
            RecordedCompletion(task_id, Completion()),
        ])


def test_validates_entire_batch_before_scoring(suite, monkeypatch):
    import callprobe.recordings as module
    def unexpected(*args, **kwargs):
        raise AssertionError("scoring started before validation finished")
    monkeypatch.setattr(module, "score", unexpected)
    record = RecordedCompletion(suite.tasks[0].id, Completion())
    with pytest.raises(ValueError, match="duplicates"):
        score_recordings(suite, _config(), iter([record, record]))


def test_recorded_results_use_current_evaluator_version(suite):
    from callprobe import __version__
    config = _config(callprobe_version="old-import-source")
    run = score_recordings(suite, config, [RecordedCompletion(suite.tasks[0].id, Completion())])
    assert run.config.callprobe_version == __version__
    assert config.callprobe_version == "old-import-source"
    run.config.pads.append(9)
    assert config.pads == [0]


def test_archived_llamacpp_decisions_preserve_scores_and_call_evidence(monkeypatch):
    from callprobe.models import Run
    from callprobe.report import summarize
    _no_network(monkeypatch)
    root = Path(__file__).resolve().parents[1] / "results/2026-10-02-llamacpp-validation/evidence"
    for name in ("core", "mail"):
        source = root / name / "01-result.json"
        before = source.read_bytes()
        original = Run.model_validate_json(before)
        suite = load_suite(root / (name + "-suite"))
        assert suite.hash == original.config.suite_hash
        records = [RecordedCompletion(
            task_id=r.task_id, pad=r.pad, repeat=r.repeat,
            completion=Completion(
                calls=r.calls, content=r.response_text, error=r.error,
                prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens,
                latency_ms=r.latency_ms, finish_reason=r.finish_reason,
            ),
        ) for r in original.results]
        replay = score_recordings(suite, original.config, reversed(records))
        # Archived response_text is a 300-character digest, not the original
        # completion text; rescoring may trim its trailing cut-off whitespace.
        assert [r.model_dump(exclude={"response_text"}) for r in replay.results] == [
            r.model_dump(exclude={"response_text"}) for r in original.results
        ]
        assert summarize(replay) == summarize(original)
        assert source.read_bytes() == before



def test_every_call_is_preserved_even_when_only_one_matches(suite):
    task = next(t for t in suite.tasks if t.expect.tool)
    calls = [Call(name=task.expect.tool), Call(name="unexpected_extra_tool")]
    run = score_recordings(suite, _config(), [
        RecordedCompletion(task.id, Completion(calls=calls)),
    ])
    result = run.results[0]
    assert result.calls == calls
    assert not result.call_count_ok and not result.success
    assert result.calls[0] is not calls[0]


@pytest.mark.parametrize("field,value", [
    ("calls", {}), ("calls", None), ("calls", ()), ("calls", ["PRIVATE_PAYLOAD"]),
    ("content", []), ("content", None), ("content", False),
    ("reasoning", {}), ("reasoning", None),
    ("finish_reason", []), ("finish_reason", None),
    ("error", False), ("error", {"PRIVATE_PAYLOAD": 1}),
    ("prompt_tokens", -1), ("prompt_tokens", True), ("prompt_tokens", "7"),
    ("completion_tokens", -2), ("completion_tokens", 1.5),
    ("completion_tokens", None), ("completion_tokens", 7.0),
    ("latency_ms", -1), ("latency_ms", True), ("latency_ms", "7"),
    ("latency_ms", None), ("latency_ms", float("nan")),
    ("latency_ms", float("inf")), ("latency_ms", 10 ** 400),
])
def test_invalid_completion_aborts_batch_before_scoring(suite, monkeypatch, field, value):
    import callprobe.recordings as module
    _no_network(monkeypatch)
    def unexpected(*args, **kwargs):
        raise AssertionError("scoring started before completion validation finished")
    monkeypatch.setattr(module, "score", unexpected)
    abstain = next(t for t in suite.tasks if t.category == "abstain")
    valid = RecordedCompletion(abstain.id, Completion())
    invalid = RecordedCompletion(abstain.id, Completion(**{field: value}), repeat=1)
    with pytest.raises(ValueError, match="recording 1 has invalid completion") as caught:
        score_recordings(suite, _config(repeats=2), [valid, invalid])
    assert "PRIVATE_PAYLOAD" not in str(caught.value)


@pytest.mark.parametrize("field,value", [
    ("name", None), ("name", []), ("arguments", []),
    ("arguments", "PRIVATE_PAYLOAD"), ("id", 1),
    ("raw_arguments", {}), ("parse_error", False),
])
def test_mutated_call_fields_are_rejected_as_adapter_errors(suite, field, value):
    # Call is normally validated at construction, but reassignment/model_copy
    # can bypass that boundary. Do not let a malformed object reach scoring.
    call = Call(name="get_order_status").model_copy(update={field: value})
    with pytest.raises(ValueError, match="invalid completion call") as caught:
        score_recordings(suite, _config(), [
            RecordedCompletion(suite.tasks[0].id, Completion(calls=[call])),
        ])
    assert "PRIVATE_PAYLOAD" not in str(caught.value)


@pytest.mark.parametrize("latency", [0, 12, 12.5])
def test_normalized_provider_completion_preserves_metadata(suite, latency):
    from callprobe.client import parse_completion
    abstain = next(t for t in suite.tasks if t.category == "abstain")
    completion = parse_completion({
        "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": "7", "completion_tokens": 2.0},
    }, latency)
    # Unconsumed provider metadata is opaque, never echoed or normalized.
    completion.raw["opaque"] = object()
    result = score_recordings(suite, _config(), [
        RecordedCompletion(abstain.id, completion),
    ]).results[0]
    assert result.success
    assert result.prompt_tokens == 7 and result.completion_tokens == 2
    assert result.latency_ms == latency
