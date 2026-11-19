# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 65/80 | 87.2% | 81.0% | 4 | 1/36 | 1 | 16/20 |
| mistral-nemo:latest | email | 15/18 | 88.9% | 88.9% | 0 | 1/8 | 1 | 2/5 |
| mistral-nemo:latest | support | 35/40 | 94.7% | 85.7% | 0 | 0/18 | 0 | 9/10 |
| mistral-nemo:latest | files | 11/14 | 83.3% | 71.4% | 2 | 0/7 | 0 | 3/3 |
| mistral-nemo:latest | scheduling | 4/8 | 60.0% | 60.0% | 2 | 0/3 | 0 | 2/2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
