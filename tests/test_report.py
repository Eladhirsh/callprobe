from callprobe.models import Run, RunConfig, TaskResult
from callprobe.report import failure_digest, summarize


def _config():
    return RunConfig(
        model="stub",
        endpoint="http://fake",
        suite="stub",
        pads=[0],
        repeats=1,
        temperature=0.0,
        max_tokens=512,
    )


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
