"""Tests for the offline JUnit exporter."""

from __future__ import annotations

import copy
import math
import re
from xml.etree import ElementTree as ET

import pytest

from callprobe.junit import render_junit
from callprobe.models import Run, RunConfig, TaskResult


# ---- helpers --------------------------------------------------------------


def _config(**overrides):
    base = dict(
        model="demo-model",
        endpoint="http://localhost:11434/v1",
        suite="demo",
        pads=[0, 8],
        repeats=2,
        temperature=0.0,
        max_tokens=1024,
        suite_name="demo-suite",
        suite_hash="hashA",
        scoring_version=3,
        task_ids=["t1", "t2"],
    )
    base.update(overrides)
    return RunConfig(**base)


def _result(task_id="t1", pad=0, repeat=0, **overrides):
    base = dict(
        task_id=task_id,
        category="select",
        model="demo-model",
        pad=pad,
        repeat=repeat,
        selection_ok=True,
        schema_ok=True,
        args_ok=True,
        success=True,
        latency_ms=100.0,
    )
    base.update(overrides)
    return TaskResult(**base)


def _run(config=None, results=None):
    return Run(
        config=config or _config(),
        started_at="2026-01-01T00:00:00Z",
        results=list(results or []),
    )


def _full_coverage_results(cfg):
    rs = []
    for tid in cfg.task_ids or []:
        for pad in cfg.pads:
            for rep in range(cfg.repeats):
                rs.append(_result(task_id=tid, pad=pad, repeat=rep))
    return rs


def _parse(xml: str) -> ET.Element:
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    return root


def _suite(xml: str) -> ET.Element:
    root = _parse(xml)
    suites = list(root.findall("testsuite"))
    assert len(suites) == 1
    return suites[0]


def _cases(suite: ET.Element) -> list[ET.Element]:
    return list(suite.findall("testcase"))


def _properties(suite: ET.Element) -> dict[str, str]:
    props = suite.find("properties")
    assert props is not None
    return {p.attrib["name"]: p.attrib["value"] for p in props.findall("property")}


# ---- happy paths ----------------------------------------------------------


def test_full_coverage_all_pass():
    cfg = _config()
    run = _run(cfg, _full_coverage_results(cfg))
    xml = render_junit(run)
    suite = _suite(xml)
    assert suite.attrib["tests"] == str(len(cfg.task_ids) * len(cfg.pads) * cfg.repeats)
    assert suite.attrib["failures"] == "0"
    assert suite.attrib["errors"] == "0"
    assert suite.attrib["skipped"] == "0"
    for case in _cases(suite):
        assert list(case) == []  # pass => no child
    props = _properties(suite)
    assert props["model"] == "demo-model"
    assert props["suite_hash"] == "hashA"
    assert props["scoring_version"] == "3"
    assert props["planned_coverage"] == "8"
    assert props["recorded_coverage"] == "8"
    assert props["targeted_scope"] == "false"


def test_mixed_outcomes_counters_and_types():
    cfg = _config()
    results = _full_coverage_results(cfg)
    # pick 4 unique observations and give them distinct outcomes
    results[0] = _result(task_id="t1", pad=0, repeat=0,
                         selection_ok=False, schema_ok=False, args_ok=False, success=False)
    results[1] = _result(task_id="t1", pad=0, repeat=1,
                         selection_ok=True, schema_ok=True, args_ok=True, success=True,
                         # per spec, error wins over flags
                         error="SECRET_ENDPOINT_LEAK: boom")
    results[2] = _result(task_id="t1", pad=8, repeat=0,
                         selection_ok=True, schema_ok=False, args_ok=True, success=False,
                         truncated=True)
    results[3] = _result(task_id="t1", pad=8, repeat=1,
                         selection_ok=True, schema_ok=False, args_ok=True, success=False)
    run = _run(cfg, results)
    xml = render_junit(run)
    suite = _suite(xml)
    # 8 observations, no synthetic cases (coverage complete, not targeted)
    assert suite.attrib["tests"] == "8"
    assert suite.attrib["errors"] == "1"  # the request error
    # One strict-fail, one truncated, one schema-only fail => 3 failures
    assert suite.attrib["failures"] == "3"
    assert suite.attrib["skipped"] == "0"


