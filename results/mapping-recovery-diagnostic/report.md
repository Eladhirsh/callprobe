# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 14/16 | 100.0% | 75.0% | 0 | 0/12 | 0 | 14/16 |
| mistral-nemo:latest | email | 2/4 | n/a | 0.0% | 0 | 0/3 | 0 | 2/4 |
| mistral-nemo:latest | support | 4/4 | 100.0% | 100.0% | 0 | 0/3 | 0 | 4/4 |
| mistral-nemo:latest | files | 4/4 | 100.0% | 100.0% | 0 | 0/3 | 0 | 4/4 |
| mistral-nemo:latest | scheduling | 4/4 | 100.0% | 100.0% | 0 | 0/3 | 0 | 4/4 |
| qwen2.5:7b | all | 12/16 | 100.0% | 50.0% | 0 | 0/12 | 0 | 12/16 |
| qwen2.5:7b | email | 4/4 | 100.0% | 100.0% | 0 | 0/3 | 0 | 4/4 |
| qwen2.5:7b | support | 2/4 | n/a | 0.0% | 0 | 0/3 | 0 | 2/4 |
| qwen2.5:7b | files | 2/4 | n/a | 0.0% | 0 | 0/3 | 0 | 2/4 |
| qwen2.5:7b | scheduling | 4/4 | 100.0% | 100.0% | 0 | 0/3 | 0 | 4/4 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
