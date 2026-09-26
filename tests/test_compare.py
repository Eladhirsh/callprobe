from callprobe.compare import category_deltas, flipped_tasks, render_compare
from callprobe.models import Run, RunConfig, TaskResult


def _config(model="m", suite_hash=None):
    return RunConfig(
        model=model,
        endpoint="http://fake",
        suite="stub",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=512,
        suite_hash=suite_hash,
    )


def _result(task_id, category, pad, success, **kwargs):
    base = dict(
        task_id=task_id,
        category=category,
        model="m",
        pad=pad,
        repeat=0,
        selection_ok=success,
        schema_ok=success,
        args_ok=success,
        success=success,
    )
    base.update(kwargs)
    return TaskResult(**base)


def test_category_deltas():
    a = Run(
        config=_config(),
        started_at="now",
        results=[
            _result("t1", "select", 0, True),
            _result("t2", "select", 0, False),
        ],
    )
    b = Run(
        config=_config(),
        started_at="now",
        results=[
            _result("t1", "select", 0, True),
            _result("t2", "select", 0, True),
        ],
    )
    deltas = category_deltas(a, b)
    assert deltas["select"]["success_a"] == 0.5
    assert deltas["select"]["success_b"] == 1.0
    assert deltas["select"]["success_delta"] == 0.5


def test_flipped_tasks_aggregate_across_pads_and_repeats():
    # t1 passes every instance in a, fails one instance in b -> pass_to_fail.
    # t2 fails every instance in a, passes every instance in b -> fail_to_pass.
    a = Run(
        config=_config(),
        started_at="now",
        results=[
            _result("t1", "select", 0, True),
            _result("t1", "select", 8, True),
            _result("t2", "select", 0, False),
        ],
    )
    b = Run(
        config=_config(),
        started_at="now",
        results=[
            _result("t1", "select", 0, True),
            _result("t1", "select", 8, False),
            _result("t2", "select", 0, True),
        ],
    )
    pass_to_fail, fail_to_pass = flipped_tasks(a, b)
    assert pass_to_fail == ["t1"]
    assert fail_to_pass == ["t2"]


def test_errored_results_excluded_from_verdicts():
    a = Run(
        config=_config(),
        started_at="now",
        results=[_result("t1", "select", 0, False, error="timeout")],
    )
    b = Run(
        config=_config(),
        started_at="now",
        results=[_result("t1", "select", 0, True)],
    )
    pass_to_fail, fail_to_pass = flipped_tasks(a, b)
    # t1 has no scored instance in a, so it cannot be compared at all.
    assert pass_to_fail == []
    assert fail_to_pass == []


def test_render_compare_lists_flips_and_deltas():
    a = Run(
        config=_config(model="old"),
        started_at="now",
        results=[_result("t1", "select", 0, True)],
    )
    b = Run(
        config=_config(model="new"),
        started_at="now",
        results=[_result("t1", "select", 0, False)],
    )
    text = render_compare(a, b)
    assert "old  ->  new" in text
    assert "t1" in text
    assert "pass -> fail (1):" in text
    assert "fail -> pass (0):" in text


def test_comparison_reports_request_errors_without_inventing_rate_delta():
    a = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, False, error="timeout")])
    b = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, True)])
    text = render_compare(a, b)
    assert "scored observations: 0 -> 1" in text
    assert "request errors: 1 -> 0" in text
    row = next(line for line in text.splitlines() if line.startswith("select"))
    assert row.split()[1:] == ["n/a", "100.0%", "n/a", "n/a", "0.0%", "n/a"]
    assert "+100.0%" not in row


def test_category_absent_from_candidate_is_not_reported_as_zero_percent():
    a = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, True)])
    b = Run(config=_config(), started_at="now", results=[])
    row = next(line for line in render_compare(a, b).splitlines() if line.startswith("select"))
    assert row.split()[2:4] == ["n/a", "n/a"]
