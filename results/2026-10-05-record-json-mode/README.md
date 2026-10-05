# Saved JSON mode consistency validation

Before this fix, the comparison gate accepted records whose `json_mode` was
false even though their run metadata declared true. Reproducing that mismatch
returned a passing gate. The comparison now checks every recorded setting
against the run metadata and rejects contradictions or partial coverage with
exit code 2. Boolean types are required, including on extraction-error records.

A run where all older records omit the field remains supported and explicitly
reports `record_json_mode: legacy_unverified` in its evidence. Matching recorded
values report `verified`. These statuses describe saved-configuration consistency,
not actual request bodies, model identity, server behavior, or extraction accuracy.

Offline validation used existing saved model evidence:

- Four current successful records self-compare with exit code 0 and verified settings.
- The earlier 102-record Mistral run self-compares with exit code 0 and legacy unverified settings.
- Copies with contradictory or partly missing settings return exit code 2.
- The previous 36-pair rejected prompt experiment still returns exit code 1.

No model inference or business tools ran for this validation. `summary.json`
contains input and comparison-script hashes, exit codes, and safe diagnostics.
Raw replies stay local. Thirteen new scripted regressions cover both JSON mode
values, invalid types, partial coverage, older records, CLI diagnostics, and
extraction errors. Required checks pass: 1,465 Callprobe tests, 780 tracked
Didyoureally tests, package Ruff checks, and 102 labeled matcher cases. The 48
preserved local duplicate tests also pass and are excluded from tracked totals.
