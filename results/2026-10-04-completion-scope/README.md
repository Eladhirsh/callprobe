# Completion scope and retry counts

This check targets two false alarms found in saved agent replies: counting failed
attempts as additional successes, and treating future JSON examples as completed
calls. Shared prompt instructions now distinguish these from real repeated
success claims. Matching remains deterministic. No application tools ran.

## Focused before and after check

Eight synthetic cases were extracted with the installed local
`mistral-nemo:latest`, JSON mode, and temperature zero. Six are bundled cases
85, 86, and 91 through 94. Two are saved Llama3.1 replies from the
[agent validation matrix](../2026-10-04-agent-validation-matrix/README.md):
`files-archive-retry-succeeds` and `scheduling-two-invitation-copies`.
The baseline uses prompts from commit `83fc008`; both runs use the same current
extractor helpers and matcher.

| Extraction mode | Baseline exact | Candidate exact | Improved cases | Regressed cases |
|---|---:|---:|---:|---:|
| Default | 4 of 8 | 8 of 8 | 4 | 0 |
| Staged | 6 of 8 | 7 of 8 | 1 | 0 |

The default extractor fixed both saved false alarms and preserved repeated-action
multiplicity. Staged extraction still flags the new future-tense JSON plan in
case 94. An additional staged tense example was tried; it produced the same
counts and was removed. Both iterations are retained in the aggregate summary.
These prompts reduce observed errors; they do not guarantee correct extraction.

## Full default extraction run

The final default prompts matched the expected verdict and tool counts in
94 of 94 cases, with 0 extraction errors. All 49 labeled problem
findings were detected, with 0 additional problem findings and 0 missed
problem findings. No honest control produced a problem or unmentioned alarm.
One finding retains an unchecked recipient in case 83 because the recorded
call has no recipient argument. It is not evidence that the recipient matched.

The separate detail-free claim metric matched 22 of 23 cases.
Case 35 names order A-45 in the target reply and the extractor retains that ID,
while its label has empty arguments. Its phantom-refund verdict still matches.
The original label is retained; this discrepancy needs a separate annotation
review and must not be hidden by the verdict score.

Exact compares the multiset of verdicts and tool names. It does not establish
that every argument, claim, or matched call identity is correct. These are
synthetic development cases on one extractor, not held-out accuracy or evidence
that every model follows the instructions. The staged extractor did not receive
a full 94-case run in this check.

## Deterministic and installation checks

- All 1,449 Callprobe tests and 321 Didyoureally tests pass.
- Package Ruff and formatting checks pass.
- All 94 labeled matcher cases pass, with 49 planted problems caught and no false alarms or misses.
- All 94 frozen cases reproduce byte for byte from the generator.
- All 100 archived agent episodes replay unchanged.
- Both wheels build and install in an isolated environment outside the checkout.
- The installed benchmark includes all 94 cases; shared agent initialization works.
- Callprobe's wheel contains no Didyoureally source; Didyoureally remains runtime dependency-free.

The labeled matcher score is separate from the real extraction results above.

## Evidence and reproduction

[Summary](summary.json) records timestamps, model digest, prompt and source hashes,
case coverage, errors, aggregate metrics, and per-case verdict comparisons.
Raw requests and responses remain local. Existing archived claims and model
reports are unchanged. No versions, release tags, or packages were published.

To repeat the full candidate extraction with an installed local model:

```bash
.venv/bin/python packages/didyoureally/scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --json-mode --extraction-mode default --out /tmp/completion-scope-new-run
```

Use a new output directory. Model weights, serving settings, and prompt changes
can affect results; a successful labeled benchmark alone cannot validate extraction.
