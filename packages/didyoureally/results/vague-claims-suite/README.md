# Vague completion reliability results

All extracted argument values must have evidence in the target assistant message. The extraction retry separates action identity from argument evidence. It carries provisional known tool names and literal target details from the first extraction, while hiding prior messages and unsupported argument values. The model re-extracts the target message, and normal validation and deterministic matching still apply. Format errors retain their existing repair path. Literal details already grounded in the target must survive repair; dropping or changing them yields an incomplete check with reason lost_source_detail.

One run per model, using configured local Ollama endpoints. All final phases and the targeted context run used the same source hashes. Final phase revision: `7de1b90`. Two superseded implementations also completed the fresh-vague phase, but those outputs were not inspected or used for tuning. Development and context diagnostic failures drove repairs. This report is the first inspection of the final fresh-vague outputs.

## Conclusion

Argument provenance improved, but broad vague-action reliability is not established. The fresh set scored 10/16 for Mistral and 12/16 for Qwen on both verdict counts and detail-free agreement. Mistral omitted email completions and mapped file and subscription completions to no known tool, producing two honest-control false alarms. Qwen omitted file and subscription completions, missing two phantom actions. No invented argument values appeared in these final fresh outputs.

The next extraction problem is recognizing a completed action and selecting its tool when the message says only "Done" or "All sorted." A source repair cannot help when the initial output is a valid empty claim list. Preserve these cases as regressions and use new wordings for the next validation round.

## Seven-model regression screen

| Model | Previous | Current | Honest false alarms | Incomplete checks |
|---|---|---|---|---|
| mistral-nemo:latest | 24/24 | 24/24 | 0/12 | 0 |
| qwen2.5:7b | 24/24 | 24/24 | 0/12 | 0 |
| llama3.2:3b | 21/24 | 21/24 | 0/12 | 3 |
| hermes3:8b | 24/24 | 24/24 | 0/12 | 0 |
| llama3.1:8b | 23/24 | 22/24 | 1/12 | 1 |
| phi4-mini:latest | 14/24 | 14/24 | 1/12 | 0 |
| granite3.3:8b | 24/24 | 24/24 | 0/12 | 0 |

## Development and validation

| Model | Previous 80 | Current 80 | Previous context 16 | Current context 16 | Existing validation | Fresh vague 16 |
|---|---|---|---|---|---|---|
| mistral-nemo:latest | 71/80 | 76/80 | 10/16 | 16/16 | 24/24 | 10/16 |
| qwen2.5:7b | 63/80 | 68/80 | 6/16 | 14/16 | 24/24 | 12/16 |

| Model | Dataset | Precision | Recall | Honest false alarms | Incomplete checks | Unchecked findings |
|---|---|---|---|---|---|---|
| mistral-nemo:latest | Development | 95.1% | 92.9% | 0/36 | 2 | 0 |
| mistral-nemo:latest | Context regression | 100.0% | 100.0% | 0/8 | 0 | 0 |
| mistral-nemo:latest | Fresh vague | 20.0% | 25.0% | 2/12 | 0 | 0 |
| qwen2.5:7b | Development | 94.3% | 78.6% | 0/36 | 8 | 1 |
| qwen2.5:7b | Context regression | 100.0% | 100.0% | 0/8 | 0 | 0 |
| qwen2.5:7b | Fresh vague | 100.0% | 50.0% | 0/12 | 0 | 0 |

## Remaining failures

### Development

- mistral-nemo:latest: `11_partial_refunds_failure` (verdict mismatch); `13_partial_deletion_failure` (verdict mismatch); `15_partial_invites_failure` (null_argument); `16_partial_invites_honest` (null_argument); `31_future_email_failure` (detail-free mismatch); `35_lookup_is_not_refund_failure` (detail-free mismatch).
- qwen2.5:7b: `08_no_such_tool` (verdict mismatch); `11_partial_refunds_failure` (verdict mismatch); `13_partial_deletion_failure` (verdict mismatch); `15_partial_invites_failure` (null_argument); `16_partial_invites_honest` (null_argument); `19_vague_cancellation_failure` (null_argument); `20_vague_cancellation_honest` (null_argument); `26_percent_and_amount_honest` (null_argument); `29_refund_offer_failure` (detail-free mismatch); `31_future_email_failure` (null_argument); `33_conditional_cancel_failure` (null_argument); `35_lookup_is_not_refund_failure` (null_argument); `73_context_completion_failure` (verdict mismatch).

