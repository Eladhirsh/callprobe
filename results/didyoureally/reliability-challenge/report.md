# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| qwen2.5:7b | all | 18/24 | 66.7% | 100.0% | 0 | 6/12 | 6 |
| qwen2.5:7b | email | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| qwen2.5:7b | support | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 3 |
| qwen2.5:7b | files | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 0 |
| qwen2.5:7b | scheduling | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 3 |
| llama3.1:8b | all | 19/24 | 68.8% | 91.7% | 0 | 4/12 | 6 |
| llama3.1:8b | email | 6/6 | 100.0% | 100.0% | 0 | 0/3 | 0 |
| llama3.1:8b | support | 5/6 | 75.0% | 100.0% | 0 | 1/3 | 3 |
| llama3.1:8b | files | 4/6 | 50.0% | 66.7% | 0 | 1/3 | 0 |
| llama3.1:8b | scheduling | 4/6 | 60.0% | 100.0% | 0 | 2/3 | 3 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
