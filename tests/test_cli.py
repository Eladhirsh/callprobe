import json
import math
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.client import Completion

SUITE = Path(__file__).resolve().parents[1] / "src" / "callprobe" / "suites" / "core"


class _FakeClient:
    """Never calls a tool, so only the abstain tasks succeed."""

    def __init__(self, *args, **kwargs):
        pass

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        return Completion(content="no thanks", prompt_tokens=1, completion_tokens=1)

    def close(self):
        pass


def _run_cli(monkeypatch, extra_args, capsys, client=_FakeClient, setup=True):
    if setup:
        monkeypatch.setattr(cli, "ChatClient", client)
        monkeypatch.setattr(cli, "probe_server_version", lambda _: (None, None))
    args = [
        "run",
        "--model",
        "stub",
        "--suite",
        str(SUITE),
        "--pad",
        "0",
        "--repeats",
        "1",
        "--quiet",
        *extra_args,
    ]
    code = cli.main(args)
    return code, capsys.readouterr().out


def test_format_json_is_valid_and_strict(monkeypatch, capsys):
    code, out = _run_cli(monkeypatch, ["--format", "json"], capsys)
    assert code == 0
    payload = json.loads(out)  # raises if malformed
    assert 0.0 <= payload["overall"]["success"] <= 1.0
    # inf must not leak through as a bare, non-standard JSON token.
    assert "Infinity" not in out
    assert payload["cost"]["tokens_per_success"] is None or math.isfinite(
        payload["cost"]["tokens_per_success"]
    )


def test_fail_under_passes_when_threshold_met(monkeypatch, capsys):
    code, _ = _run_cli(monkeypatch, ["--format", "json", "--fail-under", "0.0"], capsys)
    assert code == 0


def test_fail_under_fails_when_threshold_not_met(monkeypatch, capsys):
    code, _ = _run_cli(monkeypatch, ["--format", "json", "--fail-under", "0.99"], capsys)
    assert code == 1


def test_text_format_unaffected_by_fail_under_flag(monkeypatch, capsys):
    code, out = _run_cli(monkeypatch, ["--fail-under", "0.99"], capsys)
    assert code == 1
    assert "model            stub" in out  # still the human-readable report


def test_missing_resume_file_is_an_error(monkeypatch, tmp_path, capsys):
    code, _ = _run_cli(monkeypatch, ["--resume", str(tmp_path / "missing.json")], capsys)
    assert code == 2


def test_resume_rejects_changed_model_without_overwriting_checkpoint(monkeypatch, tmp_path, capsys):
    path = tmp_path / "run.json"
    assert _run_cli(monkeypatch, ["--out", str(path)], capsys)[0] == 0
    original = path.read_bytes()
    code, _ = _run_cli(monkeypatch, ["--model", "other", "--resume", str(path),
                                    "--out", str(path)], capsys)
    assert code == 2
    assert path.read_bytes() == original


def test_failed_checkpoint_write_preserves_previous_file(monkeypatch, tmp_path):
    from test_gates import make_run

    path = tmp_path / "run.json"
    path.write_text("previous checkpoint")

    def fail_replace(self, target):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        cli._write_run(str(path), make_run())
    assert path.read_text() == "previous checkpoint"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("interrupt", [False, True])
def test_fail_under_cannot_pass_errored_or_interrupted_run(monkeypatch, capsys, interrupt):
    def complete(self, **kwargs):
        if interrupt:
            raise KeyboardInterrupt
        return Completion(error="offline")

    monkeypatch.setattr(_FakeClient, "complete", complete)
    code, _ = _run_cli(monkeypatch, ["--fail-under", "0"], capsys)
    assert code == 1


# ------------------------------------------------------------- targeting


from callprobe.loader import load_suite  # noqa: E402

_SUITE_OBJ = load_suite(SUITE)
_SOME_ID = _SUITE_OBJ.tasks[0].id
_ANOTHER_ID = _SUITE_OBJ.tasks[1].id
_ABSTAIN_ID = next(t.id for t in _SUITE_OBJ.tasks if t.category == "abstain")


