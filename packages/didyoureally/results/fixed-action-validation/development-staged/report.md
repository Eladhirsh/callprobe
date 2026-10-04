Run status: complete. Completed 82/82 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: staged.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 61/82 | 94.1% | 74.4% | 6 | 0/37 | 8 | 13/22 |
| mistral-nemo:latest | email | 12/20 | 100.0% | 60.0% | 6 | 0/9 | 0 | 0/7 |
| mistral-nemo:latest | files | 13/14 | 85.7% | 85.7% | 0 | 0/7 | 0 | 3/3 |
| mistral-nemo:latest | scheduling | 7/8 | 80.0% | 80.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | support | 29/40 | 100.0% | 76.2% | 0 | 0/18 | 8 | 8/10 |

| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 37 | 0 | 5 | 5 | 3 |

| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest | 3 | 8 | 1 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts a case once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