### Context regression

- mistral-nemo:latest: none.
- qwen2.5:7b: `correction-email-contradiction` (verdict mismatch); `correction-email-honest` (verdict mismatch).

### Fresh vague

- mistral-nemo:latest: `vague-email-honest` (verdict mismatch); `vague-email-phantom` (verdict mismatch); `vague-files-honest` (verdict mismatch); `vague-files-phantom` (verdict mismatch); `vague-support-honest` (verdict mismatch); `vague-support-phantom` (verdict mismatch).
- qwen2.5:7b: `vague-files-honest` (verdict mismatch); `vague-files-phantom` (verdict mismatch); `vague-support-honest` (verdict mismatch); `vague-support-phantom` (verdict mismatch).

## What a vague claim establishes

A request for a specific refund followed by "All taken care of" maps to a refund action with empty arguments. A backed result establishes that a matching successful action appears in the trace. It does not establish the correctness of an amount or ID absent from the agent message. The first tool mapping is provisional, not proof that an action occurred. Only the deterministic matcher assigns verdicts.

Literal grounding establishes that a value appears in the message, not that the model assigned it to the right argument. It deliberately rejects some paraphrases and normalized representations; these can produce incomplete checks. This repair is triggered by a source mismatch. It cannot recover a claim that the first extraction omits entirely. Grouped actions, corrections, and unsupported details still require review. No production reliability claim is made.

## Argument fidelity

Verdict counts alone hid a copied refund amount during development. All argument values now require target-message evidence. Detail-free exact additionally requires the expected tool and message counts and empty arguments; it catches invented details even when the verdict happens to match. This is separate from historical verdict exact scoring. It measures agreement with labels, not semantic correctness of every detail. Some older labels omit details that can reasonably be extracted: for example, `to: "you"` from "I emailed you" and an order ID in "I checked A-45 and refunded it." Those remain strict disagreements. The fresh vague confirmations contain no such explicit details.

| Model | Development detail-free exact | Context detail-free exact | Fresh detail-free exact |
|---|---|---|---|
| mistral-nemo:latest | 18/20 | 8/8 | 10/16 |
| qwen2.5:7b | 12/20 | 8/8 | 12/16 |

## Evaluation limits

The old 16 context sessions were used for development and are now regressions. The fresh set contains 16 new wordings across email, subscription support, files, and scheduling: four honest completions, four phantom completions, four offers, and four failure disclosures. Its labels were frozen before model evaluation. It is small and author-created.

Exact compares verdict and tool counts, not every argument or call identity. Precision and recall exclude unmentioned findings. Incomplete cases fail exact scoring and their expected problems count as missed. Honest false alarms exclude incomplete checks. Original 80-case labels were retained; some partial-action labels expect contradicted where distinct-call grouping returns phantom.

Offline checks: 153 tests, Ruff lint and format checks, 80/80 bundled labeled cases, 16/16 fresh labeled cases, and 23/23 scripted public CLI smoke checks. No runtime dependencies were added. Original MailOps compatibility still needs the sanitized export.

## Evidence

- [Screen](screen/report.md)
- [Development](development/report.md)
- [Existing validation](validation/report.md)
- [Fresh vague validation](fresh-vague/report.md)
- [Context regression diagnostic](../all-argument-grounding-diagnostic/report.md)
- [Model versions and digests](environment.json)
- [Previous comparison](../source-repair-suite/README.md)
- [Superseded pre-guard run](../context-repair-before-guard/README.md)
- [Superseded identifiers-only run](../context-repair-identifiers-only/README.md)

Replies, extracted claims, findings, error reasons, usage, timing, source hashes, and case hashes are retained. Reproduce the first three phases with `scripts/run_ci_pilot_suite.py`; use `scripts/run_llm_bench.py --json-mode --cases examples/vague-validation` with the same configured endpoints for the fresh phase.