class _CountingFakeClient(_FakeClient):
    calls = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def complete(self, model, messages, tools, temperature=0.0, max_tokens=512):
        type(self).calls += 1
        return super().complete(model, messages, tools, temperature, max_tokens)


class _UnreachableClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError("ChatClient must not be constructed for this run")


def test_task_flag_limits_calls_and_coverage(monkeypatch, capsys):
    _CountingFakeClient.calls = 0
    code, out = _run_cli(
        monkeypatch, ["--task", _SOME_ID, "--task", _ANOTHER_ID, "--format", "json"], capsys,
        client=_CountingFakeClient,
    )
    assert code == 0
    assert _CountingFakeClient.calls == 2
    payload = json.loads(out)
    assert payload["n"] == 2
    assert payload["scope"] == {
        "targeted": True, "selected_task_count": 2, "total_task_count": len(_SUITE_OBJ.tasks),
    }


def test_task_flag_repeated_id_still_counts_once(monkeypatch, capsys):
    _CountingFakeClient.calls = 0
    code, out = _run_cli(
        monkeypatch, ["--task", _SOME_ID, "--task", _SOME_ID, "--format", "json"], capsys,
        client=_CountingFakeClient,
    )
    assert code == 0
    assert _CountingFakeClient.calls == 1


def test_unknown_task_id_fails_before_endpoint_probing_or_client_creation(monkeypatch, capsys):
    def boom(_):
        raise AssertionError("must not probe the endpoint for an unknown task id")

    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _ = _run_cli(monkeypatch, ["--task", "does-not-exist"], capsys, setup=False)
    assert code == 2


def test_task_and_failed_from_are_mutually_exclusive(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            "run", "--model", "stub", "--suite", str(SUITE), "--task", _SOME_ID,
            "--failed-from", str(tmp_path / "r.json"),
        ])
    assert excinfo.value.code == 2


def test_fail_under_rejected_with_targeting_before_anything_runs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            "run", "--model", "stub", "--suite", str(SUITE), "--task", _SOME_ID,
            "--fail-under", "0.5",
        ])
    assert excinfo.value.code == 2


def _write_source_run(monkeypatch, tmp_path, capsys) -> Path:
    """A full run where every non-abstain task fails and abstain tasks pass."""
    path = tmp_path / "source.json"
    code, _ = _run_cli(monkeypatch, ["--out", str(path)], capsys)
    assert code == 0
    return path


