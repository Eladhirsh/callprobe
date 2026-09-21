import pytest

from callprobe import cli
from callprobe.gates import GatePolicy, evaluate_gate, load_policy
from callprobe.models import Run, RunConfig, TaskResult


def make_run(outcomes=(True, True), **overrides):
    config = RunConfig(model="m", endpoint="http://fake", suite="test", pads=[0],
                       repeats=1, temperature=0, max_tokens=64, suite_hash="same",
                       scoring_version=2, task_ids=["t1", "t2"])
    results = [TaskResult(task_id=f"t{i+1}", category="args" if i == 0 else "abstain",
                          model="m", pad=0, repeat=0, selection_ok=ok, schema_ok=ok,
                          args_ok=ok, success=ok) for i, ok in enumerate(outcomes)]
    return Run(config=config, started_at="now", results=results, **overrides)


def test_default_gate_passes_unchanged_and_fails_regression():
    assert evaluate_gate(make_run(), make_run(), GatePolicy())["passed"]
    result = evaluate_gate(make_run(), make_run((True, False)), GatePolicy())
    assert not result["passed"]
    assert result["success_delta"] == -0.5
    assert result["regressions"] == [{"task_id": "t2", "pad": 0, "repeat": 0}]


def test_detects_regressed_case_even_when_task_already_failed_elsewhere():
    a, b = make_run((True, False)), make_run((False, False))
    for run in (a, b):
        run.config.task_ids = ["t1"]
        run.config.repeats = 2
        run.results[1].task_id = "t1"
        run.results[1].repeat = 1
        run.results[1].category = "args"
    assert not evaluate_gate(a, b, GatePolicy())["passed"]


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r.results.pop(), "coverage"),
    (lambda r: r.results.append(r.results[0]), "duplicate"),
    (lambda r: setattr(r.config, "scoring_version", None), "scoring_version"),
    (lambda r: setattr(r.config, "scoring_version", 1), "scoring_version"),
    (lambda r: setattr(r.config, "suite_hash", "different"), "suite_hash"),
    (lambda r: setattr(r.config, "task_ids", None), "planned coverage"),
    (lambda r: setattr(r.results[0], "category", "select"), "categories differ"),
    (lambda r: setattr(r.results[0], "model", "other"), "result model"),
])
def test_invalid_comparisons_are_rejected(mutation, match):
    a, b = make_run(), make_run()
    mutation(b)
    with pytest.raises(ValueError, match=match):
        evaluate_gate(a, b, GatePolicy())


def test_different_complete_coverage_is_rejected():
    a, b = make_run(), make_run()
    b.config.pads = [8]
    for r in b.results:
        r.pad = 8
    with pytest.raises(ValueError, match="same tasks, pads, and repeats"):
        evaluate_gate(a, b, GatePolicy())


def test_error_limit_applies_to_both_runs_and_deltas_only_use_matched_cases():
    a, b = make_run(), make_run((False, True))
    a.results[0].error = "timeout"
    gate = evaluate_gate(a, b, GatePolicy())
    assert not gate["passed"]
    assert "baseline error rate" in gate["failures"][0]
    assert gate["matched_cases"] == 1
    assert gate["success_delta"] == 0
    assert evaluate_gate(a, b, GatePolicy(max_error_rate=0.5))["passed"]


def test_all_errors_cannot_pass_even_when_error_limit_is_one():
    a, b = make_run(), make_run()
    for r in b.results:
        r.error = "offline"
    gate = evaluate_gate(a, b, GatePolicy(max_error_rate=1.0))
    assert not gate["passed"]
    assert gate["success_delta"] is None


def test_policy_thresholds_and_critical_tasks():
    policy = GatePolicy(fail_on_regression=False, critical_tasks=["t1"],
                        min_success=0.9, min_category_success={"args": 1.0},
                        max_success_drop=0.1)
    gate = evaluate_gate(make_run(), make_run((False, True)), policy)
    assert len(gate["failures"]) == 4
    assert any("critical tasks failed: t1" in f for f in gate["failures"])


def test_policy_can_allow_bounded_drop():
    gate = evaluate_gate(make_run(), make_run((False, True)),
                         GatePolicy(fail_on_regression=False, max_success_drop=0.5))
    assert gate["passed"]


@pytest.mark.parametrize("policy", [
    GatePolicy(critical_tasks=["typo"]),
    GatePolicy(min_category_success={"sequence": 0.5}),
])
def test_unknown_policy_targets_are_rejected(policy):
    with pytest.raises(ValueError):
        evaluate_gate(make_run(), make_run(), policy)


@pytest.mark.parametrize("text", [
    "min_sucess: 0.5", "min_success: 1.1", "max_error_rate: .nan",
    "fail_on_regression: 'false'", "[]", "", "min_category_success: {typo: 0.5}",
])
def test_invalid_policy_does_not_silently_pass(tmp_path, text):
    path = tmp_path / "policy.yaml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_policy(str(path))


def test_cli_gate_json_exit_codes_and_legacy_readability(tmp_path, capsys):
    import json

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(make_run().model_dump_json())
    b.write_text(make_run((False, True)).model_dump_json())
    assert cli.main(["compare", str(a), str(b), "--fail-on-regression", "--format", "json"]) == 1
    assert not json.loads(capsys.readouterr().out)["gate"]["passed"]
    b.write_text(make_run().model_dump_json())
    assert cli.main(["compare", str(a), str(b), "--fail-on-regression"]) == 0
    capsys.readouterr()
    old = make_run()
    old.config.scoring_version = None
    b.write_text(old.model_dump_json())
    assert cli.main(["compare", str(a), str(b), "--fail-on-regression"]) == 2
    assert "scoring_version" in capsys.readouterr().err
    assert cli.main(["compare", str(a), str(b)]) == 0
