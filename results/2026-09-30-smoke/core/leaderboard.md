suite: core v2

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ max padding | tokens per success | scored/recorded/planned | request errors | truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| command-r7b:latest | 22.0% | 12.0-34.0% | 22.0% | 22.0% | 22.0% | 22.0% | 100.0% | 22.0% (+0 tools) | 7455 | 50/50/50 | 0 | 0 |
| granite3.3:8b | 48.0% | 34.0-62.0% | 48.0% | 66.0% | 60.0% | 56.0% | 45.5% | 48.0% (+0 tools) | 1305 | 50/50/50 | 0 | 0 |
| hermes3:8b | 56.0% | 42.0-70.0% | 56.0% | 80.0% | 76.0% | 68.0% | 63.6% | 56.0% (+0 tools) | 1150 | 50/50/50 | 0 | 0 |
| llama3.1:8b | 30.0% | 18.0-44.0% | 48.0% | 66.0% | 34.0% | 42.0% | 18.2% | 30.0% (+0 tools) | 1984 | 50/50/50 | 0 | 0 |
| llama3.2:3b | 30.0% | 18.0-44.0% | 36.0% | 60.0% | 38.0% | 40.0% | 9.1% | 30.0% (+0 tools) | 1929 | 50/50/50 | 0 | 0 |
| mistral-nemo:latest | 58.0% | 44.0-72.0% | 58.0% | 68.0% | 76.0% | 62.0% | 63.6% | 58.0% (+0 tools) | 897 | 50/50/50 | 0 | 0 |
| phi4-mini:latest | 22.0% | 12.0-34.0% | 22.0% | 26.0% | 22.0% | 22.0% | 90.9% | 22.0% (+0 tools) | 2708 | 50/50/50 | 0 | 0 |
| qwen2.5:7b | 76.0% | 64.0-88.0% | 76.0% | 94.0% | 94.0% | 82.0% | 100.0% | 76.0% (+0 tools) | 777 | 50/50/50 | 0 | 0 |
| qwen3:8b | 84.0% | 74.0-94.0% | 84.0% | 96.0% | 98.0% | 88.0% | 90.9% | 84.0% (+0 tools) | 1160 | 50/50/50 | 0 | 0 |

Note: request errors are excluded from scored success rates; truncated responses stay in them as failures. Rates are only comparable when scored/recorded/planned is complete; INCOMPLETE or `?` means partial or unverifiable coverage.
