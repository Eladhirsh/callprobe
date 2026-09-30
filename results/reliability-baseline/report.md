# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| qwen2.5:7b | all | 30/60 | 42.9% | 56.2% | 0 | 11/27 | 10 |
| qwen2.5:7b | email | 4/16 | 15.4% | 25.0% | 0 | 5/7 | 0 |
| qwen2.5:7b | support | 24/34 | 60.0% | 66.7% | 0 | 4/16 | 10 |
| qwen2.5:7b | files | 2/6 | 25.0% | 33.3% | 0 | 1/3 | 0 |
| qwen2.5:7b | scheduling | 0/4 | 60.0% | 100.0% | 0 | 1/1 | 0 |
| llama3.1:8b | all | 49/60 | 83.8% | 96.9% | 0 | 3/27 | 15 |
| llama3.1:8b | email | 15/16 | 88.9% | 100.0% | 0 | 1/7 | 4 |
| llama3.1:8b | support | 30/34 | 89.5% | 94.4% | 0 | 1/16 | 11 |
| llama3.1:8b | files | 4/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.1:8b | scheduling | 0/4 | 50.0% | 100.0% | 0 | 1/1 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
