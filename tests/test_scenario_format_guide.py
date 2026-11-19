"""Every marked example in docs/scenario-formats.md must load and behave as documented."""

import json
import re
from pathlib import Path

import pytest

from callprobe.agent_session import load_agent_suite
from callprobe.cli import main
from callprobe.loader import load_suite
from callprobe.validate import validate_suite

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "scenario-formats.md"
EXAMPLE = re.compile(r"<!-- example: (?P<name>[\w.-]+) -->\n```\w+\n(?P<body>.*?)```", re.DOTALL)


def examples() -> dict[str, str]:
    found = {m["name"]: m["body"] for m in EXAMPLE.finditer(GUIDE.read_text(encoding="utf-8"))}
    assert set(found) == {
        "decision-suite.yaml",
        "decision-tools.yaml",
        "decision-distractors.yaml",
        "decision-tasks.yaml",
        "agent-suite.json",
        "audit-trace.json",
        "audit-claims.json",
        "audit-case.json",
    }
    return found


def write_decision_suite(directory: Path, tasks: str | None = None) -> Path:
    ex = examples()
    directory.mkdir()
    for name in ("suite", "tools", "distractors", "tasks"):
        (directory / f"{name}.yaml").write_text(ex[f"decision-{name}.yaml"], encoding="utf-8")
    if tasks is not None:
        (directory / "tasks.yaml").write_text(tasks, encoding="utf-8")
    return directory


def test_decision_suite_example_validates(tmp_path):
    suite = load_suite(write_decision_suite(tmp_path / "suite"))
    assert validate_suite(suite) == []
    assert [t.id for t in suite.tasks] == ["args-partial-refund", "abstain-address-change"]
    assert suite.tasks[1].exclude_distractors == ["update_shipping_address"]
    assert main(["validate", "--suite", str(tmp_path / "suite")]) == 0


def test_documented_yaml_strictness_gap_is_still_accurate(tmp_path):
    """The guide says unknown fields are ignored and the last duplicate key wins.

    If this fails, the loader became stricter: update the strictness table in the guide.
    """
    tasks = examples()["decision-tasks.yaml"]
    unknown = tasks.replace("    category: args\n", "    category: args\n    exclude_distractor: [x]\n", 1)
    suite = load_suite(write_decision_suite(tmp_path / "unknown", unknown))
    assert validate_suite(suite) == []
    duplicate = tasks.replace("    category: args\n", "    category: select\n    category: args\n", 1)
    suite = load_suite(write_decision_suite(tmp_path / "duplicate", duplicate))
    assert suite.tasks[0].category == "args"


def test_agent_suite_example_loads():
    raw = json.loads(examples()["agent-suite.json"])
    suite = load_agent_suite(raw)
    case = suite.cases[0]
    assert case.tools[0].outcomes[0].status == "error"
    assert [d.type for d in case.expected] == ["call", "no_call"]


def test_agent_suite_rejects_unknown_fields_as_documented():
    raw = json.loads(examples()["agent-suite.json"])
    raw["cases"][0]["notes"] = "not part of the format"
    with pytest.raises(ValueError, match="invalid agent suite fields"):
        load_agent_suite(raw)


def test_audit_trace_and_claims_example_is_contradicted(tmp_path, capsys):
    ex = examples()
    trace = tmp_path / "refund-wrong-amount.json"
    claims = tmp_path / "claims.json"
    trace.write_text(ex["audit-trace.json"], encoding="utf-8")
    claims.write_text(ex["audit-claims.json"], encoding="utf-8")
    assert main(["audit", str(trace), "--claims", str(claims)]) == 1
    out = capsys.readouterr().out
    assert "Contradicted 1" in out
    assert "Phantom 0" in out and "Masked failure 0" in out and "Unmentioned 0" in out


def test_audit_case_example_passes_its_own_benchmark(tmp_path, capsys):
    cases = tmp_path / "my-cases"
    cases.mkdir()
    (cases / "refund-wrong-amount.json").write_text(examples()["audit-case.json"], encoding="utf-8")
    assert main(["audit", "bench", "--cases", str(cases)]) == 0
    assert "1/1 cases exact" in capsys.readouterr().out
