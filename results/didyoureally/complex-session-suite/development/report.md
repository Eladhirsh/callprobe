# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 67/80 | 87.2% | 81.0% | 8 | 1/36 | 0 |
| mistral-nemo:latest | email | 16/18 | 88.9% | 88.9% | 1 | 0/8 | 0 |
| mistral-nemo:latest | support | 37/40 | 86.4% | 90.5% | 0 | 1/18 | 0 |
| mistral-nemo:latest | files | 11/14 | 83.3% | 71.4% | 2 | 0/7 | 0 |
| mistral-nemo:latest | scheduling | 3/8 | 100.0% | 40.0% | 5 | 0/3 | 0 |
| qwen2.5:7b | all | 60/80 | 93.5% | 69.0% | 16 | 0/36 | 2 |
| qwen2.5:7b | email | 14/18 | 100.0% | 66.7% | 3 | 0/8 | 1 |
| qwen2.5:7b | support | 32/40 | 94.1% | 76.2% | 7 | 0/18 | 0 |
| qwen2.5:7b | files | 11/14 | 83.3% | 71.4% | 1 | 0/7 | 0 |
| qwen2.5:7b | scheduling | 3/8 | 100.0% | 40.0% | 5 | 0/3 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
