import json

import pytest

from didyoureally.bench import default_cases_dir
from didyoureally.cli import main


@pytest.mark.parametrize("prefix,unchecked", [("83_", ["to"]), ("84_", [])])
@pytest.mark.parametrize("strict", [False, True])
def test_unchecked_exit_policy_keeps_deterministic_report(prefix, unchecked, strict, tmp_path, capsys):
    case = json.loads(next(default_cases_dir().glob(prefix + "*.json")).read_text())
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps({**case["trace"], "claims": case["claims"]}))
    args = ["check", str(trace_path), "--format", "json", "--fail-on", ""]
    if strict:
        args.append("--fail-on-unchecked")
    assert main(args) == (1 if strict and unchecked else 0)
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "complete"
    assert report["findings"][0]["verdict"] == "backed"
    assert report["findings"][0]["unchecked"] == unchecked
