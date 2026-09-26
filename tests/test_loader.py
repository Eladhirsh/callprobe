"""Reject ambiguous tool contracts before any model request."""

import pytest
import yaml

from callprobe.loader import load_suite


TOOL = {"name": "lookup", "description": "Lookup", "parameters": {"type": "object"}}


@pytest.mark.parametrize("duplicate_in", ["bundle", "distractors"])
def test_duplicate_tool_names_are_rejected(tmp_path, duplicate_in):
    bundle_tools = [TOOL, TOOL] if duplicate_in == "bundle" else [TOOL]
    distractors = [TOOL, TOOL] if duplicate_in == "distractors" else []
    (tmp_path / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"support": bundle_tools}}))
    (tmp_path / "distractors.yaml").write_text(yaml.safe_dump({"tools": distractors}))
    with pytest.raises(ValueError, match="duplicate tool name: lookup"):
        load_suite(tmp_path)


def test_tool_names_may_repeat_across_separate_bundles_and_distractor_pool(tmp_path):
    (tmp_path / "tools.yaml").write_text(yaml.safe_dump({"bundles": {"a": [TOOL], "b": [TOOL]}}))
    (tmp_path / "distractors.yaml").write_text(yaml.safe_dump({"tools": [TOOL]}))
    suite = load_suite(tmp_path)
    assert len(suite.bundles) == 2
    assert len(suite.distractors) == 1
