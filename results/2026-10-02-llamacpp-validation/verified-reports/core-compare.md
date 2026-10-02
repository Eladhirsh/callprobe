## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen2.5:7b

- Scored observations: 100 -> 100
- Request errors: 0 -> 0

| Run setting | Baseline | Candidate |
| --- | --- | --- |
| Server | ollama | llama.cpp |
| Server version | 0.34.2 | b11339-81e39ad34 |
| Suite hash | e597c986302b5596 | e597c986302b5596 |
| Scoring version | 3 | 3 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 4096 |
| Distractor counts | 0 | 0 |
| Repeats per case | 2 | 2 |

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 90.9% | 90.9% | +0.0% | 90.9% | 90.9% | +0.0% |
| args | 70.8% | 75.0% | +4.2% | 70.8% | 75.0% | +4.2% |
| depth | 77.3% | 81.8% | +4.5% | 77.3% | 81.8% | +4.5% |
| select | 91.7% | 100.0% | +8.3% | 91.7% | 100.0% | +8.3% |
| sequence | 70.0% | 70.0% | +0.0% | 70.0% | 70.0% | +0.0% |

**Pass -> fail (2):**

- abstain-reschedule-unsupported
- depth-escalation-after-repeated-question

**Fail -> pass (5):**

- abstain-availability-no-calendar
- args-country-name-to-iso
- depth-reason-stated-earlier
- select-status-direct
- sequence-cancel-before-rebook

**CI gate:** FAIL

Gate failure reasons:

- 6 previously passing case\(s\) regressed

Regressed observations:

- abstain-no-such-capability pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=1
- depth-escalation-after-repeated-question pad=0 repeat=0
- depth-file-share-after-detour pad=0 repeat=1
- sequence-availability-first pad=0 repeat=1
- sequence-search-before-refund pad=0 repeat=1
