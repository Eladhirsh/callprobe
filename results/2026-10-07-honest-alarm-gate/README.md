# Honest-control alarm gate validation

The optional `--fail-on-new-honest-alarms` check rejects a newly observed alarm
even when the baseline and candidate were both nonexact. Default comparison
behavior is unchanged. Reports always include the additional diagnostics.

## Concrete failure

The [completed-tool mapping experiment](https://github.com/Eladhirsh/callprobe/blob/bea616fe4da0a74f4c42033514e241fc9a65da7d/results/2026-10-07-completed-tool-mapping/README.md)
passed its focused regression gate even though Qwen's `94_json_plan_honest`
changed from an extraction error to two phantom-email findings. The case expects
no findings. Neither run matched its labels, so the existing exact-to-nonexact
regression check did not catch the transition. The candidate no longer had an
extraction error, which also removed that reason to fail the gate.

An extraction error is inconclusive. It is not evidence of a clean baseline.
The new report marks this distinction with `baseline_extraction_error: true`.
The optional check rejects the candidate's observed false alarm without claiming
that the baseline had verified the trace correctly.

## Offline results

We reran the comparison CLI over the frozen baseline and candidate recordings.
This made no model calls and did not change the earlier experiment reports.

| Suite | Paired attempts | Default exit | Strict exit | Newly observed alarm cases | After baseline extraction errors |
|---|---|---|---|---|---|
| Focused | 36 | 0 | 1 | 1 | 1 |
| Broad | 284 | 1 | 1 | 10 | 5 |

The focused strict comparison now rejects Qwen's honest JSON-plan case. The
broad comparison already failed on individual regressions and candidate errors;
its additional diagnostics identify five alarms after completed baseline
observations without alarms and five after incomplete baseline extractions.
An attempt is counted once even if it contains multiple problem findings.

The diagnostic includes `unmentioned` findings as well as phantom, contradicted,
and masked-failure findings. It applies only to controls labeled entirely
`backed` or with no expected findings. Existing alarms do not by themselves
trigger the new check, and candidate extraction errors remain unconditional
gate failures. Failure-labeled controls remain covered by the original gate.

## Evidence and limits

- `focused-default.json`, `focused-strict.json`, `broad-default.json`, and
  `broad-strict.json` are the CLI reports, including source-record hashes and
  sanitized attempt identities.
- `validation.json` records the comparison script hash, exit codes, coverage,
  and diagnostic counts.
- An independent scan of the saved records produced the same alarm identities.
  Every preexisting default report field except explanatory `scope` text matches
  the frozen experiment report exactly.

These are reused synthetic development controls. The check does not establish
argument accuracy, model stability, or production integration quality. It does
not detect all possible changes among nonexact outcomes. No raw model replies,
claim arguments, or provider error text are exported here. The rejected mapping
candidate remains disabled.
