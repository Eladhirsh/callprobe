suite: suite v1

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ max padding | tokens per success | scored/recorded/planned | request errors | truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| command-r7b:latest | 33.3% | 11.1-55.6% | 33.3% | 33.3% | 33.3% | 33.3% | 100.0% | 33.3% (+0 tools) | 4793 | 18/18/18 | 0 | 0 |
| llama3.1:8b | 27.8% | 11.1-50.0% | 33.3% | 66.7% | 44.4% | 27.8% | 16.7% | 27.8% (+0 tools) | 1944 | 18/18/18 | 0 | 0 |
| llama3.2:3b | 27.8% | 11.1-50.0% | 33.3% | 61.1% | 50.0% | 27.8% | 0.0% | 27.8% (+0 tools) | 1907 | 18/18/18 | 0 | 0 |
| qwen2.5:7b | 22.2% | 5.6-44.4% | 22.2% | 88.9% | 22.2% | 22.2% | 66.7% | 22.2% (+0 tools) | 2406 | 18/18/18 | 0 | 0 |

Note: request errors are excluded from scored success rates; truncated responses stay in them as failures. Rates are only comparable when scored/recorded/planned is complete; INCOMPLETE or `?` means partial or unverifiable coverage.
