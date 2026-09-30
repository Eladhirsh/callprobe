# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| qwen2.5:7b | all | 46/60 | 75.6% | 96.9% | 2 | 8/27 | 24 |
| qwen2.5:7b | email | 15/16 | 88.9% | 100.0% | 0 | 1/7 | 12 |
| qwen2.5:7b | support | 28/34 | 78.3% | 100.0% | 0 | 5/16 | 10 |
| qwen2.5:7b | files | 3/6 | 66.7% | 66.7% | 2 | 1/3 | 0 |
| qwen2.5:7b | scheduling | 0/4 | 50.0% | 100.0% | 0 | 1/1 | 2 |
| llama3.1:8b | all | 52/60 | 81.1% | 93.8% | 1 | 3/27 | 12 |
| llama3.1:8b | email | 16/16 | 100.0% | 100.0% | 0 | 0/7 | 0 |
| llama3.1:8b | support | 31/34 | 88.9% | 88.9% | 1 | 1/16 | 10 |
| llama3.1:8b | files | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 0 |
| llama3.1:8b | scheduling | 0/4 | 42.9% | 100.0% | 0 | 1/1 | 2 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
