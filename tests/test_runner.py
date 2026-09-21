import threading
from pathlib import Path

import pytest

from callprobe.client import Completion
from callprobe.loader import load_suite
from callprobe.models import RunConfig
from callprobe.runner import run_suite

SUITE = Path(__file__).resolve().parents[1] / "src" / "callprobe" / "suites" / "core"


@pytest.fixture(scope="module")
def suite():
    return load_suite(SUITE)


def _config(**kwargs):
    base = dict(
        model="stub",
        endpoint="http://fake",
        suite="stub",
        pads=[0],
        repeats=2,
        temperature=0.0,
        max_tokens=64,
    )
    base.update(kwargs)
    return RunConfig(**base)


class _CountingClient:
    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        with self._lock:
            self.calls += 1
        return Completion(content="no thanks", prompt_tokens=1, completion_tokens=1)


def test_result_order_is_deterministic_regardless_of_concurrency(suite):
    sequential = run_suite(suite, _CountingClient(), _config(), concurrency=1)
    concurrent = run_suite(suite, _CountingClient(), _config(), concurrency=8)
    seq_keys = [(r.task_id, r.pad, r.repeat) for r in sequential.results]
    conc_keys = [(r.task_id, r.pad, r.repeat) for r in concurrent.results]
    assert seq_keys == conc_keys


def test_result_order_matches_pad_repeat_task_nesting(suite):
    config = _config(pads=[0, 8], repeats=2)
    run = run_suite(suite, _CountingClient(), config, concurrency=4)
    expected = [
        (task.id, pad, repeat)
        for pad in config.pads
        for repeat in range(config.repeats)
        for task in suite.tasks
    ]
    actual = [(r.task_id, r.pad, r.repeat) for r in run.results]
    assert actual == expected


def test_resume_skips_already_done_combinations(suite):
    client = _CountingClient()
    first = run_suite(suite, client, _config(pads=[0], repeats=1))
    assert client.calls == len(suite.tasks)

    resumed_client = _CountingClient()
    second = run_suite(suite, resumed_client, _config(pads=[0], repeats=1), resume=first)
    assert resumed_client.calls == 0  # every combination was already in `first`
    assert len(second.results) == len(first.results)


def test_resume_only_covers_matching_combinations(suite):
    client = _CountingClient()
    partial = run_suite(suite, client, _config(pads=[0], repeats=1))

    resumed_client = _CountingClient()
    full = run_suite(suite, resumed_client, _config(pads=[0], repeats=2), resume=partial)
    # repeat=1 is new and must be computed; repeat=0 is reused.
    assert resumed_client.calls == len(suite.tasks)
    assert len(full.results) == len(suite.tasks) * 2


def test_on_progress_snapshots_are_in_canonical_order(suite):
    seen_lengths = []

    def on_progress(run):
        seen_lengths.append(len(run.results))

    config = _config(pads=[0], repeats=1)
    run_suite(suite, _CountingClient(), config, concurrency=4, on_progress=on_progress)
    assert seen_lengths == list(range(1, len(suite.tasks) + 1))


class _InterruptingClient:
    def __init__(self, fail_after: int):
        self.calls = 0
        self.fail_after = fail_after
        self._lock = threading.Lock()

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        with self._lock:
            self.calls += 1
            if self.calls == self.fail_after:
                raise KeyboardInterrupt()
        return Completion(content="no thanks", prompt_tokens=1, completion_tokens=1)


def test_keyboard_interrupt_returns_partial_run_instead_of_raising(suite):
    config = _config(pads=[0], repeats=1)
    client = _InterruptingClient(fail_after=5)
    run = run_suite(suite, client, config)  # must not raise
    assert run.finished_at is not None
    assert 0 < len(run.results) < len(suite.tasks)
    keys = [(r.task_id, r.pad, r.repeat) for r in run.results]
    assert keys == sorted(keys, key=lambda k: [t.id for t in suite.tasks].index(k[0]))


@pytest.mark.parametrize("change", [
    {"model": "different"}, {"endpoint": "http://other"}, {"temperature": 0.5},
    {"max_tokens": 128}, {"quantization": "q8"}, {"server_version": "new"},
])
def test_resume_rejects_changed_experiment_before_requests(suite, change):
    first = run_suite(suite, _CountingClient(), _config())
    client = _CountingClient()
    with pytest.raises(ValueError, match="incompatible resume"):
        run_suite(suite, client, _config(**change), resume=first)
    assert client.calls == 0


@pytest.mark.parametrize("field,value", [
    ("suite_hash", "changed"), ("suite_hash", None),
    ("scoring_version", None), ("scoring_version", 1), ("task_ids", None),
])
def test_resume_rejects_changed_or_unknown_provenance(suite, field, value):
    first = run_suite(suite, _CountingClient(), _config())
    setattr(first.config, field, value)
    client = _CountingClient()
    with pytest.raises(ValueError, match="incompatible resume"):
        run_suite(suite, client, _config(), resume=first)
    assert client.calls == 0


def test_resume_retries_errors_and_preserves_start(suite):
    first = run_suite(suite, _CountingClient(), _config())
    first.started_at = "original start"
    first.results[0].error = "timeout"
    client = _CountingClient()
    resumed = run_suite(suite, client, _config(), resume=first)
    assert client.calls == 1
    assert resumed.results[0].error is None
    assert resumed.started_at == "original start"


def test_resume_rejects_duplicate_results(suite):
    first = run_suite(suite, _CountingClient(), _config())
    first.results.append(first.results[0])
    with pytest.raises(ValueError, match="duplicate"):
        run_suite(suite, _CountingClient(), _config(), resume=first)
