# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 13/17 | 33.3% | 50.0% | 0 | 2/13 | 0 | 11/17 |
| mistral-nemo:latest | email | 6/8 | 33.3% | 50.0% | 0 | 1/6 | 0 | 5/8 |
| mistral-nemo:latest | files | 6/8 | 33.3% | 50.0% | 0 | 1/6 | 0 | 5/8 |
| mistral-nemo:latest | scheduling | 1/1 | n/a | n/a | 0 | 0/1 | 0 | 1/1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
