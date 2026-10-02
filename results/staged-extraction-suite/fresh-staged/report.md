# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 29/32 | 100.0% | 75.0% | 3 | 0/24 | 0 | 29/32 |
| mistral-nemo:latest | email | 8/8 | 100.0% | 100.0% | 0 | 0/6 | 0 | 8/8 |
| mistral-nemo:latest | support | 8/8 | 100.0% | 100.0% | 0 | 0/6 | 0 | 8/8 |
| mistral-nemo:latest | files | 8/8 | 100.0% | 100.0% | 0 | 0/6 | 0 | 8/8 |
| mistral-nemo:latest | scheduling | 5/8 | n/a | 0.0% | 3 | 0/6 | 0 | 5/8 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
