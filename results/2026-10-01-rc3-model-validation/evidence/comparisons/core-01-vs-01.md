## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen2.5:7b

- Scored observations: 100 -> 100
- Request errors: 0 -> 0

| Run setting | Baseline | Candidate |
| --- | --- | --- |
| Suite hash | e597c986302b5596 | e597c986302b5596 |
| Scoring version | 3 | 3 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 4096 |
| Distractor counts | 0 | 0 |
| Repeats per case | 2 | 2 |

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 90.9% | 90.9% | +0.0% | 90.9% | 90.9% | +0.0% |
| args | 70.8% | 70.8% | +0.0% | 70.8% | 70.8% | +0.0% |
| depth | 77.3% | 77.3% | +0.0% | 77.3% | 77.3% | +0.0% |
| select | 91.7% | 91.7% | +0.0% | 91.7% | 91.7% | +0.0% |
| sequence | 70.0% | 70.0% | +0.0% | 70.0% | 70.0% | +0.0% |

**Pass -> fail (0):**

- none

**Fail -> pass (0):**

- none

**CI gate:** PASS
