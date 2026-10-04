# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 | 8/8 |
| mistral-nemo:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| qwen2.5:7b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 | 8/8 |
| qwen2.5:7b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| qwen2.5:7b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| qwen2.5:7b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| qwen2.5:7b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | all | 20/24 | 100.0% | 75.0% | 4 | 0/12 | 0 | 8/8 |
| llama3.2:3b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | scheduling | 2/6 | n/a | 0.0% | 4 | 0/3 | 0 | 2/2 |
| hermes3:8b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 | 8/8 |
| hermes3:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | all | 23/24 | 100.0% | 100.0% | 1 | 0/12 | 0 | 7/8 |
| llama3.1:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | scheduling | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 | 1/2 |
| phi4-mini:latest | all | 12/24 | 80.0% | 33.3% | 0 | 1/12 | 0 | 7/8 |
| phi4-mini:latest | email | 3/6 | 100.0% | 33.3% | 0 | 0/3 | 0 | 2/2 |
| phi4-mini:latest | support | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 | 1/2 |
| phi4-mini:latest | files | 2/6 | n/a | 0.0% | 0 | 0/3 | 0 | 2/2 |
| phi4-mini:latest | scheduling | 2/6 | n/a | 0.0% | 0 | 0/3 | 0 | 2/2 |
| granite3.3:8b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 | 8/8 |
| granite3.3:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| granite3.3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| granite3.3:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| granite3.3:8b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
