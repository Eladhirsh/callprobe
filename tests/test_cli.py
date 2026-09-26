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


def test_compare_format_markdown_reports_gate_and_leaves_exit_status_unchanged(
    monkeypatch, tmp_path, capsys
):
    a = _write_source_run(monkeypatch, tmp_path, capsys)
    b = tmp_path / "b.json"
    a.replace(b)
    code = cli.main(["compare", str(b), str(b), "--format", "markdown", "--fail-on-regression"])
    out = capsys.readouterr().out
    assert code == 0
    assert "## Comparison" in out
    assert "**CI gate:** PASS" in out


def test_leaderboard_rejects_targeted_run_even_with_allow_mixed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "ChatClient", _FakeClient)
    monkeypatch.setattr(cli, "probe_server_version", lambda _: (None, None))
    targeted = tmp_path / "targeted.json"
    code, _ = _run_cli(monkeypatch, ["--task", _SOME_ID, "--out", str(targeted)], capsys)
    assert code == 0
    code = cli.main(["leaderboard", str(targeted), "--allow-mixed"])
    assert code == 1


# ------------------------------------------------------------ --config


def _run_config_cli(monkeypatch, args, capsys, client=_FakeClient):
    monkeypatch.setattr(cli, "ChatClient", client)
    def probe(_):
        if client is _UnreachableClient:
            raise AssertionError("must fail before probing the endpoint")
        return None, None

    monkeypatch.setattr(cli, "probe_server_version", probe)
    code = cli.main(["run", *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_no_config_behavior_and_defaults_unchanged(monkeypatch, capsys):
    code, out, _ = _run_config_cli(
        monkeypatch,
        ["--model", "stub", "--suite", str(SUITE), "--quiet", "--format", "json"],
        capsys,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["endpoint"] == "http://localhost:11434/v1"
    assert set(payload["by_pad"]) == {"0", "8", "16"}


def test_missing_model_without_config_or_flag_is_actionable_exit_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, err = _run_config_cli(monkeypatch, ["--suite", str(SUITE)], capsys, client=_UnreachableClient)
    assert code == 2
    assert "--model" in err


def test_config_supplies_model_and_effective_config_reflects_merge(monkeypatch, tmp_path, capsys):
    out_path = tmp_path / "run.json"
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"""
model: qwen2.5:7b
suite: {SUITE}
pads: [0]
repeats: 1
temperature: 0.3
max_tokens: 1024
quant: q4_K_M
notes: from config
retries: 2
concurrency: 1
out: {out_path.name}
""")
    code, out, _ = _run_config_cli(
        monkeypatch, ["--config", str(config_path), "--quiet", "--format", "json"], capsys
    )
    assert code == 0
    assert json.loads(out)["model"] == "qwen2.5:7b"
    saved = json.loads(out_path.read_text())
    saved_config = saved["config"]
    assert saved_config["model"] == "qwen2.5:7b"
    assert saved_config["pads"] == [0]
    assert saved_config["repeats"] == 1
    assert saved_config["temperature"] == 0.3
    assert saved_config["max_tokens"] == 1024
    assert saved_config["quantization"] == "q4_K_M"
    assert saved_config["notes"] == "from config"


def test_missing_model_in_config_and_no_flag_is_actionable_exit_2(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"suite: {SUITE}\npads: [0]\n")
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, err = _run_config_cli(
        monkeypatch, ["--config", str(config_path)], capsys, client=_UnreachableClient
    )
    assert code == 2
    assert "--model" in err


def test_cli_model_flag_overrides_config_model(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: from-config\nsuite: {SUITE}\npads: [0]\n")
    code, out, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--model", "from-cli", "--quiet", "--format", "json"],
        capsys,
    )
    assert code == 0
    assert json.loads(out)["model"] == "from-cli"


def test_equals_style_flag_overrides_config(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: from-config\nsuite: {SUITE}\npads: [0]\n")
    code, out, _ = _run_config_cli(
        monkeypatch,
        [f"--config={config_path}", "--model=from-cli", "--quiet", "--format", "json"],
        capsys,
    )
    assert code == 0
    assert json.loads(out)["model"] == "from-cli"


def test_cli_pad_comma_notation_overrides_config_pads(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0, 8]\n")
    code, out, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--pad", "0,8,16", "--quiet", "--format", "json"],
        capsys,
    )
    assert code == 0
    assert set(json.loads(out)["by_pad"]) == {"0", "8", "16"}


def test_config_pads_used_when_no_cli_pad_given(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0, 8]\n")
    code, out, _ = _run_config_cli(
        monkeypatch, ["--config", str(config_path), "--quiet", "--format", "json"], capsys
    )
    assert code == 0
    assert set(json.loads(out)["by_pad"]) == {"0", "8"}


def test_relative_suite_and_out_resolve_against_config_dir_not_cwd(monkeypatch, tmp_path, capsys):
    project = tmp_path / "project"
    project.mkdir()
    import shutil
    suite_copy = project / "suite"
    shutil.copytree(SUITE, suite_copy)
    config_path = project / "run.yaml"
    config_path.write_text("model: stub\nsuite: suite\npads: [0]\nout: results/run.json\n")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    import os
    old_cwd = os.getcwd()
    os.chdir(elsewhere)
    try:
        code, out, _ = _run_config_cli(
            monkeypatch, ["--config", str(config_path), "--quiet", "--format", "json"], capsys
        )
    finally:
        os.chdir(old_cwd)
    assert code == 0
    assert json.loads(out)["n"] == 50
    assert (project / "results" / "run.json").exists()
    assert not (elsewhere / "results").exists()


def test_cli_out_override_stays_cwd_relative(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0]\nout: config-relative.json\n")
    cli_out = tmp_path / "cli-relative.json"
    code, _, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--out", str(cli_out), "--quiet"],
        capsys,
    )
    assert code == 0
    assert cli_out.exists()
    assert not (tmp_path / "config-relative.json").exists()


@pytest.mark.parametrize("bad_text", [
    "model: stub\nmax_tokens: -1\n",
    "model: stub\nmax_tokens: not-an-int\n",
    "model: stub\npads: []\n",
    "model: stub\npads: [0, 0]\n",
    "model: stub\nunknown_field: 1\n",
    "model: stub\nmodel: stub\n",
])
def test_invalid_config_fails_before_endpoint_probing(monkeypatch, tmp_path, capsys, bad_text):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(bad_text)
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, _ = _run_config_cli(
        monkeypatch, ["--config", str(config_path), "--suite", str(SUITE)], capsys,
        client=_UnreachableClient,
    )
    assert code == 2


def test_invalid_config_field_fails_even_when_that_field_is_overridden_by_cli(monkeypatch, tmp_path, capsys):
    """An invalid value elsewhere in the file still fails the whole file,
    even though the CLI overrides the one field the file gets wrong."""
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\nmax_tokens: -1\n")
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--max-tokens", "2048"],
        capsys,
        client=_UnreachableClient,
    )
    assert code == 2


