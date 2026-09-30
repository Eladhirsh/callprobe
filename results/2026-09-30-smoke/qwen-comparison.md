## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen3:8b

- Scored observations: 50 -> 50
- Request errors: 0 -> 0

| Run setting | Baseline | Candidate |
| --- | --- | --- |
| Suite hash | e597c986302b5596 | e597c986302b5596 |
| Scoring version | 3 | 3 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 4096 |
| Distractor counts | 0 | 0 |
| Repeats per case | 1 | 1 |

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 100.0% | 90.9% | -9.1% | 100.0% | 90.9% | -9.1% |
| args | 66.7% | 83.3% | +16.7% | 66.7% | 83.3% | +16.7% |
| depth | 72.7% | 81.8% | +9.1% | 72.7% | 81.8% | +9.1% |
| select | 83.3% | 100.0% | +16.7% | 83.3% | 100.0% | +16.7% |
| sequence | 60.0% | 70.0% | +10.0% | 60.0% | 70.0% | +10.0% |

**Pass -> fail (2):**

- abstain-no-such-capability
- sequence-list-before-delete

**Fail -> pass (6):**

- args-explicit-datetime
- args-partial-refund
- depth-refund-amount-after-clarification
- select-status-direct
- sequence-availability-first
- sequence-search-before-refund

**CI gate:** FAIL

Gate failure reasons:

- 2 previously passing case\(s\) regressed

Regressed observations:

- abstain-no-such-capability pad=0 repeat=0
- sequence-list-before-delete pad=0 repeat=0
