# Structured plan retry experiment

The proposed staged-extraction retry hint was rejected. Runtime extraction
remains byte-identical to the baseline. This change retains the frozen controls,
comparison evidence, and rejected patch so later work can reproduce the problem.

## Frozen cases and method

The generator `packages/didyoureally/scripts/build_plan_validation.py` creates
16 controls across email, files, support, and scheduling. Each domain includes a
pure proposed call, a claimed execution without evidence, an honest execution,
and an honest execution followed by a proposed call. Four fixture tests check
frozen output and deterministic verdicts. The original numbered JSON plan and
completion pair, cases 93 and 94, brings the evaluation to 18 unique cases.

Cases were frozen before inference. Both the unchanged baseline and the candidate
ran all 18 cases on the configured local Mistral Nemo and Qwen 2.5 models, with
staged extraction, JSON mode, temperature zero, and one repeat. This produced
72 fresh model evaluations and 36 paired comparisons. No real business tools
were executed. These are synthetic development controls, not broad accuracy
estimates or stability measurements.

The candidate changed only the invalid-action-map retry hint. It asked the model
to reconsider whether listed calls asserted completed work and showed the full
mapping schema. Initial request hashes and first replies were identical in all
36 pairs. Scoring, initial prompts, retry limits, and the detail stage stayed
unchanged. Runtime source hashes and model digests are saved in `summary.json`.

## Results and rejection

| Model | Baseline verdict matches | Candidate verdict matches | Baseline extraction errors | Candidate extraction errors |
|---|---|---|---|---|
| mistral-nemo:latest | 16 of 18 | 17 of 18 | 0 | 0 |
| qwen2.5:7b | 9 of 18 | 4 of 18 | 5 | 14 |

Mistral's original numbered future-plan case improved, but its mixed email case
still produced an extra claim. Qwen improved on four pure-plan controls while
regressing nine previously passing completion controls. Its invalid mappings
continued to include arguments during the mapping stage. The apparent removal
of Qwen false alarms came with more incomplete checks, not reliable clean results.

The complete-run comparison gate returned exit code 1: five improvements, nine
regressions, and 14 candidate errors. No broad candidate evaluation was justified
after these focused regressions. The runtime change was restored before final
verification. `rejected-candidate.patch` records the discarded experiment; it is
not applied to the package.

## Verification and remaining work

Final checks pass: 1,465 Callprobe tests, 767 tracked Didyoureally tests, package
Ruff checks, and 102 labeled matcher cases. The preserved local duplicate test
file contributes another 48 passing tests, excluded from tracked counts.

The next extraction experiment needs to improve completion classification while
preserving the mapping format and real completed actions. It must also handle
the detail stage inventing an additional vague action in mixed messages. Retain
both models and paired honest controls when evaluating any replacement.

`comparison.json` contains safe paired diagnostics. `summary.json` saves coverage,
errors, per-case outcomes, source and fixture hashes, and model digests observed
after the run. Raw responses remain local. Verdict agreement does not establish
complete argument extraction, and model names or request hashes do not establish
server identity. No release version, tag, package, or Marketplace listing changed.