def test_config_error_output_never_echoes_secret_values(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text("model: stub\napi_key: sk-super-secret-value\n")
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, err = _run_config_cli(
        monkeypatch, ["--config", str(config_path)], capsys, client=_UnreachableClient
    )
    assert code == 2
    assert "sk-super-secret-value" not in err
    assert "api_key" in err


def test_out_cannot_alias_config_file(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0]\n")
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--out", str(config_path)],
        capsys,
        client=_UnreachableClient,
    )
    assert code == 2
    assert "model: stub" in config_path.read_text()


def test_config_missing_file_is_actionable_exit_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)

    def boom(_):
        raise AssertionError("must fail before probing the endpoint")

    monkeypatch.setattr(cli, "probe_server_version", boom)
    code, _, err = _run_config_cli(
        monkeypatch, ["--config", str(tmp_path / "missing.yaml")], capsys, client=_UnreachableClient
    )
    assert code == 2
    assert "not found" in err


def test_task_targeting_works_with_merged_config(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0]\n")
    _CountingFakeClient.calls = 0
    code, out, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--task", _SOME_ID, "--quiet", "--format", "json"],
        capsys,
        client=_CountingFakeClient,
    )
    assert code == 0
    assert _CountingFakeClient.calls == 1
    assert json.loads(out)["n"] == 1


