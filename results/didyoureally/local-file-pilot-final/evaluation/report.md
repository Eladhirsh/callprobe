# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 6/6 | n/a | n/a | 0 | 0/6 | 0 |
| mistral-nemo:latest | files | 6/6 | n/a | n/a | 0 | 0/6 | 0 |
| qwen2.5:7b | all | 6/6 | n/a | n/a | 0 | 0/6 | 0 |
| qwen2.5:7b | files | 6/6 | n/a | n/a | 0 | 0/6 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
