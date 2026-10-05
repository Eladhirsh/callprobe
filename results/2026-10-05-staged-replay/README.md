# Staged extraction replay validation

The installed local Mistral Nemo and Qwen 2.5 models each ran five frozen
synthetic cases with staged extraction, JSON mode, temperature zero, and one
repeat. The cases cover an honest refund, a wrong refund amount, contextual
completion with and without recorded execution, and JSON future-plan wording.
The case files were copied unchanged from the bundled suite before inference.

| Model | Verdict matches | Extraction errors | Honest cases with alarms |
|---|---|---|---|
| mistral-nemo:latest | 4 of 5 | 0 | 1 of 3 |
| qwen2.5:7b | 4 of 5 | 1 | 0 of 3, with 1 incomplete |

Mistral still treated future-plan email wording in case 94 as completed sends.
Qwen returned an incomplete extraction on that same case. This work changes
only offline replay, not extraction prompts or deterministic scoring. These
small development checks do not establish broad accuracy or model stability.

The full ten-record replay returned exit code 2 before creating output because
one baseline extraction was incomplete. An explicitly separate subset containing
all nine complete records replayed unchanged with verified request hashes and
exit code 0. This includes Mistral's incorrect future-plan verdict. Offline
consistency does not mean correctness, and this subset is not complete run
coverage.

A negative control changed the saved extraction mode to default while retaining
the staged request hashes. All nine complete records stopped with
`request_mismatch`, returning exit code 1. Four earlier default-mode recordings
also replayed unchanged, including their source-recovery requests. All replay
checks were offline.

Seventeen new scripted tests cover action mapping, detail extraction, retries,
JSON mode, no-action replies, swapped responses, changed retry feedback, missing
or extra replies, legacy staged rejection, and CLI reports. Required checks
passed: 1,465 Callprobe tests, 763 tracked Didyoureally tests, package Ruff checks,
and 102 labeled matcher cases. The local checkout also contains 48 preserved
untracked duplicate tests; those passed but are excluded from tracked counts.

`summary.json` saves coverage, per-case outcomes, errors, request counts, model
digests, fixture hashes, and runtime source hashes. Raw replies remain local.
The run preceded the implementation commit, so hashes identify the evaluated
code. Request hashes do not prove model weights or server identity. No real
business tools were executed.
