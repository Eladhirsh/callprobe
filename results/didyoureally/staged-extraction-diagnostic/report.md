# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 21/24 | 75.0% | 75.0% | 2 | 1/20 | 0 | 21/24 |
| mistral-nemo:latest | email | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/5 | 0 | 6/6 |
| mistral-nemo:latest | files | 5/6 | 50.0% | 100.0% | 0 | 1/5 | 0 | 5/6 |
| mistral-nemo:latest | scheduling | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | all | 15/24 | 100.0% | 25.0% | 9 | 0/20 | 0 | 15/24 |
| qwen2.5:7b | email | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | support | 4/6 | n/a | 0.0% | 2 | 0/5 | 0 | 4/6 |
| qwen2.5:7b | files | 2/6 | n/a | 0.0% | 4 | 0/5 | 0 | 2/6 |
| qwen2.5:7b | scheduling | 5/6 | 100.0% | 100.0% | 1 | 0/5 | 0 | 5/6 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
