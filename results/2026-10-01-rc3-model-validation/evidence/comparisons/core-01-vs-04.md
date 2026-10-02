## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** granite3.3:8b

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
| abstain | 90.9% | 45.5% | -45.5% | 90.9% | 45.5% | -45.5% |
| args | 70.8% | 62.5% | -8.3% | 70.8% | 62.5% | -8.3% |
| depth | 77.3% | 50.0% | -27.3% | 77.3% | 50.0% | -27.3% |
| select | 91.7% | 91.7% | +0.0% | 91.7% | 91.7% | +0.0% |
| sequence | 70.0% | 20.0% | -50.0% | 70.0% | 20.0% | -50.0% |

**Pass -> fail (18):**

- abstain-cancel-without-id
- abstain-missing-identifier
- abstain-reschedule-unsupported
- abstain-status-no-identifier
- args-dollars-to-cents
- args-filtered-search
- args-nested-address
- depth-escalation-after-repeated-question
- depth-file-move-after-distraction
- depth-file-permanent-carried-forward
- depth-meeting-id-corrected
- select-availability-not-booking
- sequence-availability-before-checkin
- sequence-list-before-delete
- sequence-list-before-share-all
- sequence-search-before-move
- sequence-search-before-share
- sequence-status-before-conditional-escalation

**Fail -> pass (2):**

- args-relative-dates
- select-status-direct

**CI gate:** FAIL

Gate failure reasons:

- 32 previously passing case\(s\) regressed

Regressed observations:

- abstain-availability-no-calendar pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=1
- abstain-missing-identifier pad=0 repeat=0
- abstain-missing-identifier pad=0 repeat=1
- abstain-no-such-capability pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=1
- abstain-status-no-identifier pad=0 repeat=0
- abstain-status-no-identifier pad=0 repeat=1
- args-country-name-to-iso pad=0 repeat=1
- args-dollars-to-cents pad=0 repeat=0
- args-filtered-search pad=0 repeat=0
- args-nested-address pad=0 repeat=0
- depth-escalation-after-repeated-question pad=0 repeat=0
- depth-file-move-after-distraction pad=0 repeat=0
- depth-file-permanent-carried-forward pad=0 repeat=1
- depth-file-share-after-detour pad=0 repeat=1
- depth-meeting-id-corrected pad=0 repeat=0
- depth-meeting-id-corrected pad=0 repeat=1
- select-availability-not-booking pad=0 repeat=1
- sequence-availability-before-checkin pad=0 repeat=0
- sequence-availability-before-checkin pad=0 repeat=1
- sequence-availability-first pad=0 repeat=1
- sequence-list-before-delete pad=0 repeat=0
- sequence-list-before-delete pad=0 repeat=1
- sequence-list-before-share-all pad=0 repeat=0
- sequence-list-before-share-all pad=0 repeat=1
- sequence-search-before-move pad=0 repeat=1
- sequence-search-before-refund pad=0 repeat=1
- sequence-search-before-share pad=0 repeat=0
- sequence-status-before-conditional-escalation pad=0 repeat=1
