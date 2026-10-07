# Short mapping retry experiment

The shorter staged-mapping retry was rejected. The runtime has been restored to
the baseline; `rejected-candidate.patch` is evidence, not an applied change.

## Method

The 16 generated structured-plan controls from `examples/plan-validation`, plus
bundled cases 93 and 94, were frozen before inference. The unchanged baseline
and candidate each ran all 18 cases on installed Mistral Nemo and Qwen 2.5 models
at the configured local endpoint. Both used staged extraction, JSON mode,
temperature zero, and one repeat: 72 model evaluations and 36 paired comparisons.
No business tools ran. These are reused synthetic development controls, not
held-out accuracy or repeat-stability measurements.

The candidate changed only `invalid_action_map` retry guidance. It explicitly
requested a boolean completion flag, a tool name or null, and empty arguments.
Initial prompts, detail extraction, retry limits, validation, and scoring stayed
unchanged. First request hashes and first replies matched in all 36 pairs.
The fresh baseline was necessary because benchmark capture and input validation
had changed since the earlier experiment.

## Results

| Model | Baseline verdict matches | Candidate verdict matches | Baseline errors | Candidate errors |
|---|---|---|---|---|
| mistral-nemo:latest | 16 of 18 | 16 of 18 | 0 | 0 |
| qwen2.5:7b | 9 of 18 | 1 of 18 | 5 | 16 |

The comparison gate failed with nine regressions and one improvement. Qwen kept
argument values in its mapping retry, producing 16 `invalid_action_map` errors.
Its lower honest-alarm count is not an improvement: 12 of 13 honest controls
became incomplete checks. Mistral retained both known false alarms, including
an extra action from a mixed completion-and-plan message.

No broad candidate run followed these regressions. Neither this short hint nor
the [earlier longer hint](../2026-10-05-staged-plan-repair/README.md) solved the
mapping problem. Further work should test a different mapping interface and
preserve completion, plan, mixed-message, and vague-completion controls instead
of accepting an aggregate score increase. Staged extraction remains opt-in.

## Evidence and verification

`summary.json` records source and fixture hashes, coverage, per-case outcomes,
extraction errors, model inventory, and honest-control diagnostics.
`comparison.json` records the complete paired gate result. Raw replies remain
local. Verdict agreement does not establish full argument accuracy, and model
names or request hashes do not establish serving-process identity.

After restoring the runtime, all 1,465 Callprobe tests, 816 tracked Didyoureally
tests, package Ruff checks, and 102 labeled matcher cases pass. The preserved
local duplicate test file adds 48 passing tests excluded from tracked counts.
No release version, tag, package, or Marketplace listing changed.
