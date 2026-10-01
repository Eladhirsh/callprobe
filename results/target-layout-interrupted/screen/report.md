# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 |
| mistral-nemo:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | all | 20/24 | 100.0% | 75.0% | 4 | 0/12 | 0 |
| qwen2.5:7b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | scheduling | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 |
| llama3.2:3b | all | 12/24 | 75.0% | 50.0% | 10 | 2/12 | 0 |
| llama3.2:3b | email | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 |
| llama3.2:3b | support | 1/6 | n/a | 0.0% | 5 | 0/3 | 0 |
| llama3.2:3b | files | 1/6 | 0.0% | 0.0% | 4 | 1/3 | 0 |
| llama3.2:3b | scheduling | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| hermes3:8b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 |
| hermes3:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| hermes3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| hermes3:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| hermes3:8b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.1:8b | all | 22/24 | 85.7% | 100.0% | 0 | 2/12 | 3 |
| llama3.1:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.1:8b | support | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.1:8b | files | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.1:8b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 3 |
| phi4-mini:latest | all | 9/9 | 100.0% | 100.0% | 0 | 0/5 | 0 |
| phi4-mini:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| phi4-mini:latest | files | 3/3 | 100.0% | 100.0% | 0 | 0/2 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
