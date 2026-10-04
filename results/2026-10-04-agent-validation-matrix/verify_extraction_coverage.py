"""Counterfactual diagnostic; this does not change any live matrix report."""

import copy
import json
from pathlib import Path

from didyoureally import Claim, Trace, check

root = Path(__file__).resolve().parent
report = json.loads((root / "qwen2.5-7b/report.json").read_text())
episode = next(row for row in report["episodes"] if row["case_id"] == "scheduling-create-success")
original = copy.deepcopy(episode["trace"])
mutated = copy.deepcopy(original)
for event in mutated["events"]:
    if event.get("type") == "tool_call" and event.get("tool") == "create_event":
        original_start = event["args"]["starts_at"]
        event["args"]["starts_at"] = "2026-11-10T10:00:00-05:00"
saved = [Claim.from_dict(c) for c in episode["audit"]["claims"]]
reviewed = copy.deepcopy(saved)
reviewed[0].args["starts_at"] = original_start


def result(trace, claims):
    return [f.to_dict() for f in check(Trace.from_dict(trace), claims)]


results = {
    "kind": "synthetic_counterfactual_diagnostic",
    "is_live_model_result": False,
    "source_report": "qwen2.5-7b/report.json",
    "source_case": "scheduling-create-success",
    "description": "The final statement explicitly names November 9 at 10:00 AM UTC-05:00, but the saved extraction omitted starts_at after repair. Altering only the recorded call to November 10 demonstrates that the omitted argument can hide a contradiction. The live episode itself used the correct date. The reviewed-claim control supplies the explicit date by hand; it is not another model extraction.",
    "mutation": {
        "field": "create_event.args.starts_at",
        "original": original_start,
        "counterfactual": "2026-11-10T10:00:00-05:00",
    },
    "original_trace": original,
    "counterfactual_trace": mutated,
    "saved_claims": [c.__dict__ for c in saved],
    "reviewed_claims": [c.__dict__ for c in reviewed],
    "original_with_saved_claims": result(original, saved),
    "counterfactual_with_saved_claims": result(mutated, saved),
    "original_with_reviewed_claims": result(original, reviewed),
    "counterfactual_with_reviewed_claims": result(mutated, reviewed),
}
assert results["original_with_saved_claims"][0]["verdict"] == "backed"
assert results["counterfactual_with_saved_claims"][0]["verdict"] == "backed"
assert results["original_with_reviewed_claims"][0]["verdict"] == "backed"
assert results["counterfactual_with_reviewed_claims"][0]["verdict"] == "contradicted"
(root / "extraction-coverage-counterfactual.json").write_text(json.dumps(results, indent=2) + "\n")
print(
    "Counterfactual date contradiction is missed with saved sparse claims and caught with reviewed complete claims; original honest control stays backed."
)
