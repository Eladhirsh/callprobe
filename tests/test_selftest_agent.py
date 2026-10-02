"""End-to-end tests for scripts/selftest_agent.py against the real CLI and a loopback mock.

No model endpoint is contacted; the live option is only tested for argument refusal.
"""

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "selftest_agent.py"
spec = importlib.util.spec_from_file_location("selftest_agent", SCRIPT)
agent = importlib.util.module_from_spec(spec)
sys.modules["selftest_agent"] = agent
spec.loader.exec_module(agent)


@pytest.fixture(scope="module")
def passing_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("selftest") / "out"
    code = agent.main(["--out", str(out)])
    return code, out


def test_full_workflow_passes_and_writes_evidence(passing_run):
    code, out = passing_run
    report = json.loads((out / "report.json").read_text())
    failed = [a["name"] for a in report["assertions"] if not a["ok"]]
    assert code == 0 and report["overall"] == "PASS" and not failed
    assert [s["name"] for s in report["steps"]] == [
        "version", "init", "validate", "dry-run", "run-baseline", "run-candidate",
        "compare-json", "compare-markdown", "explain", "targeted-rerun", "targeted-as-baseline"]
    # Gate failures and the targeted-baseline refusal are expected statuses.
    expected = {s["name"]: s["expected_status"] for s in report["steps"]}
    assert expected["compare-json"] == expected["compare-markdown"] == 1
    assert expected["targeted-as-baseline"] == 2
    assert all(s["ok"] for s in report["steps"])
    assert "SYNTHETIC" in report["label"] and "not a model benchmark" in (out / "report.md").read_text()
    for step in report["steps"]:
        assert (out / step["stdout_path"]).is_file() and (out / step["stderr_path"]).is_file()


def test_run_counts_match_the_design(passing_run):
    _, out = passing_run
    baseline = json.loads((out / "baseline.json").read_text())
    candidate = json.loads((out / "candidate.json").read_text())
    targeted = json.loads((out / "targeted.json").read_text())
    assert [sum(r["success"] for r in run["results"]) for run in (baseline, candidate)] == [162, 126]
    assert len(targeted["results"]) == 4
    failed = {r["task_id"] for r in candidate["results"] if not r["success"]}
    assert failed == set(agent.INJECTED) == {r["task_id"] for r in targeted["results"]}


def test_fixtures_are_authored_synthetic_and_complete():
    root = agent.FIXTURES
    tasks = yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]
    assert len(tasks) == 18 and len({t["id"] for t in tasks}) == 18
    assert {t["expect"].get("tool") for t in tasks} == {None, "search_messages", "get_message", "send_reply"}
    assert len(yaml.safe_load((root / "distractors.yaml").read_text())["tools"]) == 4
    text = "".join((root / n).read_text() for n in ("tasks.yaml", "openapi.yaml"))
    assert "example.invalid" in text and "@example.com" not in text


def test_refuses_nonempty_out_without_touching_it(tmp_path, capsys):
    (tmp_path / "keep.txt").write_text("mine")
    assert agent.main(["--out", str(tmp_path)]) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]
    assert "refusing" in capsys.readouterr().err


def test_report_is_never_overwritten(passing_run, tmp_path):
    _, out = passing_run
    instance = agent.Agent(out, sys.executable)
    with pytest.raises(FileExistsError):
        agent.write_report(instance, 0.0, None, sys.executable)


def test_live_flags_must_be_given_together(tmp_path):
    for flags in (["--live-model", "m"], ["--live-endpoint", "http://127.0.0.1:1/v1"]):
        with pytest.raises(SystemExit) as exc:
            agent.main(["--out", str(tmp_path / "o"), *flags])
        assert exc.value.code == 2
    assert not (tmp_path / "o").exists()


def test_unexpected_subprocess_failure_still_writes_report(tmp_path):
    wrapper = tmp_path / "flaky-python"
    wrapper.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        "if 'validate' in sys.argv: sys.stderr.write('injected failure\\n'); sys.exit(7)\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "out"
    assert agent.main(["--out", str(out), "--python", str(wrapper)]) == 1
    report = json.loads((out / "report.json").read_text())
    assert report["overall"] == "FAIL" and "validate" in report["error"]
    last = report["steps"][-1]
    assert (last["name"], last["exit_status"], last["ok"]) == ("validate", 7, False)
    assert "injected failure" in (out / last["stderr_path"]).read_text()
    assert (out / "report.md").read_text().startswith("# CallProbe self-test: FAIL")


def test_missing_interpreter_fails_with_report(tmp_path):
    out = tmp_path / "out"
    assert agent.main(["--out", str(out), "--python", str(tmp_path / "nope")]) == 1
    assert json.loads((out / "report.json").read_text())["overall"] == "FAIL"


def test_server_rejects_unknown_requests_and_stops(tmp_path):
    import httpx

    tasks = yaml.safe_load((agent.FIXTURES / "tasks.yaml").read_text())["tasks"]
    with agent.ScriptedServer(tasks) as server:
        url = server.endpoint + "/chat/completions"
        body = {"model": "synthetic-baseline", "messages": tasks[0]["messages"]}
        good = httpx.post(url, json=body)
        bad = httpx.post(url, json={**body, "messages": [{"role": "user", "content": "unscripted"}]})
        assert httpx.get(server.endpoint.removesuffix("/v1") + "/api/version").status_code == 404
        assert good.status_code == 200 and bad.status_code == 400
        assert (server.accepted, server.rejected) == (1, 1)
    with pytest.raises(httpx.TransportError):
        httpx.post(url, json=body)


