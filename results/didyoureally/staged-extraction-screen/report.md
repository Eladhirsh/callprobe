# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 22/24 | 100.0% | 75.0% | 2 | 0/20 | 0 | 22/24 |
| mistral-nemo:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| mistral-nemo:latest | files | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| mistral-nemo:latest | scheduling | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | all | 16/24 | 50.0% | 25.0% | 6 | 0/20 | 0 | 16/24 |
| qwen2.5:7b | email | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | support | 2/6 | n/a | 0.0% | 4 | 0/5 | 0 | 2/6 |
| qwen2.5:7b | files | 4/6 | 0.0% | 0.0% | 0 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | scheduling | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| hermes3:8b | all | 16/24 | 50.0% | 25.0% | 5 | 1/20 | 1 | 16/24 |
| hermes3:8b | email | 4/6 | 0.0% | 0.0% | 1 | 1/5 | 1 | 4/6 |
| hermes3:8b | support | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| hermes3:8b | files | 4/6 | 100.0% | 100.0% | 2 | 0/5 | 0 | 4/6 |
| hermes3:8b | scheduling | 4/6 | n/a | 0.0% | 0 | 0/5 | 0 | 4/6 |
| granite3.3:8b | all | 15/24 | 33.3% | 25.0% | 7 | 2/20 | 0 | 15/24 |
| granite3.3:8b | email | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| granite3.3:8b | support | 3/6 | n/a | 0.0% | 3 | 0/5 | 0 | 3/6 |
| granite3.3:8b | files | 4/6 | 33.3% | 100.0% | 0 | 2/5 | 0 | 4/6 |
| granite3.3:8b | scheduling | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
