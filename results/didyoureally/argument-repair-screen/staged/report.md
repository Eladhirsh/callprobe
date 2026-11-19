Run status: complete. Completed 16/16 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 8/8 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | email | 2/2 | 100.0% | 100.0% | 0 | 0/1 | 0 | 2/2 |
| mistral-nemo:latest | support | 6/6 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| qwen2.5:7b | all | 0/8 | n/a | 0.0% | 8 | 0/3 | 0 | 0/2 |
| qwen2.5:7b | email | 0/2 | n/a | 0.0% | 2 | 0/1 | 0 | 0/2 |
| qwen2.5:7b | support | 0/6 | n/a | 0.0% | 6 | 0/2 | 0 | 0/0 |

| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 3 | 0 | 0 | 0 | 0 |
| qwen2.5:7b | 3 | 0 | 0 | 0 | 3 |

| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest | 1 | 0 | 0 |
| qwen2.5:7b | 0 | 0 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts a case once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