def test_live_mode_runs_separately_against_a_loopback_endpoint(tmp_path):
    tasks = yaml.safe_load((agent.FIXTURES / "tasks.yaml").read_text())["tasks"]
    with agent.ScriptedServer(tasks) as live:  # stands in for a model; nothing real is called
        out = tmp_path / "out"
        code = agent.main(["--out", str(out), "--live-model", "synthetic-candidate",
                           "--live-endpoint", live.endpoint])
    report = json.loads((out / "report.json").read_text())
    findings = report["notes"]["live_findings"]
    assert code == 0 and report["steps"][-2]["name"] == "live-run"
    assert (findings["observations"], findings["successes"]) == (18, 14)
    assert set(findings["model_mistakes"]) == set(agent.INJECTED)
    # Injected failures include a wrong value type, not a repairable nesting error.
    assert findings["argument_shape_summary"] == {
        "affected_observations": 0, "unique_tasks": 0, "by_kind": {}}

    assert len(json.loads((out / "live.json").read_text())["results"]) == 18


def test_relative_interpreter_is_resolved_before_changing_directory(tmp_path, monkeypatch):
    import os

    observed = []
    monkeypatch.setattr(agent.Agent, "workflow", lambda self, tasks: observed.append(self.python))
    relative = os.path.relpath(sys.executable)
    agent.main(["--out", str(tmp_path / "out"), "--python", relative])
    assert observed == [os.path.abspath(relative)]


def test_public_sweep_exercises_two_models_through_the_real_cli(tmp_path):
    from callprobe import cli

    suite = tmp_path / "mail"
    assert cli.main(["init", "--example", "mail-sandbox", "--out", str(suite)]) == 0
    tasks = yaml.safe_load((suite / "tasks.yaml").read_text())["tasks"]
    out = tmp_path / "sweep"
    with agent.ScriptedServer(tasks) as server:
        assert cli.main(["sweep", "--models", "synthetic-baseline", "synthetic-candidate",
                         "--suite", str(suite), "--endpoint", server.endpoint,
                         "--out", str(out)]) == 0
        assert (server.accepted, server.rejected) == (36, 0)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "complete"
    assert manifest["total_planned_requests"] == 36
    scores = [sum(r["success"] for r in json.loads((out / entry["result_file"]).read_text())["results"])
              for entry in manifest["models"]]
    assert scores == [18, 14]
    assert "18/18/18" in (out / "leaderboard.md").read_text()


def test_sweep_junit_uses_real_cli_without_extra_model_requests(tmp_path):
    import xml.etree.ElementTree as ET
    from callprobe.sweep import main as sweep_main

    tasks = yaml.safe_load((agent.FIXTURES / 'tasks.yaml').read_text())['tasks']
    from callprobe.cli import main as cli_main
    suite = tmp_path / 'suite'
    assert cli_main(['init', '--example', 'mail-sandbox', '--out', str(suite)]) == 0
    out = tmp_path / 'sweep'
    with agent.ScriptedServer(tasks) as server:
        code = sweep_main(['--models', 'synthetic-baseline', 'synthetic-candidate',
                           '--suite', str(suite), '--endpoint', server.endpoint,
                           '--out', str(out), '--junit'])
        assert code == 0
        assert server.accepted == 36 and server.rejected == 0
    manifest = json.loads((out / 'manifest.json').read_text())
    for entry, expected_failures in zip(manifest['models'], [0, 4]):
        tree = ET.parse(out / entry['junit_file'])
        assert len(tree.findall('.//testcase')) == 18
        assert len(tree.findall('.//failure')) == expected_failures
        assert not tree.findall('.//error')
        assert entry['status'] == 'ok'


def test_sweep_junit_preserves_all_request_error_results(tmp_path):
    import xml.etree.ElementTree as ET
    from callprobe.sweep import main as sweep_main

    tasks = yaml.safe_load((agent.FIXTURES / 'tasks.yaml').read_text())['tasks']
    from callprobe.cli import main as cli_main
    suite = tmp_path / 'suite'
    assert cli_main(['init', '--example', 'mail-sandbox', '--out', str(suite)]) == 0
    out = tmp_path / 'errors'
    with agent.ScriptedServer(tasks) as server:
        code = sweep_main(['--models', 'unavailable-model', '--suite', str(suite),
                           '--endpoint', server.endpoint, '--out', str(out), '--junit'])
        assert code == 1
        assert server.accepted == 0 and server.rejected == 18
    manifest = json.loads((out / 'manifest.json').read_text())
    entry = manifest['models'][0]
    assert entry['status'] == 'failed' and 'result_file' not in entry
    assert (out / entry['raw_result_file']).is_file()
    tree = ET.parse(out / entry['junit_file'])
    assert len(tree.findall('.//error')) == 18
    assert not tree.findall('.//failure')
