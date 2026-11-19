# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 75/80 | 92.7% | 90.5% | 2 | 0/36 | 0 | 18/20 |
| mistral-nemo:latest | email | 18/18 | 100.0% | 100.0% | 0 | 0/8 | 0 | 4/5 |
| mistral-nemo:latest | support | 39/40 | 95.2% | 95.2% | 0 | 0/18 | 0 | 9/10 |
| mistral-nemo:latest | files | 13/14 | 85.7% | 85.7% | 0 | 0/7 | 0 | 3/3 |
| mistral-nemo:latest | scheduling | 5/8 | 75.0% | 60.0% | 2 | 0/3 | 0 | 2/2 |
| qwen2.5:7b | all | 67/80 | 94.3% | 78.6% | 9 | 0/36 | 0 | 13/20 |
| qwen2.5:7b | email | 14/18 | 100.0% | 66.7% | 2 | 0/8 | 0 | 2/5 |
| qwen2.5:7b | support | 36/40 | 94.7% | 85.7% | 3 | 0/18 | 0 | 6/10 |
| qwen2.5:7b | files | 13/14 | 85.7% | 85.7% | 0 | 0/7 | 0 | 3/3 |
| qwen2.5:7b | scheduling | 4/8 | 100.0% | 60.0% | 4 | 0/3 | 0 | 2/2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
