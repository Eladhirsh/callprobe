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
| llama3.2:3b | all | 21/24 | 100.0% | 83.3% | 3 | 0/12 | 0 | 8/8 |
| llama3.2:3b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.2:3b | scheduling | 3/6 | 100.0% | 33.3% | 3 | 0/3 | 0 | 2/2 |
| hermes3:8b | all | 24/24 | 100.0% | 100.0% | 0 | 0/12 | 0 | 8/8 |
| hermes3:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| hermes3:8b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | all | 22/24 | 92.3% | 100.0% | 1 | 1/12 | 0 | 6/8 |
| llama3.1:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | support | 5/6 | 100.0% | 100.0% | 1 | 0/3 | 0 | 1/2 |
| llama3.1:8b | files | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| llama3.1:8b | scheduling | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 | 1/2 |
| phi4-mini:latest | all | 14/24 | 83.3% | 41.7% | 0 | 1/12 | 3 | 7/8 |
| phi4-mini:latest | email | 3/6 | 100.0% | 33.3% | 0 | 0/3 | 0 | 2/2 |
| phi4-mini:latest | support | 5/6 | 100.0% | 66.7% | 0 | 0/3 | 0 | 2/2 |
| phi4-mini:latest | files | 2/6 | n/a | 0.0% | 0 | 0/3 | 0 | 2/2 |
| phi4-mini:latest | scheduling | 4/6 | 66.7% | 66.7% | 0 | 1/3 | 3 | 1/2 |
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
