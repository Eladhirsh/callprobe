# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 23/24 | 100.0% | 100.0% | 1 | 0/12 | 0 |
| mistral-nemo:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| mistral-nemo:latest | scheduling | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 |
| qwen2.5:7b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 |
| qwen2.5:7b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| qwen2.5:7b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.2:3b | all | 13/24 | 85.7% | 50.0% | 10 | 1/12 | 0 |
| llama3.2:3b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.2:3b | support | 1/6 | n/a | 0.0% | 5 | 0/3 | 0 |
| llama3.2:3b | files | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.2:3b | scheduling | 1/6 | n/a | 0.0% | 5 | 0/3 | 0 |
| hermes3:8b | all | 13/24 | 46.7% | 58.3% | 5 | 2/12 | 0 |
| hermes3:8b | email | 2/6 | 40.0% | 66.7% | 1 | 1/3 | 0 |
| hermes3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| hermes3:8b | files | 3/6 | 28.6% | 66.7% | 0 | 1/3 | 0 |
| hermes3:8b | scheduling | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 |
| llama3.1:8b | all | 15/24 | 100.0% | 41.7% | 9 | 0/12 | 0 |
| llama3.1:8b | email | 5/6 | 100.0% | 66.7% | 1 | 0/3 | 0 |
| llama3.1:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.1:8b | files | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 |
| llama3.1:8b | scheduling | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 |
| phi4-mini:latest | all | 19/24 | 100.0% | 75.0% | 5 | 0/12 | 0 |
| phi4-mini:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| phi4-mini:latest | support | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 |
| phi4-mini:latest | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| phi4-mini:latest | scheduling | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 |
| granite3.3:8b | all | 23/24 | 100.0% | 100.0% | 1 | 0/12 | 0 |
| granite3.3:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| granite3.3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| granite3.3:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| granite3.3:8b | scheduling | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
