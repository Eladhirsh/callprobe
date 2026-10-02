# Repeated local-model validation — October 1, 2026

This experiment tests a fixed installed CallProbe `0.9.0rc3.dev0` wheel
against nine locally installed Ollama model configurations. It evaluates
responses only: no proposed tool or mail operation is executed. Models were
already installed; the experiment downloads no weights.

## Completed results

All 1,386 planned observations were recorded (900 core + 486 mail).
There were **zero request errors and seven token-limit truncations**, all scored
as failures: one Qwen3 core case, one Llama3.1 mail case, and five Phi-4 Mini
mail cases. Model digests were unchanged from start to finish.

| Model | Core (out of 100) | Mail pad 0 (out of 18) | Mail pad 2 | Mail pad 4 |
| --- | ---: | ---: | ---: | ---: |
| qwen2.5:7b | 79 | 4 | 7 | 7 |
| llama3.2:3b | 31 | 5 | 7 | 8 |
| hermes3:8b | 55 | 5 | 4 | 4 |
| granite3.3:8b | 51 | 9 | 8 | 11 |
| llama3.1:8b | 31 | 5 | 5 | 8 |
| mistral-nemo:latest | 60 | 12 | 8 | 8 |
| command-r7b:latest | 22 | 6 | 6 | 6 |
| phi4-mini:latest | 22 | 6 | 5 | 6 |
| qwen3:8b | 85 | 9 | 14 | 12 |

These are 50 core cases repeated twice and 18 mail cases under three padding
settings per model, not 1,386 unique tasks. All requests use one local Ollama
backend; this does not validate other providers or a live MailOps integration.

[Full analysis](evidence/analysis.md) · [Machine-readable analysis](evidence/analysis.json)
· [Coverage check](evidence/coverage-check.json)

The final installed feature wheel passed 18 JUnit counter checks, 18 comparison
report checks, and 18 offline resume checks covering every saved observation.
Three comparison gates pass and 15 fail as expected; every gate result matches
the independent raw-case calculation. Export and resume preserve raw files.
See [comparison checks](evidence/comparison-checks.json),
[resume checks](evidence/resume-checks.json), and [file hashes](evidence/checksums.json).

## Core findings

Qwen3 recorded 85/100 successful observations, compared with Qwen2.5’s 79/100.
Those totals each cover 50 cases repeated twice, not 100 independent tasks.
The [matched comparison](evidence/comparisons/core-01-vs-09.md) still fails the
regression gate: five previously passing observations regressed despite the
six-percentage-point overall improvement.

Repeated totals also hide changes within a model. Granite moved from 24/50 to
27/50 while 11 case verdicts changed; Phi-4 Mini stayed at 11/50 while two
verdicts changed. Tool order changes between repeats, so this does not isolate
sampling randomness. Case-level results remain the source of truth.

## Conditions

- Core: 50 cases, pad 0, two repeats per model (900 planned observations).
- Updated fictional mail suite: 18 cases, pads 0/2/4, one repeat (486 planned).
- Temperature 0, max completion tokens 4096, concurrency 1, retries 0.
- HTTP operation timeout 180 seconds; each sweep step has a 3600-second timeout.
- Frozen suite snapshots, server version, model digests and quantization are
  under `evidence/`; `source.json` identifies the exact source and wheel hash.
  `evidence/runtime.json` records the live environment’s Python and package versions.
- The two core repeats use different deterministic tool-order seeds. Differences
  therefore include tool-order effects, and are not a pure randomness measure.
  Padding also participates in tool-order seeding: per-padding differences
  combine distractor selection/count and order, rather than isolating one cause.
- Server defaults govern context sizing. Model architecture and quantization
  vary; these are configuration-level observations, not a controlled comparison
  of architectures or a general model ranking.
- Core and mail scores describe different cases and must not be pooled into
  a headline model score. Repeated cases are not independent new tasks.
- Latencies reflect a shared local machine and are not throughput benchmarks.

## Evidence and report verification

`evidence/core/` and `evidence/mail/` retain raw result JSON, step logs,
per-model diagnostics and the generated leaderboards. Model request errors
remain distinct from scored failures; no recorded score is repaired.

`analyze.py` exports each recorded file as JUnit and verifies case, failure
and error counts against the raw fields, including missing-coverage errors.
It verifies raw-file hashes before and after export. Its JSON output includes
per-padding and per-repeat counts, diagnostic categories (which can overlap),
and the task IDs whose verdicts changed between core repeats.

The analyzer was also checked against archived real request errors and
truncations. The source tests separately exercise all-request-error sweeps,
failed/timeout checkpoints, and the absence of extra model calls during export.

## Reproduce

Install the source revision in `source.json` in an isolated environment, with
all nine listed model tags already served by Ollama at `127.0.0.1:11434`.
From this directory, use that environment's Python:

```bash
/path/to/python run_validation.py /path/to/new-evidence-directory
/path/to/python analyze.py /path/to/new-evidence-directory
```

The output directory must be new. The runner records both planned and actual
outcomes; inspect its manifest for failed steps rather than assuming every
planned request completed. The analyzer makes no network requests.

After the experiment, also run:

```bash
/path/to/python verify_resume.py /path/to/new-evidence-directory
/path/to/python verify_comparisons.py /path/to/new-evidence-directory
```

The resume check blocks socket connections and model calls, stubs server identity
to its recorded value, and confirms that complete error-free runs retain every
observation and pass a self-comparison gate. Runs with request errors are excluded
because resuming them intentionally retries those requests. The comparison check
independently pairs raw observations and verifies both report formats’ exit codes and the JSON report’s matched
counts, regression IDs, and deltas for each model against Qwen2.5 within each suite.
Expected model regressions remain failing gates; they are not test-harness errors.

The final feature wheel also passed `verify_installed.py`: a separate scripted
HTTP smoke test from outside the checkout, with 54 requests across passing,
regressing, and unavailable synthetic model names. The source and wheel hash
are recorded separately in `source.json`; these are not live-model scores.
To repeat this check, run the script with the final installed wheel’s Python
and pass a new JSON output path.
