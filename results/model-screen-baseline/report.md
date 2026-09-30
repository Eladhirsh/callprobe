# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| hermes3:8b | all | 16/24 | 57.9% | 91.7% | 0 | 7/12 | 7 |
| hermes3:8b | email | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| hermes3:8b | support | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 4 |
| hermes3:8b | files | 2/6 | 33.3% | 66.7% | 0 | 3/3 | 0 |
| hermes3:8b | scheduling | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 3 |
| granite3.3:8b | all | 16/24 | 60.0% | 100.0% | 0 | 8/12 | 6 |
| granite3.3:8b | email | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| granite3.3:8b | support | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 3 |
| granite3.3:8b | files | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| granite3.3:8b | scheduling | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 3 |
| phi4-mini:latest | all | 16/24 | 57.1% | 100.0% | 0 | 8/12 | 7 |
| phi4-mini:latest | email | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| phi4-mini:latest | support | 4/6 | 50.0% | 100.0% | 0 | 2/3 | 4 |
| phi4-mini:latest | files | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| phi4-mini:latest | scheduling | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 3 |
| llama3.2:3b | all | 16/24 | 61.1% | 91.7% | 0 | 7/12 | 8 |
| llama3.2:3b | email | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.2:3b | support | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 4 |
| llama3.2:3b | files | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| llama3.2:3b | scheduling | 3/6 | 50.0% | 66.7% | 0 | 2/3 | 4 |
| mistral-nemo:latest | all | 19/24 | 70.6% | 100.0% | 0 | 5/12 | 3 |
| mistral-nemo:latest | email | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| mistral-nemo:latest | support | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| mistral-nemo:latest | files | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| mistral-nemo:latest | scheduling | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 3 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
