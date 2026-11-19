# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 71/80 | 94.7% | 85.7% | 7 | 0/36 | 0 |
| mistral-nemo:latest | email | 18/18 | 100.0% | 100.0% | 0 | 0/8 | 0 |
| mistral-nemo:latest | support | 39/40 | 95.2% | 95.2% | 0 | 0/18 | 0 |
| mistral-nemo:latest | files | 11/14 | 83.3% | 71.4% | 2 | 0/7 | 0 |
| mistral-nemo:latest | scheduling | 3/8 | 100.0% | 40.0% | 5 | 0/3 | 0 |
| qwen2.5:7b | all | 63/80 | 93.9% | 73.8% | 13 | 0/36 | 2 |
| qwen2.5:7b | email | 14/18 | 100.0% | 66.7% | 3 | 0/8 | 1 |
| qwen2.5:7b | support | 34/40 | 94.4% | 81.0% | 5 | 0/18 | 0 |
| qwen2.5:7b | files | 11/14 | 83.3% | 71.4% | 1 | 0/7 | 0 |
| qwen2.5:7b | scheduling | 4/8 | 100.0% | 60.0% | 4 | 0/3 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
