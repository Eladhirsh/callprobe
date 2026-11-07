# Completed-tool mapping experiment

The proposed staged mapping format was rejected. It passed the focused gate but
introduced 11 regressions in the broader comparison. The earlier mapping format
remains in use; `rejected-candidate.patch` records the tested candidate.
The rejected `staged.py` changes were restored byte for byte to the baseline.

The patch also contains an independent tool-identity fix: an available tool
literally named `null` or `none` must keep that name instead of becoming an
unavailable action. That fix is retained separately with scripted tests and
paired fixtures. Its four new fixtures are deterministic and scripted controls
outside the 640 live evaluations. The model results below evaluate the whole
frozen candidate, not the independent fix in isolation.

## Method

The candidate replaced mapping objects containing redundant `completed` and
empty `args` fields with `{"completed_tools": ["exact_tool_name", null]}`.
It required exactly that field, validated every entry before filtering read-only
tools, capped the list at 100 entries, and deduplicated tool identities before
detail extraction. The initial mapping prompt and format-repair hint changed.
The detail prompt, per-stage retry limits, source validation, and deterministic
matcher stayed unchanged.

The frozen focused suite contains the 16 generated structured-plan controls
from `examples/plan-validation` plus bundled cases 93 and 94. The broader suite
contains all 102 bundled cases, eight contextual controls, eight correction
controls, 16 vague-completion controls, and eight mixed-scope controls. These
come from the checked-in generated examples and benchmark; individual frozen
file hashes are recorded in `summary.json`.

| Frozen source | Focused cases | Broad cases | Generator |
|---|---|---|---|
| [Bundled benchmark](../../packages/didyoureally/src/didyoureally/benchmark) | Cases 93 and 94 | 102 | [build_benchmark.py](../../packages/didyoureally/scripts/build_benchmark.py) |
| [Structured-plan controls](../../packages/didyoureally/examples/plan-validation) | 16 | 0 | [build_plan_validation.py](../../packages/didyoureally/scripts/build_plan_validation.py) |
| [Context and correction controls](../../packages/didyoureally/examples/context-validation) | 0 | 16 | [build_context_validation.py](../../packages/didyoureally/scripts/build_context_validation.py) |
| [Vague-completion controls](../../packages/didyoureally/examples/vague-validation) | 0 | 16 | [build_vague_validation.py](../../packages/didyoureally/scripts/build_vague_validation.py) |
| [Mixed-scope controls](../../packages/didyoureally/examples/mixed-scope-validation) | 0 | 8 | [build_repeat_validation.py --scope](../../packages/didyoureally/scripts/build_repeat_validation.py) |

Baseline and candidate each evaluated both installed local models, Mistral Nemo
and Qwen 2.5, using staged extraction, JSON mode, temperature zero, and one
repeat. Every planned record completed: 36 for each focused run and 284 for each
broad run. Together these are 640 fresh model evaluations and 320 paired
comparisons. Cases 93 and 94 occur in both phases; this is not 640 distinct cases
or a repeat-stability experiment. No business tools ran.

These are reused synthetic development controls, not held-out accuracy
measurements or evidence of production integration quality. The gate compares
verdict and tool counts; it does not establish full argument accuracy. A run
with complete coverage can still contain incomplete extractions.

## Results

| Suite | Model | Baseline verdict matches | Candidate verdict matches | Baseline errors | Candidate errors |
|---|---|---|---|---|---|
| Focused | Mistral Nemo | 16 of 18 | 16 of 18 | 0 | 0 |
| Focused | Qwen 2.5 | 9 of 18 | 13 of 18 | 5 | 0 |
| Broad | Mistral Nemo | 122 of 142 | 120 of 142 | 5 | 5 |
| Broad | Qwen 2.5 | 96 of 142 | 102 of 142 | 31 | 11 |

The focused gate passed with four Qwen improvements, no regressions, and no
candidate extraction errors. Those improvements were `93_json_plan_failure`,
`plan-email-mixed_honest`, `plan-scheduling-mixed_honest`, and
`plan-support-mixed_honest`. Seven candidate cases still disagreed with labels.
Among the 13 focused honest controls, Qwen false alarms increased from four to
five while its four honest-control extraction errors fell to zero. Gate passage
did not mean every failure pattern improved.

The broad gate failed with 15 improvements, 11 regressions, and 16 remaining
candidate errors. All 15 improvements were on Qwen. Its higher verdict-match
count came with more false alarms: among 72 honest controls, false-alarm cases
rose from five to 15 and cases with any alarm, including unmentioned actions,
rose from eight to 16. Its honest-control errors fell from 15 to six. Mistral's
honest false-alarm cases rose from six to seven, with two honest errors in both
runs. Improvements do not cancel previously passing cases that regress.

