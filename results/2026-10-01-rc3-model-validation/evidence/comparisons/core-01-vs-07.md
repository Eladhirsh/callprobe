## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** command-r7b:latest

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
| abstain | 90.9% | 100.0% | +9.1% | 90.9% | 100.0% | +9.1% |
| args | 70.8% | 0.0% | -70.8% | 70.8% | 0.0% | -70.8% |
| depth | 77.3% | 0.0% | -77.3% | 77.3% | 0.0% | -77.3% |
| select | 91.7% | 0.0% | -91.7% | 91.7% | 0.0% | -91.7% |
| sequence | 70.0% | 0.0% | -70.0% | 70.0% | 0.0% | -70.0% |

**Pass -> fail (27):**

- args-boolean-from-instruction
- args-dollars-to-cents
- args-duration-in-words
- args-enum-mapping
- args-escalation-urgency
- args-filtered-search
- args-full-refund-omits-amount
- args-nested-address
- depth-corrected-identifier
- depth-escalation-after-repeated-question
- depth-file-corrected-id
- depth-file-move-after-distraction
- depth-file-permanent-carried-forward
- depth-late-reference
- depth-meeting-id-corrected
- depth-notify-preference-earlier
- select-address-change
- select-availability-not-booking
- select-cancel-with-id
- select-escalate-explicit
- select-search-not-status
- sequence-availability-before-checkin
- sequence-list-before-delete
- sequence-list-before-share-all
- sequence-search-before-move
- sequence-search-before-share
- sequence-status-before-conditional-escalation

**Fail -> pass (2):**

- abstain-availability-no-calendar
- abstain-no-such-capability

**CI gate:** FAIL

Gate failure reasons:

- 59 previously passing case\(s\) regressed

Regressed observations:

- args-boolean-from-instruction pad=0 repeat=0
- args-boolean-from-instruction pad=0 repeat=1
- args-country-name-to-iso pad=0 repeat=1
- args-dollars-to-cents pad=0 repeat=0
- args-dollars-to-cents pad=0 repeat=1
- args-duration-in-words pad=0 repeat=0
- args-duration-in-words pad=0 repeat=1
- args-enum-mapping pad=0 repeat=0
- args-enum-mapping pad=0 repeat=1
- args-escalation-urgency pad=0 repeat=0
- args-escalation-urgency pad=0 repeat=1
- args-filtered-search pad=0 repeat=0
- args-filtered-search pad=0 repeat=1
- args-full-refund-omits-amount pad=0 repeat=0
- args-full-refund-omits-amount pad=0 repeat=1
- args-nested-address pad=0 repeat=0
- args-nested-address pad=0 repeat=1
- depth-corrected-identifier pad=0 repeat=0
- depth-corrected-identifier pad=0 repeat=1
- depth-escalation-after-repeated-question pad=0 repeat=0
- depth-escalation-after-repeated-question pad=0 repeat=1
- depth-file-corrected-id pad=0 repeat=0
- depth-file-corrected-id pad=0 repeat=1
- depth-file-move-after-distraction pad=0 repeat=0
- depth-file-move-after-distraction pad=0 repeat=1
- depth-file-permanent-carried-forward pad=0 repeat=0
- depth-file-permanent-carried-forward pad=0 repeat=1
- depth-file-share-after-detour pad=0 repeat=1
- depth-late-reference pad=0 repeat=0
- depth-late-reference pad=0 repeat=1
- depth-meeting-id-corrected pad=0 repeat=0
- depth-meeting-id-corrected pad=0 repeat=1
- depth-notify-preference-earlier pad=0 repeat=0
- depth-notify-preference-earlier pad=0 repeat=1
- select-address-change pad=0 repeat=0
- select-address-change pad=0 repeat=1
- select-availability-not-booking pad=0 repeat=0
- select-availability-not-booking pad=0 repeat=1
- select-cancel-with-id pad=0 repeat=0
- select-cancel-with-id pad=0 repeat=1
- select-escalate-explicit pad=0 repeat=0
- select-escalate-explicit pad=0 repeat=1
- select-search-not-status pad=0 repeat=0
- select-search-not-status pad=0 repeat=1
- select-status-direct pad=0 repeat=1
- sequence-availability-before-checkin pad=0 repeat=0
- sequence-availability-before-checkin pad=0 repeat=1
- sequence-availability-first pad=0 repeat=1
- sequence-list-before-delete pad=0 repeat=0
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
