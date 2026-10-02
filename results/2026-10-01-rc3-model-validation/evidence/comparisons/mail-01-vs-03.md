## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** hermes3:8b

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
| abstain | 66.7% | 66.7% | +0.0% | 66.7% | 66.7% | +0.0% |
| args | 26.7% | 6.7% | -20.0% | 26.7% | 6.7% | -20.0% |
| depth | 0.0% | 0.0% | +0.0% | 0.0% | 0.0% | +0.0% |
| select | 13.3% | 0.0% | -13.3% | 13.3% | 0.0% | -13.3% |

**Pass -> fail (3):**

- get-missing-id
- no-send-chat-only
- reply-missing-id

**Fail -> pass (2):**

- unsupported-delete
- unsupported-forward

**CI gate:** FAIL

Gate failure reasons:

- 11 previously passing case\(s\) regressed

Regressed observations:

- get-by-id pad=2 repeat=0
- get-by-id pad=4 repeat=0
- get-missing-id pad=4 repeat=0
- no-send-chat-only pad=2 repeat=0
- no-send-chat-only pad=4 repeat=0
- reply-draft-only pad=2 repeat=0
- reply-draft-only pad=4 repeat=0
- reply-missing-id pad=0 repeat=0
- reply-missing-id pad=2 repeat=0
- reply-missing-id pad=4 repeat=0
- reply-send pad=2 repeat=0
