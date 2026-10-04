# Agent regression comparison

Complete paired cases: 12/12.

| Check | Baseline passes | Candidate passes | Improved | Regressed |
|---|---|---|---|---|
| Decisions | 5/12 | 4/12 | 0 | 1 |
| Account | 11/12 | 8/12 | 0 | 3 |
| Both | 5/12 | 4/12 | 0 | 1 |

Decisions regressions: offer-only.

Account regressions: email-fails, email-retry-succeeds, offer-only.

Both regressions: offer-only.

Regression gate: fail.
This checks for regressions, not that either run passed every case. Matching model tags do not verify served weights.

