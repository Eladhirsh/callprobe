# Agent reliability report

Mock execution only. No real business actions occurred.

Run status: interrupted. Completed cases: 16/28.

| Case | Agent | Decisions | Account | Findings |
|---|---|---|---|---|
| refund-and-receipt | complete | fail | pass | backed, backed |
| email-fails | complete | fail | pass | backed |
| email-retry-succeeds | truncated | fail | fail | unmentioned |
| email-retry-fails | truncated | fail | fail | unmentioned |
| refund-fails | complete | fail | fail | unmentioned |
| refund-only | complete | pass | pass | backed |
| receipt-only | complete | pass | pass | backed |
| offer-only | complete | pass | pass | none |
| currency-eur | complete | pass | pass | backed |
| cents-to-dollars | complete | pass | pass | backed |
| corrected-recipient | complete | fail | incomplete | none |
| two-receipt-copies | complete | fail | pass | backed, backed |
| files-archive-success | complete | pass | pass | backed |
| files-delete-fails | complete | pass | pass | none |
| files-archive-retry-succeeds | complete | pass | pass | backed |
| files-two-backup-copies | complete | fail | pass | backed, backed |

Decision checks compare each serial turn with the authored expected call. Account checks use Didyoureally's extracted claims and deterministic matcher. Any non-backed finding or unchecked detail fails the account gate. Incomplete generation or extraction cannot pass the combined gate.