def test_duration_sum_and_bad_latencies():
    cfg = _config(task_ids=["t1"], pads=[0], repeats=4)
    results = [
        _result(task_id="t1", pad=0, repeat=0, latency_ms=1500.0),
        _result(task_id="t1", pad=0, repeat=1, latency_ms=float("nan")),
        _result(task_id="t1", pad=0, repeat=2, latency_ms=float("-inf")),
        _result(task_id="t1", pad=0, repeat=3, latency_ms=-500.0),
    ]
    run = _run(cfg, results)
    xml = render_junit(run)
    suite = _suite(xml)
    cases = _cases(suite)
    # ordering preserved; latency 1500ms = 1.5s, rest clamped to 0
    times = [float(c.attrib["time"]) for c in cases]
    assert times == pytest.approx([1.5, 0.0, 0.0, 0.0])
    for t in times:
        assert math.isfinite(t) and t >= 0
    assert float(suite.attrib["time"]) == pytest.approx(1.5)


# ---- XML safety / no leak -------------------------------------------------


def test_xml_hostile_and_illegal_characters_are_sanitized_but_unicode_preserved():
    cfg = _config(
        task_ids=["id\x01with\x08ctl☃snowman"],
        pads=[0],
        repeats=1,
        suite_name="suite\x00with<&>",
        suite_hash="hash\x1fok",
    )
    results = [
        _result(
            task_id="id\x01with\x08ctl☃snowman",
            category="select",
            pad=0,
            repeat=0,
            selection_ok=False,
            schema_ok=False,
            args_ok=False,
            success=False,
        )
    ]
    run = _run(cfg, results)
    xml = render_junit(run)
    # Illegal controls stripped
    assert "\x00" not in xml
    assert "\x01" not in xml
    assert "\x08" not in xml
    assert "\x1f" not in xml
    # Unicode preserved
    assert "☃" in xml
    # Must still parse
    suite = _suite(xml)
    cases = _cases(suite)
    assert cases[0].attrib["name"].startswith("idwithctl☃snowman[pad=0,repeat=0]")
    assert "<" not in cases[0].attrib["classname"]


def test_no_secret_leak_in_output():
    cfg = _config(
        endpoint="https://leak-endpoint.example.internal/secrets",
        notes="internal note with api_key=sk-ABC123",
    )
    results = _full_coverage_results(cfg)
    results[0] = _result(
        task_id="t1", pad=0, repeat=0,
        selection_ok=False, schema_ok=False, args_ok=False, success=False,
        error="HTTPError: Authorization: Bearer sk-ABC123",
        response_text="SECRET_RESPONSE_TOKEN=xyz",
        failures=["wire-level failure: Bearer sk-ABC123"],
        calls=[],
    )
    run = _run(cfg, results)
    xml = render_junit(run)
    assert "leak-endpoint.example.internal" not in xml
    assert "sk-ABC123" not in xml
    assert "SECRET_RESPONSE_TOKEN" not in xml
    assert "api_key" not in xml
    assert "Bearer" not in xml
    assert "wire-level failure" not in xml


# ---- coverage synthetic cases --------------------------------------------


def test_partial_run_emits_synthetic_error():
    cfg = _config()  # plans 8 observations
    results = _full_coverage_results(cfg)[:5]
    xml = render_junit(_run(cfg, results))
    suite = _suite(xml)
    cases = _cases(suite)
    assert len(cases) == 6  # 5 observations + 1 synthetic
    synthetic = cases[-1]
    assert synthetic.attrib["name"] == "coverage.partial"
    err = synthetic.find("error")
    assert err is not None
    assert err.attrib["type"] == "coverage_partial"
    assert "3 of 8" in err.attrib["message"]
    assert suite.attrib["errors"] == "1"
    # Property reflects reality
    props = _properties(suite)
    assert props["recorded_coverage"] == "5"
    assert props["planned_coverage"] == "8"


def test_empty_run_known_plan_is_not_green():
    cfg = _config()
    xml = render_junit(_run(cfg, []))
    suite = _suite(xml)
    cases = _cases(suite)
    assert len(cases) == 1
    assert cases[0].attrib["name"] == "coverage.partial"
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["failures"] == "0"


