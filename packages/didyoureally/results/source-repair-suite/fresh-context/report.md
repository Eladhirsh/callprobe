# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked |
|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 10/16 | 100.0% | 62.5% | 6 | 0/8 | 0 |
| mistral-nemo:latest | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 |
| mistral-nemo:latest | support | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| mistral-nemo:latest | files | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| mistral-nemo:latest | scheduling | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| qwen2.5:7b | all | 6/16 | 100.0% | 50.0% | 8 | 0/8 | 0 |
| qwen2.5:7b | email | 0/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| qwen2.5:7b | support | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| qwen2.5:7b | files | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |
| qwen2.5:7b | scheduling | 2/4 | 100.0% | 50.0% | 2 | 0/2 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
