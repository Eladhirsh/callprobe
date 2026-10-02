from callprobe.models import Run, RunConfig, TaskResult
from callprobe.report import failure_digest, render_markdown, render_text, summarize


def _config(**kwargs):
    base = dict(
        model="stub",
        endpoint="http://fake",
        suite="stub",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=512,
    )
    base.update(kwargs)
    return RunConfig(**base)


def _result(**kwargs):
    base = dict(
        task_id="t1",
        category="select",
        model="stub",
        pad=0,
        repeat=0,
        selection_ok=True,
        schema_ok=True,
        args_ok=True,
        success=True,
    )
    base.update(kwargs)
    return TaskResult(**base)


def test_errors_excluded_from_success_rate():
    results = [
        _result(success=True, selection_ok=True, schema_ok=True, args_ok=True),
        _result(
            success=False,
            selection_ok=False,
            schema_ok=False,
            args_ok=False,
            error="TimeoutException: timed out",
        ),
    ]
    run = Run(config=_config(), started_at="now", results=results)
    s = summarize(run)
    assert s["n"] == 1  # the errored request does not count as a scored task
    assert s["total_requests"] == 2
    assert s["errors"] == 1
    assert s["overall"]["success"] == 1.0  # not dragged down by the error


def test_errors_excluded_from_category_and_pad_rates():
    results = [
        _result(category="args", pad=8, success=True),
        _result(category="args", pad=8, success=False, error="HTTPStatusError: 500"),
    ]
    run = Run(config=_config(), started_at="now", results=results)
    s = summarize(run)
    assert s["by_category"]["args"]["success"] == 1.0
    assert s["by_category"]["args"]["n"] == 1
    assert s["by_pad"][8]["success"] == 1.0
    assert s["by_pad"][8]["n"] == 1


def test_error_rate_warning_threshold():
    results = [_result(success=True)] * 98 + [
        _result(success=False, error="x") for _ in range(2)
    ]
    run = Run(config=_config(), started_at="now", results=results)
    s = summarize(run)
    assert s["error_rate"] == 0.02  # exactly at the threshold, not over it


def test_failure_digest_skips_errored_results():
    results = [
        _result(success=False, failures=["request failed: boom"], error="boom"),
    ]
    run = Run(config=_config(), started_at="now", results=results)
    digest = failure_digest(run)
    assert "none" in digest


def test_markdown_shows_suite_version_when_runs_agree():
    config = _config(suite_name="core", suite_version=1)
    run = Run(config=config, started_at="now", results=[_result()])
    assert "suite: core v1" in render_markdown([run])


def test_markdown_omits_suite_line_when_unknown():
    run = Run(config=_config(), started_at="now", results=[_result()])
    assert "suite:" not in render_markdown([run])


def test_summarize_scope_is_full_by_default():
    config = _config(task_ids=["t1", "t2", "t3"])
    run = Run(config=config, started_at="now", results=[_result()])
    scope = summarize(run)["scope"]
    assert scope == {"targeted": False, "selected_task_count": 3, "total_task_count": 3}


def test_summarize_scope_reports_targeted_selection():
    config = _config(task_ids=["t1", "t2", "t3"], selected_task_ids=["t1"])
    run = Run(config=config, started_at="now", results=[_result()])
    scope = summarize(run)["scope"]
    assert scope == {"targeted": True, "selected_task_count": 1, "total_task_count": 3}


def test_render_text_labels_targeted_debug_run():
    config = _config(task_ids=["t1", "t2", "t3"], selected_task_ids=["t1"])
    run = Run(config=config, started_at="now", results=[_result()])
    text = render_text(run)
    assert "TARGETED DEBUG RUN" in text
    assert "1 of 3" in text


def test_render_text_omits_targeted_label_for_full_run():
    config = _config(task_ids=["t1", "t2", "t3"])
    run = Run(config=config, started_at="now", results=[_result()])
    assert "TARGETED DEBUG RUN" not in render_text(run)


def test_render_markdown_labels_targeted_debug_run():
    config = _config(task_ids=["t1", "t2", "t3"], selected_task_ids=["t1", "t2"])
    run = Run(config=config, started_at="now", results=[_result()])
    markdown = render_markdown([run])
    assert "targeted debug run" in markdown
    assert "2/3 tasks" in markdown


def test_render_markdown_omits_targeted_label_for_full_run():
    config = _config(task_ids=["t1", "t2", "t3"])
    run = Run(config=config, started_at="now", results=[_result()])
    assert "targeted debug run" not in render_markdown([run])


def test_legacy_run_json_without_selected_task_ids_field_still_loads():
    import json

    from callprobe.models import Run as RunModel

    legacy = {
        "config": {
            "model": "stub", "endpoint": "http://fake", "suite": "stub",
            "pads": [0], "repeats": 1, "temperature": 0.0, "max_tokens": 64,
            "task_ids": ["t1"],
        },
        "started_at": "now",
        "results": [
            {"task_id": "t1", "category": "select", "model": "stub", "pad": 0,
             "repeat": 0, "selection_ok": True, "schema_ok": True, "args_ok": True,
             "success": True},
        ],
    }
    run = RunModel.model_validate_json(json.dumps(legacy))
    assert run.config.selected_task_ids is None
    assert summarize(run)["scope"]["targeted"] is False


