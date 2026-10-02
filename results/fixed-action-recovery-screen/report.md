# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 6/6 |
| mistral-nemo:latest | email | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| mistral-nemo:latest | files | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| mistral-nemo:latest | scheduling | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| qwen2.5:7b | all | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 | 6/6 |
| qwen2.5:7b | email | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| qwen2.5:7b | files | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| qwen2.5:7b | scheduling | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
