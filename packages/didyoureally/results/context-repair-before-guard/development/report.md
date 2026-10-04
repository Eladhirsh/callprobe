# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 75/80 | 95.0% | 90.5% | 2 | 0/36 | 1 |
| mistral-nemo:latest | email | 18/18 | 100.0% | 100.0% | 0 | 0/8 | 0 |
| mistral-nemo:latest | support | 39/40 | 95.2% | 95.2% | 0 | 0/18 | 0 |
| mistral-nemo:latest | files | 13/14 | 85.7% | 85.7% | 0 | 0/7 | 0 |
| mistral-nemo:latest | scheduling | 5/8 | 100.0% | 60.0% | 2 | 0/3 | 1 |
| qwen2.5:7b | all | 65/80 | 93.9% | 73.8% | 11 | 0/36 | 2 |
| qwen2.5:7b | email | 16/18 | 100.0% | 77.8% | 1 | 0/8 | 1 |
| qwen2.5:7b | support | 34/40 | 94.4% | 81.0% | 5 | 0/18 | 0 |
| qwen2.5:7b | files | 12/14 | 83.3% | 71.4% | 0 | 0/7 | 0 |
| qwen2.5:7b | scheduling | 3/8 | 100.0% | 40.0% | 5 | 0/3 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