def test_empty_run_empty_plan_is_still_not_green():
    cfg = _config(task_ids=[])
    xml = render_junit(_run(cfg, []))
    suite = _suite(xml)
    cases = _cases(suite)
    assert len(cases) == 1
    assert cases[0].attrib["name"] == "coverage.empty"
    assert suite.attrib["errors"] == "1"


def test_legacy_missing_task_ids_synthetic_error_but_observations_exported():
    cfg = _config(task_ids=None)
    results = [
        _result(task_id="t1", pad=0, repeat=0),
        _result(task_id="t999", pad=8, repeat=1,
                selection_ok=False, schema_ok=False, args_ok=False, success=False),
    ]
    xml = render_junit(_run(cfg, results))
    suite = _suite(xml)
    cases = _cases(suite)
    # 2 observations + 1 synthetic coverage error
    assert len(cases) == 3
    assert cases[-1].attrib["name"] == "coverage.unknown"
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["failures"] == "1"
    props = _properties(suite)
    assert props["planned_coverage"] == "unknown"
    # legacy mode: unique/bounds/model still validated
    bad_dup = _run(cfg, [_result(), _result()])
    with pytest.raises(ValueError):
        render_junit(bad_dup)


# ---- targeted scope -------------------------------------------------------


def test_targeted_matching_plan_has_skipped_notice_and_no_missing_count():
    cfg = _config(task_ids=["t1", "t2", "t3"], selected_task_ids=["t1", "t3"])
    results = []
    for tid in ["t1", "t3"]:
        for pad in cfg.pads:
            for rep in range(cfg.repeats):
                results.append(_result(task_id=tid, pad=pad, repeat=rep))
    xml = render_junit(_run(cfg, results))
    suite = _suite(xml)
    cases = _cases(suite)
    # 8 observations + 1 skipped synthetic (no partial)
    assert len(cases) == 9
    assert suite.attrib["skipped"] == "1"
    assert suite.attrib["errors"] == "0"
    skipped_case = next(c for c in cases if c.attrib["name"] == "coverage.targeted_debug_notice")
    s = skipped_case.find("skipped")
    assert s is not None
    assert "targeted debug" in s.attrib["message"].lower()
    assert "not a full benchmark" in s.attrib["message"].lower()
    # Planned coverage counts only the selected tasks
    props = _properties(suite)
    assert props["planned_coverage"] == "8"
    assert props["targeted_scope"] == "true"


def test_targeted_observation_outside_selected_raises():
    cfg = _config(task_ids=["t1", "t2", "t3"], selected_task_ids=["t1"])
    # observation on t2 is "mismatched" — out of targeted plan
    results = [_result(task_id="t2", pad=0, repeat=0)]
    with pytest.raises(ValueError):
        render_junit(_run(cfg, results))


def test_targeted_subset_not_in_task_ids_raises():
    with pytest.raises(ValueError):
        render_junit(_run(_config(task_ids=["t1"], selected_task_ids=["tX"])))


# ---- validation errors ----------------------------------------------------


def test_duplicate_observation_raises():
    cfg = _config()
    results = [_result(), _result()]  # same (t1, 0, 0)
    with pytest.raises(ValueError):
        render_junit(_run(cfg, results))


def test_out_of_plan_pad_raises():
    cfg = _config()
    results = [_result(pad=99)]
    with pytest.raises(ValueError):
        render_junit(_run(cfg, results))


def test_out_of_plan_repeat_raises():
    cfg = _config(repeats=1)
    results = [_result(repeat=5)]
    with pytest.raises(ValueError):
        render_junit(_run(cfg, results))


def test_out_of_plan_task_id_raises():
    cfg = _config()
    results = [_result(task_id="nope")]
    with pytest.raises(ValueError):
        render_junit(_run(cfg, results))


def test_wrong_model_raises():
    cfg = _config(model="demo-model")
    results = [_result(task_id="t1", pad=0, repeat=0)]
    # mutate the observation's model to disagree with config
    r = results[0].model_copy(update={"model": "other-model"})
    with pytest.raises(ValueError):
        render_junit(_run(cfg, [r]))


def test_invalid_pads_raises():
    with pytest.raises(ValueError):
        render_junit(_run(_config(pads=[-1])))
    with pytest.raises(ValueError):
        render_junit(_run(_config(pads=[0, 0])))


