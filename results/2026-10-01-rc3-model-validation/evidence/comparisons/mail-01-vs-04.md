## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** granite3.3:8b

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
| args | 26.7% | 73.3% | +46.7% | 26.7% | 73.3% | +46.7% |
| depth | 0.0% | 0.0% | +0.0% | 0.0% | 0.0% | +0.0% |
| select | 13.3% | 73.3% | +60.0% | 13.3% | 73.3% | +60.0% |

**Pass -> fail (4):**

- get-missing-id
- no-send-chat-only
- reply-missing-id
- search-missing-criteria

**Fail -> pass (7):**

- get-by-id
- get-id-with-punctuation
- reply-draft-only
- reply-send
- search-archive-folder
- search-by-sender
- unsupported-delete

**CI gate:** FAIL

Gate failure reasons:

- 11 previously passing case\(s\) regressed

Regressed observations:

- get-missing-id pad=0 repeat=0
- get-missing-id pad=2 repeat=0
- get-missing-id pad=4 repeat=0
- no-send-chat-only pad=0 repeat=0
- no-send-chat-only pad=2 repeat=0
- no-send-chat-only pad=4 repeat=0
- reply-missing-id pad=0 repeat=0
- reply-missing-id pad=2 repeat=0
- search-missing-criteria pad=0 repeat=0
- search-missing-criteria pad=2 repeat=0
- search-missing-criteria pad=4 repeat=0
