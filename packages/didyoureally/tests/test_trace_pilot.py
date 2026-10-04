import json
import runpy
from pathlib import Path

import pytest

PREPARE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_trace_pilot.py"))["prepare"]


def test_pilot_retains_original_export_and_separate_labels(tmp_path):
    trace = {"messages": [{"role": "assistant", "content": "Sent!"}]}
    (tmp_path / "trace.json").write_text(json.dumps(trace))
    (tmp_path / "claims.json").write_text("[]")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "sanitized": True,
                "cases": [
                    {
                        "id": "mail",
                        "application": "mail-app",
                        "domain": "email",
                        "trace": "trace.json",
                        "claims": "claims.json",
                        "expected": [],
                    }
                ],
            }
        )
    )
    PREPARE(manifest, tmp_path / "prepared")
    prepared = json.loads((tmp_path / "prepared/mail.json").read_text())
    assert prepared["trace"] == trace
    assert prepared["domain"] == "email"


def test_pilot_requires_explicit_sanitization_declaration(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"cases": [{}]}')
    with pytest.raises(ValueError, match="sanitized"):
        PREPARE(manifest, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


def test_frozen_pilot_validation_has_balanced_labeled_controls():
    from didyoureally import bench

    folder = Path(__file__).resolve().parents[1] / "examples/ci-pilot-validation"
    result = bench.run(folder)
    assert len(result.cases) == result.passed == 24
    cases = [json.loads(p.read_text()) for p in folder.glob("*.json")]
    assert sum(all(e["verdict"] == "backed" for e in c["expected"]) for c in cases) == 12
