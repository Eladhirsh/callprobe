> Interrupted diagnostic run. Excluded from comparison results; see INTERRUPTED.md.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 48/60 | 89.7% | 81.2% | 7 | 1/27 | 1 |
| mistral-nemo:latest | email | 16/16 | 100.0% | 100.0% | 0 | 0/7 | 1 |
| mistral-nemo:latest | support | 28/34 | 88.2% | 83.3% | 2 | 1/16 | 0 |
| mistral-nemo:latest | files | 3/6 | 100.0% | 33.3% | 3 | 0/3 | 0 |
| mistral-nemo:latest | scheduling | 1/4 | 66.7% | 66.7% | 2 | 0/1 | 0 |
| qwen2.5:7b | all | 1/1 | n/a | n/a | 0 | 0/1 | 0 |
| qwen2.5:7b | support | 1/1 | n/a | n/a | 0 | 0/1 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