def test_fail_under_rejected_with_targeting_and_config(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0]\n")
    monkeypatch.setattr(cli, "ChatClient", _UnreachableClient)
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            "run", "--config", str(config_path), "--task", _SOME_ID, "--fail-under", "0.5",
        ])
    assert excinfo.value.code == 2


def test_resume_still_works_with_config_supplied_settings(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.yaml"
    out_path = tmp_path / "run.json"
    config_path.write_text(f"model: stub\nsuite: {SUITE}\npads: [0]\nout: {out_path.name}\n")
    code, _, _ = _run_config_cli(
        monkeypatch, ["--config", str(config_path), "--quiet"], capsys
    )
    assert code == 0
    original = out_path.read_bytes()
    code, _, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--resume", str(out_path), "--out", str(out_path), "--quiet"],
        capsys,
    )
    assert code == 0
    assert out_path.exists()
    assert out_path.read_bytes() != b""
    original = out_path.read_bytes()
    # a changed model still rejects the resume, config settings included
    code, _, _ = _run_config_cli(
        monkeypatch,
        ["--config", str(config_path), "--model", "other", "--resume", str(out_path),
         "--out", str(out_path), "--quiet"],
        capsys,
    )
    assert code == 2
    assert out_path.read_bytes() == original


def test_cli_relative_paths_and_default_value_override_config(monkeypatch, tmp_path, capsys):
    import shutil

    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shutil.copytree(SUITE, elsewhere / "suite")
    config = project / "run.yaml"
    config.write_text("model: stub\nsuite: ignored\nout: ignored.json\npads: [0]\nmax_tokens: 4096\n")
    monkeypatch.chdir(elsewhere)
    code, _, _ = _run_config_cli(monkeypatch, [
        "--config", "../project/run.yaml", "--suite", "suite", "--out", "result.json",
        "--max-tokens=2048", "--task", _ABSTAIN_ID, "--quiet",
    ], capsys)
    assert code == 0
    saved = json.loads((elsewhere / "result.json").read_text())
    assert saved["config"]["max_tokens"] == 2048
    assert saved["config"]["suite"] == "suite"
    assert not (project / "ignored.json").exists()


@pytest.mark.parametrize("link", ["symlink", "hardlink", "configured"])
def test_config_source_is_protected_from_output_aliases(monkeypatch, tmp_path, capsys, link):
    import os

    config = tmp_path / "run.yaml"
    config.write_text("model: stub\nout: run.yaml\n")
    original = config.read_bytes()
    args = ["--config", str(config)]
    if link != "configured":
        alias = tmp_path / "alias.yaml"
        if link == "symlink":
            alias.symlink_to(config)
        else:
            os.link(config, alias)
        args += ["--out", str(alias)]
    code, _, err = _run_config_cli(monkeypatch, args, capsys, client=_UnreachableClient)
    assert code == 2 and "alias" in err
    assert config.read_bytes() == original


@pytest.mark.parametrize("flags", [
    ["--pad", "0,0"], ["--pad", ""], ["--pad=-1"], ["--repeats", "0"],
])
def test_invalid_planned_coverage_fails_before_server_probe(monkeypatch, flags, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid coverage must not contact an endpoint")
    monkeypatch.setattr(cli, "ChatClient", forbidden)
    monkeypatch.setattr(cli, "probe_server_version", forbidden)
    out = tmp_path / "results.json"
    out.write_text("preserved")
    code = cli.main(["run", "--model", "stub", "--out", str(out), *flags])
    assert code == 2
    assert out.read_text() == "preserved"
    assert "error:" in capsys.readouterr().err
