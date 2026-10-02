# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 16/16 | 100.0% | 100.0% | 0 | 0/8 | 0 | 8/8 |
| mistral-nemo:latest | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |
| mistral-nemo:latest | support | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |
| mistral-nemo:latest | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |
| mistral-nemo:latest | scheduling | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |
| qwen2.5:7b | all | 10/16 | 77.8% | 87.5% | 2 | 1/8 | 0 | 4/8 |
| qwen2.5:7b | email | 2/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |
| qwen2.5:7b | support | 2/4 | 50.0% | 100.0% | 0 | 1/2 | 0 | 0/2 |
| qwen2.5:7b | files | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 | 0/2 |
| qwen2.5:7b | scheduling | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 2/2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
