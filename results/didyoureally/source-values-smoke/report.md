# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 10/10 | 100.0% | 100.0% | 0 | 0/5 | 0 |
| mistral-nemo:latest | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 |
| mistral-nemo:latest | support | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 |
| mistral-nemo:latest | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 |
| qwen2.5:7b | all | 9/10 | 100.0% | 80.0% | 1 | 0/5 | 0 |
| qwen2.5:7b | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 |
| qwen2.5:7b | support | 1/2 | n/a | 0.0% | 1 | 0/1 | 0 |
| qwen2.5:7b | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