def test_failed_from_selects_failing_tasks_and_dedups_across_pads(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    saved = json.loads(source.read_text())
    failing_ids = {r["task_id"] for r in saved["results"] if not r["success"]}
    assert failing_ids  # sanity: the fake client fails every non-abstain task

    _CountingFakeClient.calls = 0
    out_path = tmp_path / "rerun.json"
    code, out = _run_cli(
        monkeypatch,
        ["--failed-from", str(source), "--out", str(out_path), "--format", "json"],
        capsys,
        client=_CountingFakeClient,
    )
    assert code == 0
    assert _CountingFakeClient.calls == len(failing_ids)
    payload = json.loads(out)
    assert payload["n"] == len(failing_ids)
    rerun = json.loads(out_path.read_text())
    assert {r["task_id"] for r in rerun["results"]} == failing_ids
    # canonical suite order preserved
    order = [t.id for t in _SUITE_OBJ.tasks if t.id in failing_ids]
    assert [r["task_id"] for r in rerun["results"]] == order


def test_failed_from_includes_request_errors(monkeypatch, tmp_path, capsys):
    original_complete = _FakeClient.complete

    def erroring(self, model, messages, tools, temperature=0.0, max_tokens=512):
        return Completion(error="offline")

    monkeypatch.setattr(_FakeClient, "complete", erroring)
    source = tmp_path / "source.json"
    code, _ = _run_cli(monkeypatch, ["--out", str(source), "--task", _ABSTAIN_ID], capsys)
    assert code == 0
    monkeypatch.setattr(_FakeClient, "complete", original_complete)

    _CountingFakeClient.calls = 0
    code, out = _run_cli(
        monkeypatch, ["--failed-from", str(source), "--format", "json"], capsys,
        client=_CountingFakeClient,
    )
    assert code == 0
    assert _CountingFakeClient.calls == 1
    assert json.loads(out)["n"] == 1


def test_failed_from_no_op_when_source_has_no_failures(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.json"
    code, _ = _run_cli(monkeypatch, ["--out", str(source), "--task", _ABSTAIN_ID], capsys)
    assert code == 0

    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("no-op must not probe the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    out_path = tmp_path / "should-not-exist.json"
    code, out = _run_cli(
        monkeypatch,
        ["--failed-from", str(source), "--out", str(out_path), "--format", "json"],
        capsys,
        setup=False,
    )
    assert code == 0
    assert not out_path.exists()
    payload = json.loads(out)
    assert payload["noop"] is True


def test_failed_from_text_no_op_message(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.json"
    code, _ = _run_cli(monkeypatch, ["--out", str(source), "--task", _ABSTAIN_ID], capsys)
    assert code == 0
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    code, out = _run_cli(monkeypatch, ["--failed-from", str(source)], capsys, setup=False)
    assert code == 0
    assert "nothing to rerun" in out


def test_failed_from_rejects_unknown_task_ids_in_source(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    data = json.loads(source.read_text())
    data["results"][0]["task_id"] = "not-in-suite"
    source.write_text(json.dumps(data))

    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _ = _run_cli(monkeypatch, ["--failed-from", str(source)], capsys, setup=False)
    assert code == 2


@pytest.mark.parametrize("mutation", [
    lambda d: d["config"].__setitem__("suite_hash", "different"),
    lambda d: d["config"].__setitem__("suite_hash", None),
    lambda d: d["config"].__setitem__("scoring_version", None),
    lambda d: d["config"].__setitem__("scoring_version", 1),
])
def test_failed_from_rejects_incompatible_provenance_before_probing(
    monkeypatch, tmp_path, capsys, mutation
):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    data = json.loads(source.read_text())
    mutation(data)
    source.write_text(json.dumps(data))

    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _ = _run_cli(monkeypatch, ["--failed-from", str(source)], capsys, setup=False)
    assert code == 2


def test_failed_from_rejects_out_alias_of_source(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    code, _ = _run_cli(
        monkeypatch, ["--failed-from", str(source), "--out", str(source)], capsys,
        setup=False,
    )
    assert code == 2
    # evidence untouched
    assert json.loads(source.read_text())["results"]


def test_failed_from_rejects_out_symlink_alias_of_source(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    alias = tmp_path / "alias.json"
    alias.symlink_to(source)
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    code, _ = _run_cli(
        monkeypatch, ["--failed-from", str(source), "--out", str(alias)], capsys,
        setup=False,
    )
    assert code == 2


def test_failed_from_rejects_out_hardlink_alias_of_source(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    alias = tmp_path / "hardlink.json"
    import os
    os.link(source, alias)
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    code, _ = _run_cli(
        monkeypatch, ["--failed-from", str(source), "--out", str(alias)], capsys,
        setup=False,
    )
    assert code == 2


def test_selected_task_run_cannot_gate_ci_via_compare(monkeypatch, tmp_path, capsys):
    source = _write_source_run(monkeypatch, tmp_path, capsys)
    targeted = tmp_path / "targeted.json"
    monkeypatch.setattr(cli, "ChatClient", _FakeClient)
    monkeypatch.setattr(cli, "probe_server_version", lambda _: (None, None))
    code, _ = _run_cli(
        monkeypatch, ["--task", _SOME_ID, "--out", str(targeted)], capsys
    )
    assert code == 0
    code = cli.main([
        "compare", str(source), str(targeted), "--fail-on-regression",
    ])
    assert code == 2


def test_leaderboard_rejects_targeted_run_even_with_allow_mixed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "ChatClient", _FakeClient)
    monkeypatch.setattr(cli, "probe_server_version", lambda _: (None, None))
    targeted = tmp_path / "targeted.json"
    code, _ = _run_cli(monkeypatch, ["--task", _SOME_ID, "--out", str(targeted)], capsys)
    assert code == 0
    code = cli.main(["leaderboard", str(targeted), "--allow-mixed"])
    assert code == 1
