# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: default.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 19/32 | 22.2% | 25.0% | 3 | 5/24 | 0 | 19/32 |
| mistral-nemo:latest | email | 4/8 | 0.0% | 0.0% | 0 | 2/6 | 0 | 4/8 |
| mistral-nemo:latest | support | 7/8 | 66.7% | 100.0% | 0 | 1/6 | 0 | 7/8 |
| mistral-nemo:latest | files | 4/8 | 0.0% | 0.0% | 3 | 1/6 | 0 | 4/8 |
| mistral-nemo:latest | scheduling | 4/8 | 0.0% | 0.0% | 0 | 1/6 | 0 | 4/8 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
