Run status: complete. Completed 32/32 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: default.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 20/32 | 85.7% | 50.0% | 8 | 1/20 | 0 | 12/24 |
| mistral-nemo:latest | email | 20/32 | 85.7% | 50.0% | 8 | 1/20 | 0 | 12/24 |

| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 20 | 1 | 1 | 2 | 4 |

| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest | 0 | 1 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts a case once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
