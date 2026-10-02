## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** llama3.1:8b

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
| abstain | 66.7% | 5.6% | -61.1% | 66.7% | 5.6% | -61.1% |
| args | 26.7% | 40.0% | +13.3% | 26.7% | 40.0% | +13.3% |
| depth | 0.0% | 16.7% | +16.7% | 0.0% | 16.7% | +16.7% |
| select | 13.3% | 66.7% | +53.3% | 13.3% | 86.7% | +73.3% |

**Pass -> fail (4):**

- get-missing-id
- no-send-chat-only
- reply-missing-id
- search-missing-criteria

**Fail -> pass (3):**

- get-by-id
- get-id-with-punctuation
- search-by-subject

**CI gate:** FAIL

Gate failure reasons:

- 13 previously passing case\(s\) regressed

Regressed observations:

- get-missing-id pad=0 repeat=0
- get-missing-id pad=2 repeat=0
- get-missing-id pad=4 repeat=0
- no-send-chat-only pad=0 repeat=0
- no-send-chat-only pad=2 repeat=0
- no-send-chat-only pad=4 repeat=0
- reply-missing-id pad=0 repeat=0
- reply-missing-id pad=2 repeat=0
- reply-missing-id pad=4 repeat=0
- reply-send pad=2 repeat=0
- search-missing-criteria pad=0 repeat=0
- search-missing-criteria pad=2 repeat=0
- search-missing-criteria pad=4 repeat=0
