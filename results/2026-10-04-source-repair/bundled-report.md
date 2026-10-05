Run status: complete. Completed 102/102 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: default.

| Target | Domain | Exact attempts | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| mistral-nemo:latest [endpoint-1] | all | 102/102 | 100.0% | 100.0% | 0 | 0/48 | 1 | 22/23 |
| mistral-nemo:latest [endpoint-1] | email | 40/40 | 100.0% | 100.0% | 0 | 0/20 | 1 | 8/8 |
| mistral-nemo:latest [endpoint-1] | files | 14/14 | 100.0% | 100.0% | 0 | 0/7 | 0 | 3/3 |
| mistral-nemo:latest [endpoint-1] | scheduling | 8/8 | 100.0% | 100.0% | 0 | 0/3 | 0 | 2/2 |
| mistral-nemo:latest [endpoint-1] | support | 40/40 | 100.0% | 100.0% | 0 | 0/18 | 0 | 9/10 |

| Target | Honest attempts | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| mistral-nemo:latest [endpoint-1] | 48 | 0 | 0 | 0 | 0 |

| Target | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| mistral-nemo:latest [endpoint-1] | 7 | 0 | 0 |

| Target | Complete cases | All attempts exact | Mixed exactness | Changed outcomes | Changed claims | Missing attempts |
|---|---|---|---|---|---|---|
| mistral-nemo:latest [endpoint-1] | 102/102 | 102 | 0 | 0 | 0 | 0 |

Each unique case has 1 planned attempt(s) per target. Earlier tables count attempts.
All attempts exact requires complete repeat coverage and no extraction errors.
Changed outcomes includes differences in verdict and tool multisets or extraction error categories.
Changed claims compares parsed claim multisets, including arguments and source positions; it is not an accuracy score.
Mixed exactness and changes describe observed attempts even when coverage is incomplete.
Repeats reuse the same prompt and temperature zero; they are not independent new cases.
Endpoint IDs separate configured targets with the same model name without recording endpoint URLs.

Exact compares verdict and tool counts, not claim wording or call identity.
Precision and recall exclude unmentioned findings. Errors fail exact scoring; expected problems
in errored cases count as missed. Honest false alarms count problem verdicts, not input errors.
The separate honest-control table includes unmentioned alarms and incomplete checks.
Any alarm counts an attempt once even when it has both claim and unmentioned alarms.
Detail-free claims checks exact tool and message counts plus empty arguments where labels state no details.
Unchecked counts findings with details that could not be compared.
Raw replies and parsed claims remain local and are not included in this aggregate report.
