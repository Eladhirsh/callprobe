## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** hermes3:8b

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
| args | 70.8% | 54.2% | -16.7% | 70.8% | 54.2% | -16.7% |
| depth | 77.3% | 86.4% | +9.1% | 77.3% | 86.4% | +9.1% |
| select | 91.7% | 83.3% | -8.3% | 91.7% | 83.3% | -8.3% |
| sequence | 70.0% | 5.0% | -65.0% | 70.0% | 5.0% | -65.0% |

**Pass -> fail (15):**

- abstain-cancel-without-id
- abstain-missing-identifier
- abstain-policy-question
- abstain-reschedule-unsupported
- abstain-status-no-identifier
- args-duration-in-words
- args-escalation-urgency
- depth-escalation-after-repeated-question
- select-availability-not-booking
- sequence-availability-before-checkin
- sequence-list-before-delete
- sequence-list-before-share-all
- sequence-search-before-move
- sequence-search-before-share
- sequence-status-before-conditional-escalation

**Fail -> pass (4):**

- abstain-no-such-capability
- depth-file-share-after-detour
- depth-reason-stated-earlier
- select-status-direct

**CI gate:** FAIL

Gate failure reasons:

- 29 previously passing case\(s\) regressed

Regressed observations:

- abstain-availability-no-calendar pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=1
- abstain-missing-identifier pad=0 repeat=1
- abstain-policy-question pad=0 repeat=0
- abstain-policy-question pad=0 repeat=1
- abstain-reschedule-unsupported pad=0 repeat=1
- abstain-status-no-identifier pad=0 repeat=0
- abstain-status-no-identifier pad=0 repeat=1
- args-country-name-to-iso pad=0 repeat=1
- args-duration-in-words pad=0 repeat=0
- args-duration-in-words pad=0 repeat=1
- args-escalation-urgency pad=0 repeat=0
- depth-escalation-after-repeated-question pad=0 repeat=0
- select-availability-not-booking pad=0 repeat=0
- select-availability-not-booking pad=0 repeat=1
- sequence-availability-before-checkin pad=0 repeat=0
- sequence-availability-before-checkin pad=0 repeat=1
- sequence-availability-first pad=0 repeat=1
- sequence-list-before-delete pad=0 repeat=1
- sequence-list-before-share-all pad=0 repeat=0
- sequence-list-before-share-all pad=0 repeat=1
- sequence-search-before-move pad=0 repeat=0
- sequence-search-before-move pad=0 repeat=1
- sequence-search-before-refund pad=0 repeat=1
- sequence-search-before-share pad=0 repeat=0
- sequence-search-before-share pad=0 repeat=1
- sequence-status-before-conditional-escalation pad=0 repeat=0
- sequence-status-before-conditional-escalation pad=0 repeat=1
