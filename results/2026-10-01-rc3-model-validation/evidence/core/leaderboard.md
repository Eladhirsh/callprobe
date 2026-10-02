suite: core v2

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ max padding | tokens per success | scored/recorded/planned | request errors | truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| command-r7b:latest | 22.0% | 12.0-34.0% | 22.0% | 22.0% | 22.0% | 22.0% | 100.0% | 22.0% (+0 tools) | 7454 | 100/100/100 | 0 | 0 |
| granite3.3:8b | 51.0% | 39.0-64.0% | 51.0% | 67.0% | 63.0% | 59.0% | 45.5% | 51.0% (+0 tools) | 1234 | 100/100/100 | 0 | 0 |
| hermes3:8b | 55.0% | 42.0-68.0% | 55.0% | 77.0% | 73.0% | 69.0% | 54.5% | 55.0% (+0 tools) | 1172 | 100/100/100 | 0 | 0 |
| llama3.1:8b | 31.0% | 20.0-42.0% | 51.0% | 70.0% | 35.0% | 44.0% | 22.7% | 31.0% (+0 tools) | 1912 | 100/100/100 | 0 | 0 |
| llama3.2:3b | 31.0% | 19.0-44.0% | 37.0% | 61.0% | 39.0% | 41.0% | 9.1% | 31.0% (+0 tools) | 1866 | 100/100/100 | 0 | 0 |
| mistral-nemo:latest | 60.0% | 47.0-72.0% | 60.0% | 69.0% | 75.0% | 64.0% | 54.5% | 60.0% (+0 tools) | 867 | 100/100/100 | 0 | 0 |
| phi4-mini:latest | 22.0% | 12.0-34.0% | 22.0% | 27.0% | 22.0% | 22.0% | 95.5% | 22.0% (+0 tools) | 2685 | 100/100/100 | 0 | 0 |
| qwen2.5:7b | 79.0% | 68.0-89.0% | 79.0% | 95.0% | 94.0% | 84.0% | 90.9% | 79.0% (+0 tools) | 748 | 100/100/100 | 0 | 0 |
| qwen3:8b | 85.0% | 76.0-93.0% | 85.0% | 95.0% | 96.0% | 88.0% | 90.9% | 85.0% (+0 tools) | 1153 | 100/100/100 | 0 | 1 |

Note: request errors are excluded from scored success rates; truncated responses stay in them as failures. Rates are only comparable when scored/recorded/planned is complete; INCOMPLETE or `?` means partial or unverifiable coverage.
