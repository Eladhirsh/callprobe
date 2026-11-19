from pathlib import Path

import pytest

from callprobe.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "didyoureally" / "openai_masked_failure.json"


def test_audit_checks_a_trace(capsys):
    claims = EXAMPLE.with_name("openai_masked_failure.claims.json")
    assert main(["audit", str(EXAMPLE), "--claims", str(claims)]) == 1
    out = capsys.readouterr().out
    assert "Masked failure 1" in out
    assert "cancel_subscription returned an error" in out


def test_audit_bench_runs_the_bundled_benchmark(capsys):
    assert main(["audit", "bench"]) == 0
    assert "102/102 cases exact" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["audit", "--help"], "usage: callprobe audit "),
        (["audit", "bench", "--help"], "usage: callprobe audit bench "),
    ],
)
def test_audit_help_names_callprobe_commands(argv, usage, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(usage)
    assert "dyr" not in out and "didyoureally" not in out


def test_benchmark_data_ships_inside_the_package():
    from callprobe.didyoureally import bench

    package_dir = Path(bench.__file__).parent
    assert len(list((package_dir / "benchmark").glob("*.json"))) == 102


@pytest.mark.parametrize("case_id", ["honest-send", "wrong-recipient", "failed-success-flag"])
def test_selftest_runs_the_real_audit_subprocess(case_id, tmp_path):
    """The self-test shells out to `python -m callprobe audit`; labeled claims need no network."""
    import runpy

    script = Path(__file__).resolve().parents[1] / "scripts" / "didyoureally" / "selftest_agent.py"
    harness = runpy.run_path(str(script))
    case = next(c for c in harness["scenarios"]() if c["id"] == case_id)
    row = harness["run_cli"](case, tmp_path, "http://127.0.0.1:9/v1", "unused", llm=False)
    assert row["passed"], row
