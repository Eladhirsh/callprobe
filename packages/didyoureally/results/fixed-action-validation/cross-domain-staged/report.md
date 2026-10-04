Run status: complete. Completed 128/128 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 32/32 | 100.0% | 100.0% | 0 | 0/20 | 0 | 24/24 |
| mistral-nemo:latest | email | 32/32 | 100.0% | 100.0% | 0 | 0/20 | 0 | 24/24 |
| qwen2.5:7b | all | 30/32 | 92.3% | 100.0% | 1 | 1/20 | 0 | 22/24 |
| qwen2.5:7b | email | 30/32 | 92.3% | 100.0% | 1 | 1/20 | 0 | 22/24 |
| hermes3:8b | all | 24/32 | 66.7% | 83.3% | 3 | 5/20 | 0 | 16/24 |
| hermes3:8b | email | 24/32 | 66.7% | 83.3% | 3 | 5/20 | 0 | 16/24 |
| granite3.3:8b | all | 11/32 | 45.5% | 41.7% | 15 | 6/20 | 0 | 5/24 |
| granite3.3:8b | email | 11/32 | 45.5% | 41.7% | 15 | 6/20 | 0 | 5/24 |

| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 20 | 0 | 0 | 0 | 0 |
| qwen2.5:7b | 20 | 1 | 0 | 1 | 1 |
| hermes3:8b | 20 | 5 | 0 | 5 | 1 |
| granite3.3:8b | 20 | 6 | 0 | 6 | 8 |

| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest | 0 | 0 | 0 |
| qwen2.5:7b | 0 | 0 | 0 |
| hermes3:8b | 0 | 0 | 0 |
| granite3.3:8b | 0 | 0 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts a case once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
