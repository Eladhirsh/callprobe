# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| qwen2.5:7b | all | 44/60 | 74.4% | 90.6% | 4 | 8/27 | 24 |
| qwen2.5:7b | email | 15/16 | 88.9% | 100.0% | 0 | 1/7 | 12 |
| qwen2.5:7b | support | 27/34 | 73.9% | 94.4% | 1 | 5/16 | 10 |
| qwen2.5:7b | files | 2/6 | 66.7% | 66.7% | 2 | 1/3 | 0 |
| qwen2.5:7b | scheduling | 0/4 | 50.0% | 66.7% | 1 | 1/1 | 2 |
| llama3.1:8b | all | 50/60 | 79.5% | 96.9% | 0 | 4/27 | 12 |
| llama3.1:8b | email | 16/16 | 100.0% | 100.0% | 0 | 0/7 | 0 |
| llama3.1:8b | support | 30/34 | 85.0% | 94.4% | 0 | 2/16 | 10 |
| llama3.1:8b | files | 4/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.1:8b | scheduling | 0/4 | 42.9% | 100.0% | 0 | 1/1 | 2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
