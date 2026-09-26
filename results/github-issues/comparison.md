# Recorded GitHub suite comparison

Historical observations from two local configurations, not a current model
ranking. See [conditions and limitations](README.md). This report was generated
offline from the saved result files; no new model requests were made.

## Comparison

**Baseline model:** qwen2.5:7b  
**Candidate model:** qwen3:8b

- Scored observations: 18 -> 18
- Request errors: 0 -> 0

| category | strict a | strict b | delta strict | lenient a | lenient b | delta lenient |
| --- | --- | --- | --- | --- | --- | --- |
| abstain | 40.0% | 100.0% | +60.0% | 40.0% | 100.0% | +60.0% |
| args | 40.0% | 20.0% | -20.0% | 40.0% | 20.0% | -20.0% |
| depth | 33.3% | 66.7% | +33.3% | 33.3% | 66.7% | +33.3% |
| select | 0.0% | 60.0% | +60.0% | 0.0% | 60.0% | +60.0% |

**Pass -> fail (2):**

- comment-body-punctuation
- pagination-upper-values

**Fail -> pass (8):**

- comment-body-multiline
- correction-changes-issue
- draft-only-do-not-post
- missing-issue-number
- missing-repository
- owner-repo-from-url
- post-comment-simple
- read-discussion-not-post

**CI gate:** FAIL

Gate failure reasons:

- 2 previously passing case\(s\) regressed

Regressed observations:

- comment-body-punctuation pad=0 repeat=0
- pagination-upper-values pad=0 repeat=0
