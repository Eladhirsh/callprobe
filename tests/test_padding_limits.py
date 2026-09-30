import pytest

from callprobe.models import Bundle, Expectation, RunConfig, Suite, Task, Tool
from callprobe.runner import build_toolset, prepare_config, run_suite


def _tool(name):
    return Tool(name=name, description=name, parameters={"type": "object", "properties": {}})


def _task(task_id, exclude=()):
    return Task(
        id=task_id,
        category="select",
        bundle="b",
        messages=[{"role": "user", "content": "hi"}],
        expect=Expectation(type="no_call"),
        exclude_distractors=list(exclude),
    )


def _suite(distractors, tasks, bundle_tools=("core",)):
    return Suite(
        name="pad-limits",
        bundles={"b": Bundle(name="b", tools=[_tool(n) for n in bundle_tools])},
        distractors=[_tool(n) for n in distractors],
        tasks=tasks,
    )


def _config(pads, **kwargs):
    return RunConfig(
        model="stub", endpoint="http://fake", suite="s", pads=pads, repeats=1,
        temperature=0.0, max_tokens=64, **kwargs,
    )


class _Client:
    def __init__(self):
        self.calls = 0

    def complete(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("no request may be made for an impossible pad")


def test_pad_equal_to_eligible_count_is_accepted():
    suite = _suite(["d0", "d1", "d2"], [_task("t1")])
    assert prepare_config(suite, _config([0, 3])).pads == [0, 3]


def test_zero_pad_needs_no_distractors():
    suite = _suite([], [_task("t1", exclude=["anything"])])
    assert prepare_config(suite, _config([0])).pads == [0]


def test_pad_above_pool_size_is_rejected_with_counts_and_advice():
    suite = _suite(["d0", "d1"], [_task("t1")])
    with pytest.raises(ValueError) as exc:
        prepare_config(suite, _config([0, 3]))
    message = str(exc.value)
    assert "pad 3" in message and "'t1'" in message and "only 2 eligible" in message
    assert "lower pad" in message and "more distractors" in message


def test_suite_without_distractors_rejects_positive_pad():
    suite = _suite([], [_task("t1")])
    with pytest.raises(ValueError, match="only 0 eligible"):
        prepare_config(suite, _config([4]))


def test_task_exclusions_shrink_the_eligible_pool():
    suite = _suite(["d0", "d1", "d2"], [_task("strict", exclude=["d0"])])
    with pytest.raises(ValueError, match=r"'strict'.*only 2 eligible"):
        prepare_config(suite, _config([3]))
    assert prepare_config(suite, _config([2])).pads == [2]


def test_bundle_tool_name_collisions_shrink_the_eligible_pool():
    suite = _suite(["core", "d1", "d2"], [_task("t1")])
    with pytest.raises(ValueError, match=r"'t1'.*only 2 eligible"):
        prepare_config(suite, _config([3]))
    assert prepare_config(suite, _config([2])).pads == [2]


def test_exclusion_and_collision_count_once_when_they_overlap():
    suite = _suite(["core", "d1", "d2"], [_task("t1", exclude=["core"])])
    assert prepare_config(suite, _config([2])).pads == [2]
    with pytest.raises(ValueError, match="only 2 eligible"):
        prepare_config(suite, _config([3]))


def test_selected_subset_can_avoid_the_ineligible_task():
    suite = _suite(["d0", "d1", "d2"], [_task("strict", exclude=["d0"]), _task("open")])
    with pytest.raises(ValueError, match="'strict'"):
        prepare_config(suite, _config([3]))
    with pytest.raises(ValueError, match="'strict'"):
        prepare_config(suite, _config([3], selected_task_ids=["open", "strict"]))
    prepared = prepare_config(suite, _config([3], selected_task_ids=["open"]))
    assert prepared.selected_task_ids == ["open"]


def test_impossible_pad_fails_before_any_model_request():
    suite = _suite(["d0", "d1"], [_task("t1")])
    client = _Client()
    with pytest.raises(ValueError, match="pad 5"):
        run_suite(suite, client, _config([0, 5]))
    assert client.calls == 0


def test_build_toolset_still_pads_only_from_eligible_distractors():
    suite = _suite(["core", "d0", "d1", "d2"], [_task("t1", exclude=["d0"])])
    _, tools = build_toolset(suite, suite.tasks[0], 2, seed=0)
    names = {t["function"]["name"] for t in tools}
    assert names == {"core", "d1", "d2"}


def test_pad_zero_leaves_bundle_untouched():
    suite = _suite(["d0"], [_task("t1")])
    _, tools = build_toolset(suite, suite.tasks[0], 0, seed=0)
    assert [t["function"]["name"] for t in tools] == ["core"]


@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_rejects_shortage_before_probing_or_creating_output(tmp_path, monkeypatch, capsys, dry_run):
    from callprobe import cli

    def forbidden(*args, **kwargs):
        raise AssertionError("padding must be checked before endpoint access")

    monkeypatch.setattr(cli, "probe_server_version", forbidden)
    monkeypatch.setattr(cli, "ChatClient", forbidden)
    output = tmp_path / "run.json"
    args = ["run", "--model", "stub", "--pad", "16", "--out", str(output)]
    if dry_run:
        args.append("--dry-run")
    assert cli.main(args) == 2
    assert "eligible distractor" in capsys.readouterr().err
    assert not output.exists()
