## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** mistral-nemo:latest

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
| abstain | 66.7% | 33.3% | -33.3% | 66.7% | 33.3% | -33.3% |
| args | 26.7% | 46.7% | +20.0% | 26.7% | 46.7% | +20.0% |
| depth | 0.0% | 33.3% | +33.3% | 0.0% | 33.3% | +33.3% |
| select | 13.3% | 86.7% | +73.3% | 13.3% | 86.7% | +73.3% |

**Pass -> fail (3):**

- get-missing-id
- no-send-chat-only
- reply-missing-id

**Fail -> pass (5):**

- get-by-id
- get-id-with-punctuation
- search-by-sender
- search-by-subject
- search-with-limit

**CI gate:** FAIL

Gate failure reasons:

- 10 previously passing case\(s\) regressed

Regressed observations:

- get-missing-id pad=0 repeat=0
- get-missing-id pad=2 repeat=0
- get-missing-id pad=4 repeat=0
- no-send-chat-only pad=2 repeat=0
- no-send-chat-only pad=4 repeat=0
- reply-draft-only pad=2 repeat=0
- reply-missing-id pad=0 repeat=0
- reply-missing-id pad=2 repeat=0
- reply-missing-id pad=4 repeat=0
- reply-send pad=2 repeat=0
