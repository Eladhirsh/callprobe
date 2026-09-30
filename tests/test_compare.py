from callprobe.compare import category_deltas, flipped_tasks, render_compare, render_compare_markdown
from callprobe.gates import evaluate_gate, load_policy
from callprobe.models import Run, RunConfig, TaskResult


def _config(model="m", suite_hash=None, **kwargs):
    return RunConfig(
        model=model,
        endpoint="http://fake",
        suite="stub",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=512,
        suite_hash=suite_hash,
        **kwargs,
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


# ------------------------------------------------------------ markdown


def test_markdown_includes_model_labels_counts_and_no_gate_requested():
    a = Run(config=_config(model="old-model"), started_at="now",
            results=[_result("t1", "select", 0, True)])
    b = Run(config=_config(model="new-model"), started_at="now",
            results=[_result("t1", "select", 0, False)])
    text = render_compare_markdown(a, b)
    assert "old-model" in text
    assert "new-model" in text
    assert "Scored observations: 1 -> 1" in text
    assert "Request errors: 0 -> 0" in text
    assert "**CI gate:** not requested" in text


def test_markdown_category_percentages_and_n_a_when_unscored():
    a = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, False, error="timeout")])
    b = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, True)])
    text = render_compare_markdown(a, b)
    row = next(line for line in text.splitlines() if line.startswith("| select"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells == ["select", "n/a", "100.0%", "n/a", "n/a", "0.0%", "n/a"]
    assert "Request errors: 1 -> 0" in text


def test_markdown_reports_task_flips():
    a = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, True), _result("t2", "select", 0, False)])
    b = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, False), _result("t2", "select", 0, True)])
    text = render_compare_markdown(a, b)
    assert "**Pass -> fail (1):**" in text
    assert "- t1" in text
    assert "**Fail -> pass (1):**" in text
    assert "- t2" in text


def test_markdown_warns_on_targeted_debug_run():
    a = Run(config=_config(selected_task_ids=["t1"]), started_at="now",
            results=[_result("t1", "select", 0, True)])
    b = Run(config=_config(), started_at="now",
            results=[_result("t1", "select", 0, True)])
    text = render_compare_markdown(a, b)
    assert "targeted debug run(s), not full benchmark coverage" in text


def test_markdown_warns_on_mismatched_and_missing_suite_hash():
    a = Run(config=_config(suite_hash="abc"), started_at="now",
            results=[_result("t1", "select", 0, True)])
    b = Run(config=_config(suite_hash="def"), started_at="now",
            results=[_result("t1", "select", 0, True)])
    text = render_compare_markdown(a, b)
    assert "suite hashes differ or are missing" in text
    assert "a=abc" in text
    assert "b=def" in text

    c = Run(config=_config(suite_hash=None), started_at="now",
            results=[_result("t1", "select", 0, True)])
    missing_text = render_compare_markdown(a, c)
    assert "b=missing" in missing_text


def test_markdown_warns_on_mismatched_scoring_version():
    a = Run(config=_config(scoring_version=1), started_at="now",
            results=[_result("t1", "select", 0, True)])
    b = Run(config=_config(scoring_version=2), started_at="now",
            results=[_result("t1", "select", 0, True)])
    text = render_compare_markdown(a, b)
    assert "scoring versions differ" in text
    assert "a=1" in text
    assert "b=2" in text


def _gate_config(model, task_ids, scoring_version=1, suite_hash="h"):
    return _config(
        model=model, task_ids=task_ids,
        scoring_version=scoring_version, suite_hash=suite_hash,
    )


def test_markdown_real_gate_failure_lists_reasons_and_regressions():
    a = Run(
        config=_gate_config("m", ["t1"]), started_at="now",
        results=[_result("t1", "select", 0, True)],
    )
    b = Run(
        config=_gate_config("m", ["t1"]), started_at="now",
        results=[_result("t1", "select", 0, False)],
    )
    gate = evaluate_gate(a, b, load_policy(None))
    text = render_compare_markdown(a, b, gate)
    assert "**CI gate:** FAIL" in text
    assert "Gate failure reasons:" in text
    assert "previously passing case" in text and "regressed" in text
    assert "Regressed observations:" in text
    assert "- t1 pad=0 repeat=0" in text


def test_markdown_gate_pass_is_distinguishable_from_no_gate():
    a = Run(
        config=_gate_config("m", ["t1"]), started_at="now",
        results=[_result("t1", "select", 0, True)],
    )
    b = Run(
        config=_gate_config("m", ["t1"]), started_at="now",
        results=[_result("t1", "select", 0, True)],
    )
    gate = evaluate_gate(a, b, load_policy(None))
    text = render_compare_markdown(a, b, gate)
    assert "**CI gate:** PASS" in text
    assert "Gate failure reasons:" not in text
    assert "not requested" not in text


def test_markdown_adversarial_names_are_escaped():
    evil_model = "m|`*_[link](http://evil)\n# H1"
    evil_task = "t|1\n](x)"
    a = Run(config=_config(model=evil_model), started_at="now",
            results=[_result(evil_task, "select", 0, True)])
    b = Run(config=_config(model=evil_model), started_at="now",
            results=[_result(evil_task, "select", 0, False)])
    text = render_compare_markdown(a, b)
    assert "\n# H1" not in text
    assert "](http://evil)" not in text
    for raw_line in text.splitlines():
        # every literal pipe in a table row must be a column separator, not
        # smuggled-in user content; there are exactly 8 in the 7-column table
        if raw_line.startswith("| select"):
            assert raw_line.count("|") == 8
    assert "\\|" in text
    assert "\\[" in text
    assert "\\]" in text
    assert "\\`" in text
    assert "\\*" in text
    assert "\\_" in text


def test_markdown_warns_when_both_scoring_versions_are_missing():
    run = Run(config=_config(scoring_version=None), started_at="now", results=[])
    assert "scoring versions differ or are missing" in render_compare_markdown(run, run)


def test_markdown_does_not_wrap_escaped_metadata_in_code_spans():
    run = Run(config=_config(model="`<img src=x> & value"), started_at="now", results=[])
    text = render_compare_markdown(run, run)
    assert "**Baseline model:** " + chr(92) + "`" in text
    assert "<img" not in text
    assert "&lt;img" in text


def test_markdown_records_generation_conditions_without_endpoint_credentials():
    a = Run(config=_config().model_copy(update={"temperature": 0.0, "max_tokens": 1024, "pads": [0],
                          "endpoint": "https://private-secret@example.test/v1"}),
            started_at="now", results=[])
    b = Run(config=_config().model_copy(update={"temperature": 0.5, "max_tokens": 4096, "pads": [0, 8]}),
            started_at="now", results=[])
    text = render_compare_markdown(a, b)
    assert "| Temperature | 0.0 | 0.5 |" in text
    assert "| Maximum output tokens | 1024 | 4096 |" in text
    assert "| Distractor counts | 0 | 0, 8 |" in text
    assert "private-secret" not in text
