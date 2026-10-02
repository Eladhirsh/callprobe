## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen3:8b

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
| args | 70.8% | 87.5% | +16.7% | 70.8% | 87.5% | +16.7% |
| depth | 77.3% | 81.8% | +4.5% | 77.3% | 81.8% | +4.5% |
| select | 91.7% | 91.7% | +0.0% | 91.7% | 91.7% | +0.0% |
| sequence | 70.0% | 75.0% | +5.0% | 70.0% | 75.0% | +5.0% |

**Pass -> fail (3):**

- depth-file-move-after-distraction
- select-address-change
- sequence-list-before-delete

**Fail -> pass (7):**

- abstain-availability-no-calendar
- args-explicit-datetime
- args-partial-refund
- depth-refund-amount-after-clarification
- select-status-direct
- sequence-availability-first
- sequence-search-before-refund

**CI gate:** FAIL

Gate failure reasons:

- 5 previously passing case\(s\) regressed

Regressed observations:

- abstain-no-such-capability pad=0 repeat=0
- depth-file-move-after-distraction pad=0 repeat=1
- depth-file-share-after-detour pad=0 repeat=1
- select-address-change pad=0 repeat=1
- sequence-list-before-delete pad=0 repeat=0
