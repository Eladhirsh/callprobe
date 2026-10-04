# Explicit timestamp extraction reliability

This focused check re-extracts the saved scheduling-create-success replies from
Qwen2.5, Llama3.1, and Hermes in the cross-domain matrix. It uses the configured
local `mistral-nemo:latest` extractor in both default and staged modes, with JSON
mode and temperature zero. These are six fresh extractions of three existing
agent replies, not six new agent executions or a detector accuracy estimate.

All six final checks retained `starts_at`, backed the original honest event,
and contradicted a synthetic copy whose recorded date was changed from November
9 to November 10. The same freshly extracted claims were used for both matching
checks. No application tools ran. The three historical first extraction responses
also retain their full ISO date under the new source-validation rules. Existing
saved claims are not rewritten.

An earlier implementation handled full ISO values but exposed another repair
path: the Hermes staged extraction shortened the date and subsequently omitted
it. Only five of six checks retained the date in that iteration. The final guard
preserves a single full source timestamp when repairing an already identified
timestamp field. A repair that still omits it is incomplete, not a clean account.
This path has scripted regression tests for both extraction modes and an honest
control that keeps the full timestamp.

Validation on the final implementation:

- 1,449 Callprobe tests and 321 Didyoureally tests pass.
- Package Ruff checks and formatting pass.
- All 90 labeled matcher cases pass, including the new wrong-date and honest pair.
- All 100 archived agent episodes replay with unchanged decisions and findings.
- All six targeted fresh extractions retain the date and distinguish the wrong-date copy.

[Summary](summary.json) contains extractor identity, source hashes, timestamps,
and per-case results. Raw extraction requests and responses remain local. The
original cross-domain reports and counterfactual diagnostic remain frozen.

The fix does not guarantee that every detail was extracted. A date omitted on
the first attempt has no proposed timestamp field to repair. Multiple possible
source timestamps are not assigned to fields automatically. Relative dates,
missing zones or years, locale-dependent numeric dates, and fractional seconds
remain outside the new normalization. See the package README for supported fields.
