from dataclasses import dataclass

from callprobe.bootstrap import bootstrap_ci


@dataclass
class _R:
    task_id: str
    success: bool


def test_deterministic_with_fixed_seed():
    results = [_R("t1", True), _R("t1", True), _R("t2", False), _R("t3", True)]
    first = bootstrap_ci(results)
    second = bootstrap_ci(results)
    assert first == second


def test_all_success_gives_point_interval_at_one():
    results = [_R(f"t{i}", True) for i in range(10)]
    lo, hi = bootstrap_ci(results)
    assert lo == hi == 1.0


def test_ci_widens_with_fewer_tasks():
    """Correlated repeats of a thin category should show more uncertainty.

    Same underlying mix of task outcomes (half succeed), but backed by
    3 distinct task ids instead of 30. Fewer ids to resample from means
    more variance across bootstrap draws.
    """
    many_tasks = [_R(f"t{i}", i % 2 == 0) for i in range(30)] * 5
    few_tasks = [_R("a", True), _R("b", True), _R("c", False)] * 5
    wide_lo, wide_hi = bootstrap_ci(few_tasks)
    tight_lo, tight_hi = bootstrap_ci(many_tasks)
    assert (wide_hi - wide_lo) >= (tight_hi - tight_lo)


def test_resamples_by_task_id_not_individual_results():
    """A task repeated many times must not dominate the resampling pool.

    If resampling worked over individual results instead of task ids, a
    task with 100 identical failing repeats would swamp a single opposite
    task and the interval would collapse toward 0. Resampling by id keeps
    both tasks equally likely to be drawn.
    """
    results = [_R("heavy", False) for _ in range(100)] + [_R("light", True)]
    lo, hi = bootstrap_ci(results)
    assert hi > 0.0  # the single successful task id still has a voice


def test_empty_results():
    assert bootstrap_ci([]) == (0.0, 0.0)


def _reference_pooled_ci(results, field='success', confidence=0.95, iterations=2000, seed=1234):
    """Prior row-pooling implementation as an independent compatibility oracle."""
    import random
    from collections import defaultdict
    groups = defaultdict(list)
    for row in results:
        groups[row.task_id].append(row)
    keys = list(groups)
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    rates = []
    for _ in range(iterations):
        pooled = []
        for _ in keys:
            pooled.extend(groups[keys[rng.randrange(len(keys))]])
        rates.append(sum(bool(getattr(row, field)) for row in pooled) / len(pooled))
    rates.sort()
    tail = (1 - confidence) / 2
    return rates[int(tail * iterations)], rates[min(int((1 - tail) * iterations), iterations - 1)]


def test_cluster_counts_preserve_exact_intervals_for_uneven_repeats_and_seeds():
    # Different cluster sizes and mixed outcomes exercise the ratio of pooled
    # counts; averaging per-task rates instead would give different intervals.
    rows = [_R('heavy', i % 3 == 0) for i in range(17)]
    rows += [_R('medium', i % 2 == 0) for i in range(6)]
    rows += [_R('single', True), _R('small', False), _R('small', True)]
    original = list(rows)
    for seed in (0, 17, 1234):
        for confidence in (0.5, 0.8, 0.95):
            settings = dict(seed=seed, confidence=confidence, iterations=100)
            assert bootstrap_ci(rows, **settings) == _reference_pooled_ci(rows, **settings)
    assert rows == original


def test_bootstrap_reads_each_observation_once_not_once_per_resample():
    class CountedResult:
        def __init__(self, task_id, value):
            self.task_id, self.value, self.reads = task_id, value, 0

        @property
        def metric(self):
            self.reads += 1
            return self.value

    rows = [CountedResult('a', True), CountedResult('a', False), CountedResult('b', True)]
    assert bootstrap_ci(rows, field='metric', iterations=100) == (0.5, 1.0)
    assert [r.reads for r in rows] == [1, 1, 1]


def test_archived_live_intervals_match_prior_pooling():
    from pathlib import Path
    from callprobe.models import Run
    root = Path(__file__).resolve().parents[1] / 'results/2026-10-02-llamacpp-validation/evidence'
    for suite in ('core', 'mail'):
        run = Run.model_validate_json((root / suite / '01-result.json').read_text())
        scored = [r for r in run.results if r.error is None]
        for field in ('success', 'success_lenient'):
            assert bootstrap_ci(scored, field) == _reference_pooled_ci(scored, field)
