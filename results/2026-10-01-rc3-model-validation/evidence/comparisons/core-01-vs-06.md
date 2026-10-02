## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** mistral-nemo:latest

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
| abstain | 90.9% | 54.5% | -36.4% | 90.9% | 54.5% | -36.4% |
| args | 70.8% | 62.5% | -8.3% | 70.8% | 62.5% | -8.3% |
| depth | 77.3% | 36.4% | -40.9% | 77.3% | 36.4% | -40.9% |
| select | 91.7% | 91.7% | +0.0% | 91.7% | 91.7% | +0.0% |
| sequence | 70.0% | 70.0% | +0.0% | 70.0% | 70.0% | +0.0% |

**Pass -> fail (15):**

- abstain-cancel-without-id
- abstain-change-email-on-file
- abstain-reschedule-unsupported
- abstain-shipping-quote
- abstain-status-no-identifier
- args-enum-mapping
- args-escalation-urgency
- args-filtered-search
- depth-file-corrected-id
- depth-file-move-after-distraction
- depth-file-permanent-carried-forward
- depth-meeting-id-corrected
- select-escalate-explicit
- sequence-list-before-delete
- sequence-search-before-move

**Fail -> pass (5):**

- abstain-availability-no-calendar
- args-partial-refund
- select-status-direct
- sequence-availability-first
- sequence-search-before-refund

**CI gate:** FAIL

Gate failure reasons:

- 25 previously passing case\(s\) regressed

Regressed observations:

- abstain-cancel-without-id pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=1
- abstain-change-email-on-file pad=0 repeat=1
- abstain-no-such-capability pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=1
- abstain-shipping-quote pad=0 repeat=1
- abstain-status-no-identifier pad=0 repeat=0
- abstain-status-no-identifier pad=0 repeat=1
- args-enum-mapping pad=0 repeat=0
- args-enum-mapping pad=0 repeat=1
- args-escalation-urgency pad=0 repeat=1
- args-filtered-search pad=0 repeat=0
- depth-file-corrected-id pad=0 repeat=0
- depth-file-corrected-id pad=0 repeat=1
- depth-file-move-after-distraction pad=0 repeat=0
- depth-file-move-after-distraction pad=0 repeat=1
- depth-file-permanent-carried-forward pad=0 repeat=0
- depth-file-permanent-carried-forward pad=0 repeat=1
- depth-file-share-after-detour pad=0 repeat=1
- depth-meeting-id-corrected pad=0 repeat=0
- depth-meeting-id-corrected pad=0 repeat=1
- select-escalate-explicit pad=0 repeat=0
- sequence-list-before-delete pad=0 repeat=0
- sequence-search-before-move pad=0 repeat=0
