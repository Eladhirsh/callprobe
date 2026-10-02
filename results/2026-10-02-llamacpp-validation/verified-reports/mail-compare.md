## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen2.5:7b

- Scored observations: 54 -> 54
- Request errors: 0 -> 0

| Run setting | Baseline | Candidate |
| --- | --- | --- |
| Server | ollama | llama.cpp |
| Server version | 0.34.2 | b11339-81e39ad34 |
| Suite hash | 2e82c882d93ca06a | 2e82c882d93ca06a |
| Scoring version | 3 | 3 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 4096 |
| Distractor counts | 0, 2, 4 | 0, 2, 4 |
| Repeats per case | 1 | 1 |

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 66.7% | 66.7% | +0.0% | 66.7% | 66.7% | +0.0% |
| args | 26.7% | 60.0% | +33.3% | 26.7% | 60.0% | +33.3% |
| depth | 0.0% | 100.0% | +100.0% | 0.0% | 100.0% | +100.0% |
| select | 13.3% | 100.0% | +86.7% | 13.3% | 100.0% | +86.7% |

**Pass -> fail (1):**

- search-missing-criteria

**Fail -> pass (10):**

- correction-reply-target
- correction-search-sender
- get-by-id
- get-id-with-punctuation
- reply-draft-only
- reply-send
- search-archive-folder
- search-by-sender
- search-by-subject
- search-with-limit

**CI gate:** FAIL

Gate failure reasons:

- 1 previously passing case\(s\) regressed

Regressed observations:

- search-missing-criteria pad=4 repeat=0
