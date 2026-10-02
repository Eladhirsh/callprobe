suite: mail-suite v1

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ max padding | tokens per success | scored/recorded/planned | request errors | truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| command-r7b:latest | 33.3% | 11.1-55.6% | 33.3% | 33.3% | 33.3% | 33.3% | 100.0% | 33.3% (+4 tools) | 5084 | 54/54/54 | 0 | 0 |
| granite3.3:8b | 51.9% | 31.5-70.4% | 51.9% | 64.8% | 59.3% | 51.9% | 33.3% | 61.1% (+4 tools) | 1306 | 54/54/54 | 0 | 0 |
| hermes3:8b | 24.1% | 7.4-42.6% | 24.1% | 79.6% | 24.1% | 24.1% | 66.7% | 22.2% (+4 tools) | 2891 | 54/54/54 | 0 | 0 |
| llama3.1:8b | 33.3% | 16.7-50.0% | 38.9% | 63.0% | 46.3% | 33.3% | 5.6% | 44.4% (+4 tools) | 2182 | 54/54/54 | 0 | 1 |
| llama3.2:3b | 37.0% | 18.5-57.4% | 40.7% | 68.5% | 55.6% | 37.0% | 16.7% | 44.4% (+4 tools) | 1732 | 54/54/54 | 0 | 0 |
| mistral-nemo:latest | 51.9% | 33.3-70.4% | 51.9% | 72.2% | 75.9% | 53.7% | 33.3% | 44.4% (+4 tools) | 1117 | 54/54/54 | 0 | 0 |
| phi4-mini:latest | 31.5% | 11.1-53.7% | 31.5% | 38.9% | 33.3% | 33.3% | 94.4% | 33.3% (+4 tools) | 3239 | 54/54/54 | 0 | 5 |
| qwen2.5:7b | 33.3% | 14.8-53.7% | 33.3% | 88.9% | 33.3% | 33.3% | 66.7% | 38.9% (+4 tools) | 1921 | 54/54/54 | 0 | 0 |
| qwen3:8b | 64.8% | 48.1-81.5% | 64.8% | 98.1% | 70.4% | 64.8% | 94.4% | 66.7% (+4 tools) | 1347 | 54/54/54 | 0 | 0 |

Note: request errors are excluded from scored success rates; truncated responses stay in them as failures. Rates are only comparable when scored/recorded/planned is complete; INCOMPLETE or `?` means partial or unverifiable coverage.
