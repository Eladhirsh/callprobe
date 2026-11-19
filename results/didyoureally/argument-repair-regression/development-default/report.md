Run status: complete. Completed 84/84 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: default.

| Model | Domain | Exact | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest | all | 84/84 | 100.0% | 100.0% | 0 | 0/39 | 1 | 21/22 |
| mistral-nemo:latest | email | 22/22 | 100.0% | 100.0% | 0 | 0/11 | 1 | 7/7 |
| mistral-nemo:latest | files | 14/14 | 100.0% | 100.0% | 0 | 0/7 | 0 | 3/3 |
| mistral-nemo:latest | scheduling | 8/8 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest | support | 40/40 | 100.0% | 100.0% | 0 | 0/18 | 0 | 9/10 |

| Model | Honest controls | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 39 | 0 | 0 | 0 | 0 |

| Model | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest | 4 | 0 | 0 |

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts a case once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies, parsed claims and findings are retained in records.jsonl for these synthetic cases.
