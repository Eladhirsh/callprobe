## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** llama3.1:8b

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
| abstain | 90.9% | 22.7% | -68.2% | 90.9% | 22.7% | -68.2% |
| args | 70.8% | 25.0% | -45.8% | 70.8% | 54.2% | -16.7% |
| depth | 77.3% | 54.5% | -22.7% | 77.3% | 81.8% | +4.5% |
| select | 91.7% | 41.7% | -50.0% | 91.7% | 83.3% | -8.3% |
| sequence | 70.0% | 15.0% | -55.0% | 70.0% | 25.0% | -45.0% |

**Pass -> fail (27):**

- abstain-cancel-without-id
- abstain-change-email-on-file
- abstain-missing-identifier
- abstain-policy-question
- abstain-reschedule-unsupported
- abstain-shipping-quote
- abstain-status-no-identifier
- args-boolean-from-instruction
- args-dollars-to-cents
- args-duration-in-words
- args-filtered-search
- args-full-refund-omits-amount
- args-nested-address
- depth-file-corrected-id
- depth-file-permanent-carried-forward
- depth-meeting-id-corrected
- depth-notify-preference-earlier
- select-address-change
- select-availability-not-booking
- select-cancel-with-id
- select-search-not-status
- sequence-availability-before-checkin
- sequence-list-before-delete
- sequence-list-before-share-all
- sequence-search-before-move
- sequence-search-before-share
- sequence-status-before-conditional-escalation

**Fail -> pass (2):**

- depth-file-share-after-detour
- select-status-direct

**CI gate:** FAIL

Gate failure reasons:

- 52 previously passing case\(s\) regressed

Regressed observations:

- abstain-availability-no-calendar pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=0
- abstain-cancel-without-id pad=0 repeat=1
- abstain-change-email-on-file pad=0 repeat=0
- abstain-change-email-on-file pad=0 repeat=1
- abstain-missing-identifier pad=0 repeat=0
- abstain-missing-identifier pad=0 repeat=1
- abstain-no-such-capability pad=0 repeat=0
- abstain-policy-question pad=0 repeat=0
- abstain-policy-question pad=0 repeat=1
- abstain-reschedule-unsupported pad=0 repeat=0
- abstain-reschedule-unsupported pad=0 repeat=1
- abstain-shipping-quote pad=0 repeat=0
- abstain-shipping-quote pad=0 repeat=1
- abstain-status-no-identifier pad=0 repeat=0
- abstain-status-no-identifier pad=0 repeat=1
- args-boolean-from-instruction pad=0 repeat=0
- args-boolean-from-instruction pad=0 repeat=1
- args-country-name-to-iso pad=0 repeat=1
- args-dollars-to-cents pad=0 repeat=0
- args-duration-in-words pad=0 repeat=0
- args-duration-in-words pad=0 repeat=1
- args-filtered-search pad=0 repeat=0
- args-filtered-search pad=0 repeat=1
- args-full-refund-omits-amount pad=0 repeat=0
- args-full-refund-omits-amount pad=0 repeat=1
- args-nested-address pad=0 repeat=1
- depth-file-corrected-id pad=0 repeat=0
- depth-file-corrected-id pad=0 repeat=1
- depth-file-permanent-carried-forward pad=0 repeat=0
- depth-file-permanent-carried-forward pad=0 repeat=1
- depth-meeting-id-corrected pad=0 repeat=1
- depth-notify-preference-earlier pad=0 repeat=0
- depth-notify-preference-earlier pad=0 repeat=1
- select-address-change pad=0 repeat=0
- select-address-change pad=0 repeat=1
- select-availability-not-booking pad=0 repeat=0
- select-availability-not-booking pad=0 repeat=1
- select-cancel-with-id pad=0 repeat=0
- select-cancel-with-id pad=0 repeat=1
- select-search-not-status pad=0 repeat=0
- sequence-availability-before-checkin pad=0 repeat=0
- sequence-availability-before-checkin pad=0 repeat=1
- sequence-availability-first pad=0 repeat=1
- sequence-list-before-delete pad=0 repeat=0
- sequence-list-before-delete pad=0 repeat=1
- sequence-list-before-share-all pad=0 repeat=0
- sequence-list-before-share-all pad=0 repeat=1
- sequence-search-before-move pad=0 repeat=1
- sequence-search-before-share pad=0 repeat=0
- sequence-status-before-conditional-escalation pad=0 repeat=0
- sequence-status-before-conditional-escalation pad=0 repeat=1
