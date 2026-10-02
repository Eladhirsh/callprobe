## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** phi4-mini:latest

- Scored observations: 54 -> 54
- Request errors: 0 -> 0

| Run setting | Baseline | Candidate |
| --- | --- | --- |
| Suite hash | 2e82c882d93ca06a | 2e82c882d93ca06a |
| Scoring version | 3 | 3 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 4096 |
| Distractor counts | 0, 2, 4 | 0, 2, 4 |
| Repeats per case | 1 | 1 |

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 66.7% | 94.4% | +27.8% | 66.7% | 94.4% | +27.8% |
| args | 26.7% | 0.0% | -26.7% | 26.7% | 0.0% | -26.7% |
| depth | 0.0% | 0.0% | +0.0% | 0.0% | 0.0% | +0.0% |
| select | 13.3% | 0.0% | -13.3% | 13.3% | 0.0% | -13.3% |

**Pass -> fail (0):**

- none

**Fail -> pass (1):**

- unsupported-delete

**CI gate:** FAIL

Gate failure reasons:

- 6 previously passing case\(s\) regressed

Regressed observations:

- get-by-id pad=2 repeat=0
- get-by-id pad=4 repeat=0
- get-id-with-punctuation pad=4 repeat=0
- reply-draft-only pad=2 repeat=0
- reply-draft-only pad=4 repeat=0
- reply-send pad=2 repeat=0
