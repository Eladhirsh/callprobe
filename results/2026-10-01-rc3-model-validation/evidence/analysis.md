# Recorded model validation

Local Ollama configurations; small synthetic suites, not a general model ranking.
Repeats change deterministic tool order. Different suite scores are not interchangeable.

| Suite | Model | Passed/scored | Errors | Truncations | Repeat disagreements |
| --- | --- | --- | --- | --- | --- |
| core | qwen2.5:7b | 79/100 | 0 | 0 | 7 |
| core | llama3.2:3b | 31/100 | 0 | 0 | 3 |
| core | hermes3:8b | 55/100 | 0 | 0 | 5 |
| core | granite3.3:8b | 51/100 | 0 | 0 | 11 |
| core | llama3.1:8b | 31/100 | 0 | 0 | 9 |
| core | mistral-nemo:latest | 60/100 | 0 | 0 | 8 |
| core | command-r7b:latest | 22/100 | 0 | 0 | 0 |
| core | phi4-mini:latest | 22/100 | 0 | 0 | 2 |
| core | qwen3:8b | 85/100 | 0 | 1 | 5 |
| mail | qwen2.5:7b | 18/54 | 0 | 0 | n/a |
| mail | llama3.2:3b | 20/54 | 0 | 0 | n/a |
| mail | hermes3:8b | 13/54 | 0 | 0 | n/a |
| mail | granite3.3:8b | 28/54 | 0 | 0 | n/a |
| mail | llama3.1:8b | 18/54 | 0 | 1 | n/a |
| mail | mistral-nemo:latest | 28/54 | 0 | 0 | n/a |
| mail | command-r7b:latest | 18/54 | 0 | 0 | n/a |
| mail | phi4-mini:latest | 17/54 | 0 | 5 | n/a |
| mail | qwen3:8b | 35/54 | 0 | 0 | n/a |

Validated 18 JUnit exports against raw outcomes.
See analysis.json for per-padding scores, failure patterns and repeat-disagreement IDs.
