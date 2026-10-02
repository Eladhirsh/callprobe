## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen3:8b

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
| args | 26.7% | 40.0% | +13.3% | 26.7% | 40.0% | +13.3% |
| depth | 0.0% | 33.3% | +33.3% | 0.0% | 33.3% | +33.3% |
| select | 13.3% | 66.7% | +53.3% | 13.3% | 66.7% | +53.3% |

**Pass -> fail (0):**

- none

**Fail -> pass (3):**

- reply-draft-only
- search-by-sender
- unsupported-delete

**CI gate:** PASS
