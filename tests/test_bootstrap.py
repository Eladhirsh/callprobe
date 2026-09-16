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
