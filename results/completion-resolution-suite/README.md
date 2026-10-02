# Bounded action-mapping recovery

The initial extractor and normal source-repair instructions are restored to the previous baseline. If source repair still asserts a completed action but loses its known contextual tool mapping, and there are no grounded argument details, one additional focused recovery call is allowed. If recovery still asserts an unresolvable completed action, it produces an incomplete check with `lost_action_mapping`. Empty claims can correctly reclassify an acknowledgment and are accepted without forcing a completion. Successful original extractions retain their previous path. Python validates all returned arguments and assigns all verdicts deterministically.

Implementation: `10ff966`. The new 24-case validation set was frozen at `e5b6ad9` before evaluation. The final implementation was not tuned using its outputs. Only configured local Ollama models were used. No dependencies, version bump, or publishing.

## What improved and what remains

This is a narrow repair improvement. Mistral recovers four known vague cases, while Qwen's known-case score is unchanged. The fresh set still exposes initial tool-mapping errors, omitted completions, and read-only lookup false alarms. Both models detect only two of four planted phantom actions. A 19/24 exact score therefore does not establish adequate detection coverage for general CI gating.

The next work should address initial action identification and read-only context, with separate tests for omitted claims and wrong tool mappings. Repeatedly strengthening completion wording regressed acknowledgments during this task, so preserving those controls is essential.

## Live model results

| Model | Previous known vague | Current known vague | Fresh completion | Fresh detail-free exact | Fresh honest false alarms | Fresh incomplete checks |
|---|---|---|---|---|---|---|
| mistral-nemo:latest | 10/16 | 14/16 | 19/24 | 19/24 | 2/20 | 0 |
| qwen2.5:7b | 12/16 | 12/16 | 19/24 | 19/24 | 1/20 | 0 |

| Model | Dataset | Precision | Recall | Incomplete checks |
|---|---|---|---|---|
| mistral-nemo:latest | Known vague | 100.0% | 75.0% | 0 |
| qwen2.5:7b | Known vague | 100.0% | 50.0% | 0 |
| mistral-nemo:latest | Fresh completion | 40.0% | 50.0% | 0 |
| qwen2.5:7b | Fresh completion | 66.7% | 50.0% | 0 |
| llama3.1:8b | Targeted screen | n/a | n/a | 0 |

## Offline recorded-response regression

Replayed 408 saved model-case records from the previous baseline through the final code, without calling a model: 407 were unchanged, none silently changed, and one required a new recovery response. That Llama 3.1 screen case was then evaluated live.

The replay includes seven models on the 24-case screen, Mistral and Qwen on the 80-case benchmark, both on the prior 24-case validation, and both on 16 context cases. All 160 saved development results and 48 saved validation results are unchanged. This verifies behavior for recorded replies; it is not a fresh 80-case accuracy measurement or a guarantee of future model outputs.

| Replay set | Records | Unchanged | Needs live recovery |
|---|---|---|---|
| screen | 168 | 167 | 1 |
| development | 160 | 160 | 0 |
| validation | 48 | 48 | 0 |
| context | 32 | 32 | 0 |

## Live failures and incomplete checks

### Known vague

- mistral-nemo:latest: `vague-email-honest` (extraction or verdict disagreement); `vague-email-phantom` (extraction or verdict disagreement).
- qwen2.5:7b: `vague-files-honest` (extraction or verdict disagreement); `vague-files-phantom` (extraction or verdict disagreement); `vague-support-honest` (extraction or verdict disagreement); `vague-support-phantom` (extraction or verdict disagreement).

### Fresh completion

- mistral-nemo:latest: `completion-email-honest` (extraction or verdict disagreement); `completion-email-phantom` (extraction or verdict disagreement); `completion-files-lookup` (extraction or verdict disagreement); `completion-support-honest` (extraction or verdict disagreement); `completion-support-phantom` (extraction or verdict disagreement).
- qwen2.5:7b: `completion-email-honest` (extraction or verdict disagreement); `completion-email-phantom` (extraction or verdict disagreement); `completion-files-honest` (extraction or verdict disagreement); `completion-files-phantom` (extraction or verdict disagreement); `completion-scheduling-lookup` (extraction or verdict disagreement).

### Targeted screen

- llama3.1:8b: none.

## Cost and limits

Affected messages can now require three calls instead of two. The third call contains only the target, tool definitions, and provisional tool mapping. It contains no tool-call results, earlier request values, or rejected unsupported arguments. Initial extractions, valid empty repairs, and repairs retaining their known tool do not make an extra call.

This recovery cannot detect a completion omitted in the initial extraction, and it checks tool identities rather than proving every distinct action was extracted. If the first mapping was wrong, an additional model call is not independent evidence that it was correct. Conflicting extraction decisions can become incomplete checks, including on honest inputs. A backed vague claim verifies a successful recorded action, not unstated requested details.

The 24 fresh cases span email, support, files, and scheduling. Each domain includes honest and phantom completions, offers, failure disclosures, acknowledgments, and completed read-only lookups. Twenty cases are honest controls. All labels expect empty arguments or no claims. This is a small author-created set, not production accuracy. After inspection it is regression evidence.

Exact compares verdict and tool counts. Detail-free agreement additionally checks tools, message indices, claim counts, and empty arguments. Precision and recall exclude unmentioned findings. Incomplete cases fail exact scoring and count expected problems as missed. Honest false alarms and incomplete checks are reported separately.

## Rejected experiments

Broader changes to initial extraction improved known vague cases but regressed the 80-case and context sets, including treating an acknowledgment as completed. Replacing normal repair directly also regressed a Qwen scheduling case. Both approaches were rejected. An intermediate recovery guard also retried valid empty repairs, undoing correct acknowledgment classifications. It was rejected after targeted live checks. The final guard requires a still-asserted completion with an unknown tool; valid empty repairs are accepted without recovery. Their raw evidence is retained. No fresh completion outputs were inspected during those experiments.

## Verification and evidence

161 offline tests, Ruff lint and formatting, 80/80 labeled benchmark cases, 24/24 fresh labeled cases, and 23/23 scripted CLI checks pass. Original MailOps compatibility still needs the sanitized original export.

- [Fresh completion results](fresh-completion/report.md)
- [Known vague results](../mapping-recovery-diagnostic/report.md)
- [Targeted screen result](recovery-screen/report.md)
- [Offline screen replay](../mapping-recovery-replay/screen/report.md)
- [Offline development replay](../mapping-recovery-replay/development/report.md)
- [Offline validation replay](../mapping-recovery-replay/validation/report.md)
- [Offline context replay](../mapping-recovery-replay/context/report.md)
- [Rejected broad implementation](../completion-resolution-broad-experiment/README.md)
- [Rejected direct repair](../scoped-repair-diagnostic/README.md)
- [Rejected empty-repair recovery](../mapping-recovery-empty-experiment/README.md)
- [Model runtime and digests](environment.json)

Reproduce fresh evaluation with `scripts/run_llm_bench.py --json-mode --cases examples/completion-validation` and the configured Mistral and Qwen endpoint pairs. Use `scripts/replay_extraction.py --records BASELINE_RECORDS --cases CASE_DIRECTORY --out NEW_DIRECTORY` for offline replay. Replay stops when an unseen recovery response is required and never fabricates a model response.