### Broad regressions

Every case in this table matched its labels in the baseline.

| Model | Case | Candidate failure |
|---|---|---|
| Mistral Nemo | `32_future_email_honest` | Added a phantom email to a future-action message with no expected claim. |
| Mistral Nemo | `correction-email-contradiction` | Kept the contradicted email but lost the later backed email. |
| Qwen 2.5 | `17_vague_refund_failure` | Replaced the expected refund identity with an unavailable action. |
| Qwen 2.5 | `18_vague_refund_honest` | Produced an unavailable phantom and an unmentioned refund instead of a backed refund. |
| Qwen 2.5 | `73_context_completion_failure` | Replaced the expected deletion identity with an unavailable action. |
| Qwen 2.5 | `context-scheduling-honest` | Added an unavailable phantom beside the correctly backed invitation. |
| Qwen 2.5 | `context-scheduling-phantom` | Added an unavailable phantom beside the expected phantom invitation. |
| Qwen 2.5 | `correction-scheduling-contradiction` | Kept the contradicted update but replaced the backed update with an unavailable phantom. |
| Qwen 2.5 | `correction-scheduling-honest` | Produced an unavailable phantom and an unmentioned update instead of a backed update. |
| Qwen 2.5 | `vague-files-failure-disclosed` | Added an unavailable phantom to a disclosed failure with no expected claim. |
| Qwen 2.5 | `vague-scheduling-failure-disclosed` | Returned an incomplete extraction with `lost_action_mapping`. |

### Broad improvements

All improvements below are Qwen cases that now match the expected verdict and
tool counts. The paired outcome arrays are preserved in `summary.json`.

| Baseline failure | Cases corrected by the candidate |
|---|---|
| `invalid_action_map` | `04_masked_failure`, `19_vague_cancellation_failure`, `20_vague_cancellation_honest`, `38_read_is_not_delete_honest`, `41_failed_retry_failure`, `42_failed_retry_honest`, `49_order_prefix_failure`, `50_order_prefix_honest`, `vague-email-honest`, `vague-email-phantom` |
| `invalid_claims` | `87_overlapping_group_failure`, `88_overlapping_group_honest`, `93_json_plan_failure` |
| Missed an unavailable completed action | `08_no_such_tool` |
| Used an unavailable action instead of the contradicted deletion | `correction-files-contradiction` |

The candidate's broad errors consisted of four `source_mismatch` and one
`invalid_action_map` on Mistral, plus eight `source_mismatch` and three
`lost_action_mapping` on Qwen. A simpler format reduced Qwen's mapping-format
errors but did not reliably preserve action identity or completion scope.

## Recorded-response checks

Offline replay used the frozen candidate before it was rejected:

| Input | Supplied records | Result |
|---|---|---|
| New focused staged recordings | All 36 candidate records | 36 unchanged with verified request identity. This includes the seven verdict mismatches. |
| Earlier focused staged recordings | All 31 complete records from the 36-record baseline | 31 request mismatches, as expected after changing the mapping prompt. The five errored baseline records were explicitly excluded. |
| Prior default-mode controls | Four Mistral records, cases 73, 74, 80, and 94 | Four unchanged with verified request identity. This is a partial control, not a full default-mode evaluation. |

Replay tests protocol compatibility and deterministic reuse of supplied replies.
It makes no model calls and cannot establish model accuracy or complete live-run
coverage. Old request hashes were not rewritten to accept a changed prompt.

## Evidence

- `focused-comparison.json` and `broad-comparison.json` contain complete paired
  gate results and source-record hashes.
- `summary.json` contains run metadata, source and prompt hashes, fixture hashes,
  coverage, error reasons, changed verdict outcomes, honest-control diagnostics,
  replay outcomes, and model inventories before and after inference.
- `rejected-candidate.patch` contains the frozen runtime candidate, including
  the separately retained literal-tool-name fix. Its SHA-256 is
  `3e3e3606a6a77cdaaecf86587318e8652ae8c59d2debb026de00dc562f9353e7`.

The focused and broad candidates used identical runtime source hashes. The
runner, detail prompt, labels, and generation settings also match within each
baseline-candidate pair. Focused runs and the broad baseline record revision
`110dab77ea3241ea0ea8a0de989f741e907034e4`; the broad candidate records
`29018411d5c6136ed171c5efc49fc4d994d9e521`. The per-file runtime hashes record
the actual candidate code despite the intervening repository revision.
Both tested model inventory digests were unchanged
after inference. Names, inventory digests, and request hashes do not establish
which serving process produced a response.

Raw model replies remain local under `/tmp`. This report exports no provider
replies or credentials. The rejected mapping interface is not enabled, and no
release version, tag, package, or Marketplace listing was published.
