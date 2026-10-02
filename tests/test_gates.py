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


@pytest.mark.parametrize("side", ["a", "b"])
def test_targeted_runs_are_refused_by_the_gate(side):
    a, b = make_run(), make_run()
    target = a if side == "a" else b
    target.config.selected_task_ids = ["t1", "t2"]
    with pytest.raises(ValueError, match="targeted runs are for debugging"):
        evaluate_gate(a, b, GatePolicy())


def test_all_selected_targeted_run_still_refused_by_the_gate():
    a, b = make_run(), make_run()
    b.config.selected_task_ids = list(b.config.task_ids)
    with pytest.raises(ValueError, match="targeted runs are for debugging"):
        evaluate_gate(a, b, GatePolicy())


def test_identical_partial_runs_are_refused_by_the_gate():
    a, b = make_run(), make_run()
    a.config.selected_task_ids = ["t1"]
    b.config.selected_task_ids = ["t1"]
    with pytest.raises(ValueError, match="targeted runs are for debugging"):
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


def test_empty_string_error_counts_toward_error_rate_and_excludes_from_pairs():
    a, b = make_run(), make_run()
    # an empty-string error must be treated as a request error, not scored
    a.results[0].error = ""
    gate = evaluate_gate(a, b, GatePolicy())
    assert not gate["passed"]
    assert "baseline error rate" in gate["failures"][0]
    assert gate["matched_cases"] == 1  # the empty-error pair is excluded


def test_empty_string_error_still_fails_a_critical_task_when_errors_are_allowed():
    a, b = make_run(), make_run()
    b.results[0].error = ""
    policy = GatePolicy(fail_on_regression=False, critical_tasks=["t1"],
                        max_error_rate=1.0)
    gate = evaluate_gate(a, b, policy)
    assert not gate["passed"]
    assert any("critical tasks failed: t1" in f for f in gate["failures"])


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


def test_huge_incomplete_plan_is_rejected_without_expanding_repeats(monkeypatch):
    from callprobe import gates

    def no_expansion(*args):
        pytest.fail('coverage validation expanded the planned repeat range')

    monkeypatch.setattr(gates, 'range', no_expansion, raising=False)
    a, b = make_run(), make_run()
    a.config.repeats = 10**12
    with pytest.raises(ValueError, match='1999999999998 missing, 0 unexpected'):
        evaluate_gate(a, b, GatePolicy())


@pytest.mark.parametrize('field,value', [('task_id', 'unknown'), ('pad', 8), ('repeat', 1),
                                          ('repeat', -1), ('repeat', True), ('pad', False)])
def test_matching_row_count_cannot_hide_out_of_plan_observations(field, value):
    a, b = make_run(), make_run()
    setattr(b.results[0], field, value)
    with pytest.raises(ValueError, match='1 missing, 1 unexpected'):
        evaluate_gate(a, b, GatePolicy())


@pytest.mark.parametrize('field,value', [('repeats', True), ('repeats', 1.0),
                                         ('repeats', 0), ('pads', [False]), ('pads', [0.0])])
def test_malformed_in_memory_plan_rejected(field, value):
    a, b = make_run(), make_run()
    setattr(b.config, field, value)
    with pytest.raises(ValueError, match='invalid planned coverage'):
        evaluate_gate(a, b, GatePolicy())


def test_gate_accepts_complete_multi_pad_repeat_coverage_in_any_order():
    a = make_run()
    a.config.pads = [0, 2]
    a.config.repeats = 3
    a.results = [row.model_copy(update={'pad': pad, 'repeat': repeat})
                 for row in a.results for pad in a.config.pads for repeat in range(3)]
    b = a.model_copy(deep=True)
    b.results.reverse()
    gate = evaluate_gate(a, b, GatePolicy())
    assert gate['passed'] and gate['matched_cases'] == 12


def test_cli_rejects_huge_partial_file_without_rewriting_inputs(tmp_path, capsys):
    a = make_run()
    a.config.repeats = 10**12
    source = tmp_path / 'partial.json'
    source.write_text(a.model_dump_json())
    original = source.read_bytes()
    assert cli.main(['compare', str(source), str(source), '--fail-on-regression']) == 2
    output = capsys.readouterr()
    assert '1999999999998 missing, 0 unexpected' in output.err
    assert not output.out
    assert source.read_bytes() == original


@pytest.mark.parametrize('text', [
    'max_error_rate: 0\nmax_error_rate: 1\n',
    'fail_on_regression: true\nfail_on_regression: false\n',
    'min_category_success:\n  args: 1\n  args: 0\n',
    'min_success: 1\n"min_success": 0\n',
])
def test_duplicate_policy_keys_cannot_silently_weaken_gates(tmp_path, text):
    path = tmp_path / 'policy.yaml'
    path.write_text(text)
    with pytest.raises(ValueError, match='--policy: duplicate key'):
        load_policy(str(path))


@pytest.mark.parametrize('text', [
    '1: 0.5\n',
    '<<: {min_success: 1}\nmin_success: 0\n',
])
def test_policy_rejects_nonstring_and_merge_keys(tmp_path, text):
    path = tmp_path / 'policy.yaml'
    path.write_text(text)
    with pytest.raises(ValueError, match='mapping keys must be strings'):
        load_policy(str(path))


@pytest.mark.parametrize('text', [
    'min_success: PRIVATE_VALUE\n',
    'api_key: PRIVATE_VALUE\n',
    'min_success: [PRIVATE_VALUE\n',
    'min_success: !!int PRIVATE_VALUE\n',
    'min_success: !!bool PRIVATE_VALUE\n',
    'min_success: !!timestamp PRIVATE_VALUE\n',
    'min_success: !!python/object:PRIVATE_VALUE {}\n',
])
def test_policy_errors_do_not_echo_configured_values(tmp_path, text):
    path = tmp_path / 'policy.yaml'
    path.write_text(text)
    with pytest.raises(ValueError) as exc:
        load_policy(str(path))
    assert '--policy:' in str(exc.value)
    assert 'PRIVATE_VALUE' not in str(exc.value)


def test_cli_duplicate_policy_is_invalid_input_not_a_pass(tmp_path, capsys):
    source = tmp_path / 'run.json'
    policy = tmp_path / 'policy.yaml'
    source.write_text(make_run().model_dump_json())
    policy.write_text('min_success: 1\nmin_success: 0\n')
    before = source.read_bytes(), policy.read_bytes()
    assert cli.main(['compare', str(source), str(source), '--policy', str(policy)]) == 2
    output = capsys.readouterr()
    assert not output.out and 'duplicate key' in output.err
    assert (source.read_bytes(), policy.read_bytes()) == before


def test_valid_policy_preserves_all_thresholds_and_default_policy(tmp_path):
    path = tmp_path / 'policy.yaml'
    path.write_text('fail_on_regression: false\nmax_error_rate: 0.05\n'
                    'min_category_success: {args: 0.8, abstain: 1}\ncritical_tasks: [t1]\n')
    policy = load_policy(str(path))
    assert policy == GatePolicy(fail_on_regression=False, max_error_rate=0.05,
                               min_category_success={'args': 0.8, 'abstain': 1}, critical_tasks=['t1'])
    assert load_policy(None) == GatePolicy()
