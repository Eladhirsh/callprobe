# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 62/72 | 81.6% | 81.6% | 3 | 2/32 | 0 |
| mistral-nemo:latest | email | 14/16 | 100.0% | 87.5% | 2 | 0/7 | 0 |
| mistral-nemo:latest | support | 35/40 | 78.3% | 85.7% | 0 | 2/18 | 0 |
| mistral-nemo:latest | files | 11/12 | 83.3% | 83.3% | 0 | 0/6 | 0 |
| mistral-nemo:latest | scheduling | 2/4 | 50.0% | 33.3% | 1 | 0/1 | 0 |
| qwen2.5:7b | all | 53/72 | 86.7% | 68.4% | 12 | 1/32 | 1 |
| qwen2.5:7b | email | 12/16 | 100.0% | 75.0% | 3 | 0/7 | 1 |
| qwen2.5:7b | support | 29/40 | 82.4% | 66.7% | 6 | 1/18 | 0 |
| qwen2.5:7b | files | 11/12 | 83.3% | 83.3% | 0 | 0/6 | 0 |
| qwen2.5:7b | scheduling | 1/4 | 100.0% | 33.3% | 3 | 0/1 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
