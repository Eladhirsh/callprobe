# Changelog

## Unreleased (0.9.0rc2.dev0)

- Add configurable HTTP request timeouts to `run` and `sweep`, including YAML
  defaults, dry-run plans, and recorded run metadata. The default remains 120
  seconds; historical files without this field remain readable.
- Make the two literal-text mail example cases explicitly ask to send a reply,
  aligning the prompts with their expected send mode. This changes the active
  example suite hash: generate a fresh suite and baseline. Archived benchmark
  suites and responses retain their original wording and results.

## 0.9.0rc1

Published tester release candidate.

- Add an offline `demo` with recorded evidence, its matching suite, and a
  regression-gate walkthrough. No endpoint or API key is required.
- Add `sweep` for already-served models, with preflight plans, per-model results,
  a manifest, and a leaderboard. Add `run --dry-run` for offline request budgets.
- Bundle the 18-case fictional mail example; improve schema validation and
  diagnostics for nested arguments and tool-shaped assistant text.
- Export readable Markdown comparisons and CI summaries, retaining evidence
  even when a quality gate fails. Show incomplete coverage in leaderboards.
- Record reproducible nine-model smoke evidence, without treating single runs
  as a general model ranking.

### Upgrade and baseline migration

- New runs use **scoring version 3**. Lenient integer coercion no longer truncates
  fractional strings or loses large-integer precision. Strict scoring is unchanged.
  Historical files keep their verdicts and remain readable; compatible version-2
  files can still be compared with each other. Gates, resume, and `--failed-from`
  reject mixed scoring versions. Rerun both baseline and candidate under this
  version with the same suite and settings, using new output files. Never edit
  old scoring-version labels to migrate them.
- `run` and the GitHub Action now default to **`--pad 0`**, replacing `0,8,16`.
  Padding that cannot fit every selected task is rejected before endpoint access;
  old releases could silently cap it. Choose explicit valid counts (for example
  `--pad 0,8` for core or `--pad 0,2,4` for mail) and collect fresh baselines.
  Old silently capped observations must not be relabeled as new runs.
- The offline demo deliberately retains its historical version-2 evidence.
  Compare its two bundled files together rather than using them as new baselines.

## 0.8.0

- Add bundled support and GitHub Issues examples, saved YAML run settings, and
  targeted reruns with `--failed-from`.

## 0.7.0

- Add offline `explain RESULTS.json --suite DIR` diagnostics with task filtering
  and text/JSON output. Reports prompts, actual calls, assertions, and recurring
  failure types from a matching saved run and suite.
- Suggest unambiguous nested argument shapes only when the complete candidate
  validates. Suggestions preserve values and never change scores or execute calls.
- Reject mismatched suites and unknown task IDs; distinguish empty runs and
  request errors. Schemas that cannot be inspected offline keep their recorded
  failure reasons without speculative hints.

## 0.6.0

- Add offline OpenAPI 3.0/3.1 import through `init --from-openapi`, with local
  references, grouped parameters and JSON request bodies, operation filtering,
  import diagnostics, and explicit skipping of unsupported operations.
- Generate editable test drafts and a suite walkthrough; protect existing
  suite files unless `--force` is supplied.
- Include a small support API with six human-authored tests for an end-to-end
  import, validation, model evaluation, and baseline-comparison walkthrough.

## 0.5.0

- Scoring version 2 requires exactly one call for call expectations and
  rejects truncated responses, including apparent abstentions. Lenient
  coercion cannot rescue either failure.
- Preserve all structured calls, IDs, raw arguments, parse errors, and
  finish reasons in result files.
- Reject incompatible or missing resume files; preserve the original start
  time, retry request errors, and write checkpoints atomically.
- Add `compare --fail-on-regression`, YAML `--policy`, and JSON comparison
  output. Gates require complete matched coverage and compatible suite and
  scoring provenance. Policies cover critical tasks, overall/category
  minimums, maximum success drops, and request error limits.
- Fail `run --fail-under` on request errors and incomplete runs. Reject
  mixed scoring versions in leaderboards by default.
- Add GitHub Action baseline/policy and run-configuration inputs; install
  the selected action revision instead of an unrelated PyPI version.
- Include two fresh 150-request Qwen 2.5 7B validation runs, an example CI
  policy, and a report of the six false passes prevented per run. Both
  runs scored 78.7% with no matched-case regressions.

Older results remain readable for informational comparison. Rerun them
before resuming or using them as CI baselines with this rubric.

## 0.4.0

First public release.

- Package the default suite inside the wheel, so `pip install callprobe`
  works outside a git checkout. Previously the packaged CLI could not find
  `suites/core` at all.
- Add `callprobe validate [--suite PATH]`, which checks task expectations
  against tool schemas without needing a model.
- Add CI: pytest on Python 3.10 through 3.13, plus a wheel-install smoke
  test that would have caught the packaging bug above.
- Retry request errors (429, 5xx, connection and timeout errors) with
  exponential backoff and jitter instead of scoring them as model failures.
  Configurable with `--retries` (default 3). Reports honor `Retry-After`.
- Reports now exclude errored requests from every success/selection/schema
  /args rate, and warn when errors exceed 2% of requests. Error counts are
  still shown.
- Stop tracking log files and the overnight sweep log in git.
- Add `__version__` and `callprobe --version`.
- `--api-key` falls back to `API_KEY`, then `OPENAI_API_KEY`.
- Add PyPI packaging metadata (urls, keywords, classifiers, authors) and a
  trusted-publishing release workflow.