def test_invalid_repeats_raises():
    with pytest.raises(ValueError):
        render_junit(_run(_config(repeats=0)))


def test_invalid_selected_ids_raise():
    with pytest.raises(ValueError):
        render_junit(_run(_config(selected_task_ids=[])))
    with pytest.raises(ValueError):
        render_junit(_run(_config(selected_task_ids=["t1", "t1"])))


# ---- scalability ----------------------------------------------------------


def test_huge_repeat_count_without_allocation():
    big = 10**9
    cfg = _config(task_ids=["t1"], pads=[0], repeats=big)
    results = [_result(task_id="t1", pad=0, repeat=0)]
    xml = render_junit(_run(cfg, results))
    suite = _suite(xml)
    # one real observation + one synthetic partial-coverage error
    assert len(_cases(suite)) == 2
    props = _properties(suite)
    assert props["planned_coverage"] == str(big)
    assert props["recorded_coverage"] == "1"
    assert suite.attrib["errors"] == "1"


# ---- metadata & immutability ----------------------------------------------


def test_scoring_version_recorded_as_is_without_rewrite():
    cfg = _config(scoring_version=1)
    results = _full_coverage_results(cfg)
    xml = render_junit(_run(cfg, results))
    props = _properties(_suite(xml))
    assert props["scoring_version"] == "1"


def test_render_does_not_mutate_run():
    cfg = _config()
    run = _run(cfg, _full_coverage_results(cfg))
    before = run.model_dump()
    _ = render_junit(run)
    _ = render_junit(run)
    assert run.model_dump() == before


def test_render_is_deterministic():
    cfg = _config()
    run = _run(cfg, _full_coverage_results(cfg))
    assert render_junit(run) == render_junit(copy.deepcopy(run))


def test_no_rescoring_passes_are_passes_even_if_flags_disagree_elsewhere():
    """A record that scoring already marked success stays a pass; a record
    with success=False stays a failure, regardless of what sub-flags claim.
    """
    cfg = _config(task_ids=["t1"], pads=[0], repeats=2)
    results = [
        # success recorded True; emits a pass
        _result(task_id="t1", pad=0, repeat=0,
                selection_ok=False, schema_ok=False, args_ok=False, success=True),
        # success recorded False even though sub-flags look fine; still a failure
        _result(task_id="t1", pad=0, repeat=1,
                selection_ok=True, schema_ok=True, args_ok=True, success=False),
    ]
    xml = render_junit(_run(cfg, results))
    suite = _suite(xml)
    cases = _cases(suite)
    assert list(cases[0]) == []
    assert cases[1].find("failure") is not None
    assert suite.attrib["failures"] == "1"


def test_request_error_overrides_success_flags():
    cfg = _config(task_ids=["t1"], pads=[0], repeats=1)
    r = _result(
        task_id="t1", pad=0, repeat=0,
        selection_ok=True, schema_ok=True, args_ok=True, success=True,
        error="whatever",
    )
    xml = render_junit(_run(cfg, [r]))
    suite = _suite(xml)
    cases = _cases(suite)
    err = cases[0].find("error")
    assert err is not None
    assert err.attrib["type"] == "request_error"
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["failures"] == "0"


def test_output_parses_as_well_formed_xml_with_declaration():
    cfg = _config()
    xml = render_junit(_run(cfg, _full_coverage_results(cfg)))
    assert xml.startswith("<?xml")
    ET.fromstring(xml)


def test_case_name_includes_task_id_pad_and_repeat():
    cfg = _config(task_ids=["t1"], pads=[0], repeats=1)
    xml = render_junit(_run(cfg, [_result(task_id="t1", pad=0, repeat=0)]))
    suite = _suite(xml)
    case = _cases(suite)[0]
    assert case.attrib["name"] == "t1[pad=0,repeat=0]"
    assert case.attrib["classname"] == "select"


def test_missing_suite_label_does_not_export_local_path():
    cfg = _config(suite_name=None, suite="/private/SECRET_PATH/my-suite")
    xml = render_junit(_run(cfg, _full_coverage_results(cfg)))
    assert "SECRET_PATH" not in xml
    assert _suite(xml).attrib["name"] == "callprobe"


def test_empty_padding_plan_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        render_junit(_run(_config(pads=[])))
