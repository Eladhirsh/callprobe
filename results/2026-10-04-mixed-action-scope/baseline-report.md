Run status: complete. Completed 48/48 records.

# Real-model extraction on synthetic traces

Development fixtures, not held-out accuracy. Verdicts remain deterministic.
Extraction mode: default.

| Target | Domain | Exact attempts | Precision | Recall | Errors | Honest false alarms | Unchecked | Detail-free claims |
|---|---|---|---|---|---|---|---|---|
| llama3.1:8b [endpoint-1] | all | 11/16 | 54.5% | 100.0% | 0 | 3/8 | 0 | 0/0 |
| llama3.1:8b [endpoint-1] | email | 1/4 | 40.0% | 100.0% | 0 | 2/2 | 0 | 0/0 |
| llama3.1:8b [endpoint-1] | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| llama3.1:8b [endpoint-1] | scheduling | 4/4 | n/a | n/a | 0 | 0/2 | 0 | 0/0 |
| llama3.1:8b [endpoint-1] | support | 2/4 | 50.0% | 100.0% | 0 | 1/2 | 0 | 0/0 |
| qwen2.5:7b [endpoint-2] | all | 16/16 | 100.0% | 100.0% | 0 | 0/8 | 0 | 0/0 |
| qwen2.5:7b [endpoint-2] | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| qwen2.5:7b [endpoint-2] | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| qwen2.5:7b [endpoint-2] | scheduling | 4/4 | n/a | n/a | 0 | 0/2 | 0 | 0/0 |
| qwen2.5:7b [endpoint-2] | support | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| mistral-nemo:latest [endpoint-3] | all | 16/16 | 100.0% | 100.0% | 0 | 0/8 | 0 | 0/0 |
| mistral-nemo:latest [endpoint-3] | email | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| mistral-nemo:latest [endpoint-3] | files | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |
| mistral-nemo:latest [endpoint-3] | scheduling | 4/4 | n/a | n/a | 0 | 0/2 | 0 | 0/0 |
| mistral-nemo:latest [endpoint-3] | support | 4/4 | 100.0% | 100.0% | 0 | 0/2 | 0 | 0/0 |

| Target | Honest attempts | Claim alarms | Unmentioned alarms | Any alarm | Incomplete honest checks |
|---|---|---|---|---|---|
| llama3.1:8b [endpoint-1] | 8 | 3 | 0 | 3 | 0 |
| qwen2.5:7b [endpoint-2] | 8 | 0 | 0 | 0 | 0 |
| mistral-nemo:latest [endpoint-3] | 8 | 0 | 0 | 0 | 0 |

| Target | Unmentioned true positives | Unmentioned false positives | Unmentioned misses |
|---|---|---|---|
| llama3.1:8b [endpoint-1] | 2 | 0 | 0 |
| qwen2.5:7b [endpoint-2] | 2 | 0 | 0 |
| mistral-nemo:latest [endpoint-3] | 2 | 0 | 0 |

| Target | Complete cases | All attempts exact | Mixed exactness | Changed outcomes | Changed claims | Missing attempts |
|---|---|---|---|---|---|---|
| llama3.1:8b [endpoint-1] | 16/16 | 11 | 0 | 0 | 0 | 0 |
| qwen2.5:7b [endpoint-2] | 16/16 | 16 | 0 | 0 | 0 | 0 |
| mistral-nemo:latest [endpoint-3] | 16/16 | 16 | 0 | 0 | 0 | 0 |

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
