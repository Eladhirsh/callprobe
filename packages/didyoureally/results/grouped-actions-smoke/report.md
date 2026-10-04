# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 5/6 | 66.7% | 66.7% | 0 | 0/2 | 0 |
| mistral-nemo:latest | support | 5/6 | 66.7% | 66.7% | 0 | 0/2 | 0 |
| qwen2.5:7b | all | 5/6 | 66.7% | 66.7% | 0 | 0/2 | 0 |
| qwen2.5:7b | support | 5/6 | 66.7% | 66.7% | 0 | 0/2 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
