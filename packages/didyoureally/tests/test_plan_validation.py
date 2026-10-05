import json
import runpy
from pathlib import Path

import pytest

from didyoureally import bench


@pytest.mark.parametrize("domain", ["email", "files", "support", "scheduling"])
def test_frozen_plan_controls_keep_completions_and_plans_distinct(domain):
    source = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "build_plan_validation.py"))
    cases = [case for case in source["cases"]() if case["domain"] == domain]
    assert len(cases) == 4
    assert sum(not case["claims"] for case in cases) == 1
    assert sum(case["expected"] == [] for case in cases) == 1
    assert sum(any(e["verdict"] == "phantom" for e in case["expected"]) for case in cases) == 1
    for case in cases:
        assert bench.run_case(case, None).passed
        assert json.loads((source["OUT"] / f"{case['id']}.json").read_text()) == case
