# Seven-model extraction comparison

Seven installed local models were measured across email, refunds, files, and scheduling.
These are synthetic English transcripts, not real-world agent accuracy or independent certification.

## Screening: 24 cases per model

| Model | Before exact | After exact | Honest false alarms before | Honest false alarms after | Errors after |
|---|---|---|---|---|---|
| mistral-nemo:latest | 19/24 | 24/24 | 5/12 | 0/12 | 0 |
| qwen2.5:7b | 18/24 | 22/24 | 6/12 | 1/12 | 0 |
| llama3.2:3b | 16/24 | 21/24 | 7/12 | 1/12 | 1 |
| hermes3:8b | 16/24 | 18/24 | 7/12 | 2/12 | 3 |
| llama3.1:8b | 19/24 | 18/24 | 4/12 | 1/12 | 4 |
| phi4-mini:latest | 16/24 | 18/24 | 8/12 | 0/12 | 1 |
| granite3.3:8b | 16/24 | 16/24 | 8/12 | 1/12 | 6 |

The revised profile combines a new extraction contract, tool parameter schemas, and JSON mode.
This is not an ablation study: the results do not isolate the contribution of each change.
Llama3.1 lost exact matches despite fewer false alarms. Errors remain failed checks, not correct answers.
Phi-4 Mini made no honest-case problem accusations but still missed or misclassified several failures.

## Qualification of the selected models

Selection used highest screening exact count, then fewer honest false alarms, fewer errors, and model name.
The selected models were tested on 60 development cases and 24 freshly worded validation cases.
Validation results did not influence model selection or prompt tuning.

| Model | Development exact | Development honest false alarms | Development errors | Fresh validation exact | Fresh honest false alarms | Fresh errors |
|---|---|---|---|---|---|---|
| mistral-nemo:latest | 48/60 | 1/27 | 9 | 20/24 | 0/12 | 4 |
| qwen2.5:7b | 47/60 | 1/27 | 7 | 20/24 | 0/12 | 4 |

### Type-level precision and recall

| Model | Development precision | Development recall | Fresh precision | Fresh recall |
|---|---|---|---|---|
| mistral-nemo:latest | 89.3% | 78.1% | 100.0% | 75.0% |
| qwen2.5:7b | 89.3% | 78.1% | 100.0% | 75.0% |

### Fresh validation by domain

| Model | Email | Refunds | Files | Scheduling |
|---|---|---|---|---|
| mistral-nemo:latest | 6/6 | 6/6 | 2/6 | 6/6 |
| qwen2.5:7b | 6/6 | 6/6 | 2/6 | 6/6 |

## What changed

- Extraction explicitly classifies whether the wording asserts a completed action. The matcher still assigns every verdict.
- Native traces and OpenAI exports preserve tool parameter schemas. Explicit scalar lists can become separate claims; array-valued arguments remain one action.
- Null placeholders and ambiguous parallel lists require repair. They are not silently treated as asserted argument values.
- JSON mode is opt-in. Repair includes the original invalid response, and has a fixed one-retry limit.
- Duplicate JSON keys are rejected instead of silently losing an argument. This was discovered during qualification.
- Raw replies, parsed claims, findings, response usage, model digests, source hashes, and case hashes are retained.

## Remaining limits

The 24-case screen is too simple to establish general reliability. Grouped actions, vague confirmations,
argument inference, and exact source quoting remain harder in the 60-case suite. Some models include
sentence punctuation in filenames. Loosening identifier comparison would hide real mismatches, so that
comparison was not weakened. A quoted claim still does not guarantee its extracted arguments are correct.

Both finalists failed the same four fresh file cases. The replies rewrote the quoted source text
and dropped the meaningful trailing dot from `cache.log.`. Source-quote validation rejected these
replies after repair. These are extraction errors, including one honest case per model, not
four successful abstentions. The other three domains each scored 6/6 per model.

The fresh validation set is a small synthetic check, not independent production data. Use these results
to choose a reviewed pilot, not to justify unattended CI blocking across arbitrary traces.

## Protocol and evidence

- [Five additional baseline models](model-screen-baseline/report.md). The Qwen and Llama3.1 baseline rows reuse the earlier [two-model challenge run](reliability-challenge/report.md).
- [Seven-model updated screen](model-screen-updated/report.md). Prompts and labels were held fixed across these models.
- [Model selection criteria and scores](model-selection.json).
- [Corrected development qualification](model-followup-development/report.md).
- [Fresh validation qualification](model-followup-validation/report.md).
- [Model digests and Ollama version](model-environment.json).

The old screening transcripts and expected labels were preserved; parameter schemas were added.
The first development qualification was interrupted when duplicate JSON keys were discovered. Its partial
evidence is under model-followup-interrupted and is excluded from every completed-run table here.
All 168 screening replies were audited: none had duplicate keys, so that guard does not change the ranking.
Qualification was restarted after the duplicate-key fix. Screening core: aee765e; qualification core: 94b86df.

All rows are single runs at temperature zero. Exact compares verdict and tool counts, not complete semantic equivalence.
Precision and recall compare problem verdict and tool pairs; a wrong problem type can count as both a false positive
and a false negative even when the case was flagged. Honest false alarms count contradicted, phantom, or masked_failure
on honest controls. Unmentioned findings affect exact scoring but are excluded from these problem metrics.
Errors fail exact scoring and expected problems in errored cases count as missed. Unchecked details are reported separately.
The synthetic evaluation sends no real emails, refunds, file operations, or calendar changes.
