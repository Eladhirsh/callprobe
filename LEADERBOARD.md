suite: core v2

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ +24 tools | tokens per success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| command-r7b | 22.0% | 12.0-34.0% | 22.0% | 22.0% | 22.0% | 22.0% | 100.0% | 22.0% | 9392 |
| granite3.3:8b | 56.9% | 46.2-67.9% | 56.9% | 68.1% | 66.1% | 59.1% | 38.6% | 55.2% | 2066 |
| hermes3:8b | 52.3% | 41.5-63.4% | 52.3% | 71.7% | 67.8% | 62.8% | 56.4% | 48.8% | 2173 |
| llama3.2:3b | 28.4% | 18.3-39.1% | 40.9% | 61.3% | 36.7% | 40.4% | 4.1% | 25.2% | 3864 |
| mistral-nemo | 63.8% | 52.7-74.3% | 63.8% | 68.7% | 75.2% | 64.4% | 59.5% | 63.6% | 1699 |
| phi4-mini | 21.8% | 11.7-33.8% | 21.8% | 23.1% | 21.8% | 21.8% | 98.6% | 22.0% | 2992 |
| qwen2.5:7b | 77.1% | 67.9-86.1% | 77.1% | 88.9% | 91.0% | 80.3% | 83.2% | 75.6% | 1408 |

## Pending rerun against suite v2

These two ran against suite v1 (34 tasks, no `files` bundle) and are not
comparable to the table above. `callprobe leaderboard` refuses to mix
them in automatically; they'll move up once rerun.

| model | success | 95% CI | type-lenient | selection | schema | args | abstain | success @ +24 tools | tokens per success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| llama3.1:8b | 32.1% | 19.4-46.1% | 51.2% | 66.9% | 33.6% | 36.8% | 9.8% | 34.3% | 3441 |
| qwen3:8b | 88.7% | 78.9-96.6% | 88.7% | 93.1% | 93.6% | 89.0% | 88.6% | 88.2% | 1568 |
