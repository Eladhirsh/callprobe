# Local model smoke tests — September 30, 2026

Nine installed models were evaluated on core suite v2, scoring v3: 50 cases
per model, pad 0, one repeat, temperature 0, maximum completion tokens 4096,
concurrency 1, retries 0. All 450 observations completed with zero request errors
and zero truncation. Four also have earlier same-day observations on the
original 18-case synthetic mail suite. The model-server combination is what
was tested; these results do not establish a general model ranking.

## Evidence

- [Core leaderboard](core/leaderboard.md): all nine models, 450 observations.
- [Core diagnostic counts](core/diagnostics.json): categories can overlap.
- [Mail leaderboard](mail/leaderboard.md): four models, 72 observations.
- Raw observations: `core/*-result.json` and `mail/*-result.json`.
- [Model identities](model-provenance.json): local tags, digests, quantization.
- [Scoring source provenance](source-provenance.json): revision and file hashes.
- [Checksums](checksums.json): raw JSON files were copied without modification.

## A higher score can still regress

Qwen 3 passed 42/50 versus Qwen 2.5's 38/50, improving six cases but regressing
two: `abstain-no-such-capability` and `sequence-list-before-delete`. The matched
regression gate correctly fails. See the [comparison report](qwen-comparison.md)
and [machine-readable evidence](qwen-comparison.json).

Command R7B's 11 passing cases are abstentions; it produced no structured call
in all 39 cases expecting one. This describes the tested local model/server
configuration, not every deployment of that model.

## Different suites expose different weaknesses

| Model | Core | Synthetic mail |
| --- | --- | --- |
| qwen2.5:7b | 38/50 | 4/18 |
| llama3.1:8b | 15/50 | 5/18 |
| llama3.2:3b | 15/50 | 5/18 |
| command-r7b:latest | 11/50 | 6/18 |

These are different task sets; do not aggregate their scores into a single
ranking. Confidence intervals in the generated tables are wide, and one repeat
does not establish run-to-run reliability. Models use the local quantizations
listed in provenance; this is not a controlled architecture-only comparison.
No mail or other tool operations were executed.

## Reproduce

Use a development build containing `callprobe sweep`, with the listed model
digests already served by Ollama. From the repository root:

```sh
callprobe sweep --models command-r7b:latest llama3.2:3b hermes3:8b \
  phi4-mini:latest granite3.3:8b mistral-nemo:latest qwen2.5:7b qwen3:8b \
  llama3.1:8b --out /tmp/core-plan --dry-run
callprobe sweep --models command-r7b:latest llama3.2:3b hermes3:8b \
  phi4-mini:latest granite3.3:8b mistral-nemo:latest qwen2.5:7b qwen3:8b \
  llama3.1:8b --out /tmp/core-results --timeout 1200
callprobe leaderboard results/2026-09-30-smoke/core/*-result.json
callprobe explain results/2026-09-30-smoke/core/04-result.json \
  --suite src/callprobe/suites/core
```

The original run used the backwards-compatible script entry point. The public
command has the same generation settings. No model weights are downloaded by
this workflow. The 1200-second limit applies to each model subprocess.

## Provenance limitations

The core experiment used an editable installation whose package metadata still
said `0.5.0`, while its Python package pointed at the current source checkout.
That raw version label is preserved rather than rewritten. The source commit,
scoring-file hashes, suite hash, and scoring version identify the implementation.
Scoring and generation code stayed unchanged throughout the experiment; report
and CLI onboarding improvements were developed while the sweep ran.

The mail observations predate the clarification of the missing-ID prompt in
`mail-sandbox`. Their original suite hash is retained. The matching original suite is preserved in `mail/suite`; use it with
`callprobe explain`. These results cannot be used as a baseline for the revised
bundled example. They do not reproduce MailOps or the
external tester's reported 92% result. The mail cases need further independent
expectation review before being used for broader benchmark claims.

## Next experiments

Repeat promising model/suite combinations at the intended production settings,
then add distractor counts while keeping coverage and token budgets matched.
Investigate errors, truncation, response format, and ambiguous expectations
before expanding the experiment. Preserve every failure and collect a new run
after changing an adapter or contract; never rewrite recorded calls to pass.
