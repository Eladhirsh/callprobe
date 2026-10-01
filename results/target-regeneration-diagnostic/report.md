# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 10/15 | 100.0% | 62.5% | 5 | 0/7 | 1 |
| mistral-nemo:latest | email | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | files | 0/2 | n/a | 0.0% | 2 | 0/1 | 0 |
| mistral-nemo:latest | scheduling | 2/5 | 100.0% | 33.3% | 3 | 0/2 | 1 |
| qwen2.5:7b | all | 8/15 | 100.0% | 37.5% | 7 | 0/7 | 1 |
| qwen2.5:7b | email | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 |
| qwen2.5:7b | support | 4/6 | 100.0% | 33.3% | 2 | 0/3 | 0 |
| qwen2.5:7b | files | 0/2 | n/a | 0.0% | 2 | 0/1 | 0 |
| qwen2.5:7b | scheduling | 2/5 | 100.0% | 33.3% | 3 | 0/2 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