def test_leaderboard_labels_actual_maximum_padding_without_falling_back():
    runs = [
        Run(config=_config(pads=[0]), started_at="now", results=[_result()]),
        Run(config=_config(pads=[0, 24, 32]), started_at="now",
            results=[_result(pad=24), _result(pad=32, success=False)]),
        Run(config=_config(pads=[0, 8]), started_at="now",
            results=[_result(), _result(pad=8, success=False, error="timeout")]),
    ]
    text = render_markdown(runs)
    assert "success @ +24 tools" not in text
    assert "100.0% (+0 tools)" in text
    assert "0.0% (+32 tools)" in text
    assert "unscored (+8 tools)" in text


def _row(text):
    return next(l for l in text.splitlines() if l.startswith("| stub"))


def _cells(text):
    return [c.strip() for c in _row(text).strip("|").split("|")]


def test_leaderboard_full_run_coverage_is_complete():
    config = _config(task_ids=["t1", "t2"], pads=[0, 8], repeats=2)
    results = [_result(task_id=t, pad=p, repeat=r)
               for t in ("t1", "t2") for p in (0, 8) for r in (0, 1)]
    cells = _cells(render_markdown([Run(config=config, started_at="now", results=results)]))
    assert cells[-3:] == ["8/8/8", "0", "0"]


def test_leaderboard_partial_run_is_flagged_and_metrics_unchanged():
    config = _config(task_ids=["t1", "t2"], pads=[0, 8], repeats=1)
    run = Run(config=config, started_at="now", results=[_result(), _result(task_id="t2")])
    text = render_markdown([run])
    assert "2/2/4 INCOMPLETE (2 missing)" in _row(text)
    assert "100.0%" in _row(text)  # existing metric values preserved
    assert "request errors are excluded" in text and "truncated" in text


def test_leaderboard_counts_errors_and_truncations_without_hiding_rows():
    config = _config(task_ids=["t1", "t2", "t3"])
    results = [
        _result(),
        _result(task_id="t2", success=False, truncated=True),
        _result(task_id="t3", success=False, error="timeout"),
    ]
    run = Run(config=config, started_at="now", results=results)
    cells = _cells(render_markdown([run]))
    assert cells[-3:] == ["2/3/3", "1", "1"]
    assert cells[1] == "50.0%"  # truncation is a failure; error is not scored
    assert len(run.results) == 3


def test_leaderboard_duplicate_and_unexpected_rows_not_complete():
    config = _config(task_ids=["t1", "t2"])
    results = [_result(), _result(), _result(task_id="zz")]
    cell = _cells(render_markdown([Run(config=config, started_at="now", results=results)]))[-3]
    assert cell == "3/3/2 INCOMPLETE (1 missing, 1 duplicate, 1 unexpected)"


def test_leaderboard_legacy_run_without_task_ids_has_unknown_planned():
    run = Run(config=_config(), started_at="now", results=[_result()])
    cell = _cells(render_markdown([run]))[-3]
    assert cell == "1/1/? (planned unknown)"


def test_coverage_does_not_materialize_large_planned_sweeps():
    config = _config(task_ids=["t1"], repeats=10**12)
    text = render_markdown([Run(config=config, started_at="now", results=[_result()])])
    assert "1/1/1000000000000 INCOMPLETE (999999999999 missing)" in text


def test_empty_string_error_is_treated_as_request_error_in_summary():
    results = [
        _result(success=True),
        _result(success=True, error=""),
    ]
    run = Run(config=_config(), started_at="now", results=results)
    s = summarize(run)
    # the empty-string error must not inflate the scored denominator or
    # mask itself as a success in the overall rate
    assert s["n"] == 1
    assert s["errors"] == 1
    assert s["total_requests"] == 2
    assert s["overall"]["success"] == 1.0


def test_empty_string_error_is_skipped_by_failure_digest():
    # an errored record never carries diagnostic weight for the failure
    # digest, even if its error string is empty
    results = [
        _result(success=False, failures=["request failed: "], error=""),
    ]
    run = Run(config=_config(), started_at="now", results=results)
    assert "none" in failure_digest(run)


def test_leaderboard_preserves_table_structure_for_external_labels():
    run = Run(config=_config(model="model|<img>\n# title", suite_name="suite\n<script>",
                             suite_version=1), started_at="now", results=[_result()])
    text = render_markdown([run])
    assert "<img>" not in text and "<script>" not in text
    assert "model\\|&lt;img&gt; \\# title" in text
    assert "suite: suite &lt;script&gt; v1" in text
    assert "\n# title" not in text
