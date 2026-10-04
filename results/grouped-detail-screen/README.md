# Grouped detail extraction screen

The staged detail prompt now illustrates separate objects for repeated scalar parameters and one object for an array parameter. This addresses a recorded failure where a second order ID became an amount instead of a second refund.

This targeted screen used twelve known development cases, with the corrected partial-action labels. It covers partial refunds, deletions, invitations, retries, duplicates, and successful controls. It is not fresh validation or a general accuracy estimate.

| Model | Exact | Incomplete checks | Honest controls with any alarm |
|---|---|---|---|
| mistral-nemo:latest | 12/12 | 0 | 0/5 |
| qwen2.5:7b | 6/12 | 6 | 0/5 |

The duplicate-call control intentionally contains an unmentioned action, so it is not counted among the five fully honest controls. On these same twelve IDs, the previous saved Mistral staged predictions pass four cases under the audited labels. This is a historical comparison, not repeated-run evidence. Qwen still failed source validation on all six B-order grouped cases; its incomplete checks are not clean passes.

The run began at base commit `957831c` with the grouped-prompt edit uncommitted. The evaluated source and prompt hashes are retained in metadata. The prompt is committed alongside this report. No extraction code was changed while this screen ran. The separate unchecked-detail CLI option does not change extraction or these scores.

[Full report](report.md) and raw replies in `records.jsonl` are retained. Broader validation is still needed before promoting staged mode or claiming that the earlier 84-case benchmark problems are resolved.
