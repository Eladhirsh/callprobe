Latest: [Source-specific repair reliability comparison](source-repair-suite/README.md).

Previous: [Complex-session reliability comparison](complex-session-suite/README.md).

Previous: [CI pilot reliability results](ci-pilot-suite/README.md).

Earlier: [seven-model comparison](model-comparison.md). The report below preserves the earlier experiment.

# Reliability evaluation, September 30, 2026

Two locally installed models were evaluated through Ollama 0.34.2. No external API was used.
Qwen model ID: `845dbda0ea48`. Llama model ID: `46e0c10c039e`. Temperature: 0.
Each table represents one run per model and case. These are synthetic fixtures, not production accuracy.

| Model | Development exact, before | Development exact, after | Challenge exact |
|---|---|---|---|
| qwen2.5:7b | 30/60 | 46/60 | 18/24 |
| llama3.1:8b | 49/60 | 52/60 | 19/24 |

## Problem detection on the development set

| Model | Precision before | Precision after | Recall before | Recall after |
|---|---|---|---|---|
| qwen2.5:7b | 42.9% | 75.6% | 56.2% | 96.9% |
| llama3.1:8b | 83.8% | 81.1% | 96.9% | 93.8% |

Exact-case agreement improved for both models, but Llama problem precision and recall regressed.
The change should not be described as an across-the-board accuracy improvement.

## Separate challenge by domain

| Domain | Qwen exact | Llama exact |
|---|---|---|
| email | 4/6 | 6/6 |
| support | 6/6 | 5/6 |
| files | 4/6 | 4/6 |
| scheduling | 4/6 | 4/6 |

The challenge contains 12 honest controls. Qwen falsely flagged 6; Llama falsely flagged 4.
All 48 challenge evaluations returned a result without an input or provider error.
No prompt or matcher changes were made in response to challenge results.

## What changed

- Each assistant message is extracted separately; later messages are excluded from its context.
- The application attaches the message index, and every extracted claim must quote that message.
- Invalid output gets one bounded repair attempt, then an explicit error. Unknown tool names do not silently become phantom actions.
- Read-only claims are excluded by tool metadata. Equivalent clock times and separate currency arguments are compared deterministically.
- Reports retain raw replies, parsed claims, findings, errors and unchecked details. Duplicate benchmark IDs fail validation.

## Remaining failures

- Both models can turn offers or honest failure disclosures into completed-action claims.
- Grouped actions and scheduling tool selection remain weak. Both models scored 0/4 on the original scheduling cases.
- Models sometimes invent missing argument values or nulls. A quoted claim can still have incorrectly extracted arguments.
- Llama extracted `notes-final.md.` with sentence punctuation as part of the filename, causing a false contradiction.
- Some matching details remain unchecked. Even an exact case score does not guarantee all claim details were verified.

This evidence does not justify unattended CI blocking with these models. Use findings for reviewed diagnostics while extraction improves.

## Evidence and scoring

- [Initial baseline](reliability-baseline/report.md): core implementation `77aedbf`.
- [Intermediate iteration](reliability-updated/report.md): retained for transparency; an uncommitted development snapshot.
- [Final development run](reliability-final/report.md): core implementation `9d2bdfe`.
- [Separate challenge run](reliability-challenge/report.md): same frozen core implementation.

Each directory includes `records.jsonl` with diagnostic evidence and `metadata.json` with prompt and case hashes.
Exact matches compare verdict and tool counts. Precision and recall use contradicted, phantom and masked failure only.
Unmentioned findings affect exact scores but are excluded from problem precision and recall.
Errors fail exact scoring and expected problems in errored cases count as missed.
Honest false alarms count problem verdicts, with errors reported separately. Cases may have unchecked details.
The 60-case suite was used for development. The 24-case challenge was authored before its run and has balanced controls,
but neither set is an independent real-world evaluation. No statistical confidence or repeatability claim is made.
