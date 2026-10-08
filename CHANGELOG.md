# Changelog

## Unreleased (0.9.0rc3.dev0)

- Preserve request errors for legacy function-call envelopes and provider refusals
  through Callprobe recording export and replay. Interrupted finish reasons and
  tool-call finishes without calls can no longer count as successful abstention.
  Valid modern calls and omitted finish metadata remain compatible.

- Save canonical request-body hashes with benchmark responses. Offline replay
  verifies each request, including recovery steps, and fails on mismatches.
  Older recordings remain explicitly marked as having unverified request identity.

- Treat explicit provider refusals as incomplete extraction in both default and
  staged modes, even when response content contains valid empty claims. Share
  response-envelope checks and keep provider refusal text out of diagnostics.

- Validate offline replay inputs before writing reports. Empty inputs, duplicate
  identities, malformed JSON, mismatched response arrays, staged recordings, and
  incomplete baseline extractions can no longer appear to pass replay.

- Reject legacy `function_call` fields and populated `functions` definitions in
  chat recordings instead of silently discarding them. Diagnostics explain how
  to normalize calls and results to the supported tool-message format.

- Add an offline model-run comparison gate with complete-coverage checks.
  Individual verdict regressions and candidate extraction errors fail the gate,
  even when improvements elsewhere increase the aggregate score.

- Report newly observed alarms on honest controls in saved model comparisons.
  The optional `--fail-on-new-honest-alarms` gate rejects them even when neither
  run matched its labels. Reports distinguish alarms after baseline extraction
  errors from completed baseline observations. Default gate behavior is unchanged.

- Add eight frozen mixed-action controls and record a rejected extraction-prompt
  experiment. Focused improvements did not outweigh broader completion omissions;
  the runtime prompt remains unchanged.

- Reject duplicate JSON keys, nonfinite numbers, invalid encoding, and excessively
  nested JSON in agent suite files before model requests or output creation.
  The runner and saved-run comparison share the same strict input reader.

- Allow one focused recovery when argument repair drops grounded target details.
  Preserve ordinary repair behavior and the maximum of three model calls per
  message. Recovery uses only the original target and grounded details; prior
  conversation values and execution evidence stay hidden. Unrecovered details
  still produce incomplete extraction errors.

- Add repeated extraction diagnostics to the development benchmark runner.
  Record repeat coverage, mixed exactness, changes in claims and outcomes, and
  incomplete attempts while keeping same-named endpoint targets separate.
  Include eight fresh paired cases for repeated model validation.

- Validate supplied claim collections, fields, and explicit assistant-message
  references before matching. Malformed reviewed claims now return input errors
  instead of silently dropping claims or letting future and non-assistant
  positions back earlier statements. Claims without positions resolve only
  when there is exactly one nonempty assistant message, and still require
  earlier execution. Ambiguous manual claims require explicit message indices;
  reviewed baselines relying on session-wide matching should be regenerated.

- Validate imported chat message shapes and tool-call ownership. Reject malformed
  containers, unknown roles, unsupported content parts, and calls attached to
  non-assistant messages before extraction. Preserve valid text and refusal
  parts, empty assistant call turns, and result ordering with clear input errors.

- Validate native trace structures before extraction. Reject duplicate call IDs
  and tool definitions, nonboolean side-effect flags, and malformed argument or
  message shapes. Check call identity again in the matcher so an unreported
  action cannot disappear behind a reused ID. Valid traces retain their scores.

- Reject duplicate JSON keys, nonfinite values, and malformed recorded arguments
  at Didyoureally input boundaries. Ambiguous tool outcomes cannot silently
  become successful execution. Preserve valid nested results and plain-text
  success markers; invalid recordings exit as input errors before extraction.

- Clarify completed-action scope in both Didyoureally extraction modes and repair:
  attempts do not multiply successful actions, and JSON plans do not assert
  execution. Preserve genuinely repeated successes and completed actions in mixed
  replies. Add paired retry-count and prospective-JSON benchmark controls.

- Preserve explicit date, time, and UTC-offset claims in Didyoureally extraction
  and repair. Compare supported prose timestamps with their ISO representations
  without guessing missing details. Add wrong-date and honest benchmark controls.
  Saved claims stay unchanged; rerun extraction for the new date coverage.

- Add `parse_ollama_completion` for native, completed non-streaming `/api/chat`
  recordings. Preserve calls, thinking, usage, and truncation through the existing
  offline scoring/export APIs; reject malformed, partial, and lifecycle responses.

- Validate the complete suite before `run` or `run --dry-run`, including unused
  distractors and expected arguments. Invalid suites exit before endpoint access
  or output changes; use `validate --suite DIR` for detailed diagnostics.

- Reject `run --out` destinations that name or alias suite definition files,
  including config-relative paths and packaged-suite files, before endpoint
  access. Obvious output-directory conflicts also fail before generation.
  Ordinary result replacement and resuming into the same result file still work.

- Reject ambiguous duplicate keys and nonfinite numbers in string-form tool
  arguments, including nested values and overflowing float literals. Preserve
  the original argument string as parse-failure evidence instead of silently
  accepting it. Re-run affected baselines: already-saved scores are not rewritten.

- Filter offline `explain` diagnostics by `--pad` and zero-based `--repeat`,
  optionally combined with `--task`. Counts and repeat-variation summaries
  describe only the explicitly labeled selection; saved results are unchanged.

- Add `recordings_to_json(config, recordings)` to export application completions
  in the offline replay v1 format. It validates before returning JSON, preserves
  decision evidence, and excludes raw provider bodies and connection settings.

- Validate Python recorded-completion inputs before scoring any item in a batch.
  Invalid adapter types cannot become successful abstentions, and invalid token
  or latency metadata cannot corrupt reports. Valid errors and malformed-tool
  parse evidence retain their existing scores; the scoring rubric is unchanged.

- Support `python -m callprobe` for all CLI commands, using the selected Python
  environment even when the console script is not on `PATH`. Command output and
  exit codes match the `callprobe` executable.

- Reject invalid provider token counts instead of rounding fractions, accepting
  negatives, or treating booleans/containers as usage. Valid integer strings
  and integral floats remain supported; absent or null usage still defaults to
  zero. Malformed usage becomes a request error, never a corrupted cost total.

- Let `doctor --config FILE` use the same model, endpoint, and suite defaults as
  `run`, with CLI overrides and config-relative suite paths. Diagnostics remain
  read-only, use their own short timeout, and ignore run output settings.

- Reject malformed provider text, usage containers, and argument types even
  when their values are false or empty. Invalid response envelopes become
  request errors instead of successful abstentions or empty-argument calls;
  valid null fields and malformed JSON argument-string scoring are unchanged.

- Add offline `replay` for versioned normalized recordings JSON, with strict
  input validation, protected source/suite files, and atomic output writes.
  A synthetic support example demonstrates partial coverage without a model.

- Add a Python API to score recorded application completions without an HTTP
  proxy. It uses the existing rubric, preserves incomplete/targeted coverage,
  and rejects duplicate or out-of-plan observations before scoring.

- Flag malformed saved coverage plans in text, JSON, and leaderboard summaries.
  Duplicate tasks/pads and invalid targeted selections no longer appear complete;
  recorded scores and legacy unknown-plan support remain unchanged.

- Add offline `report --format text|json` summaries for saved runs, preserving
  the JUnit default and source/output protections. Summary exports omit endpoint
  URLs and raw evidence; run summaries now show scored/recorded/planned coverage.
  Invalid saved-result diagnostics identify fields without echoing their values.

- Speed up confidence intervals for repeated runs by accumulating per-task
  counts before bootstrap sampling. Task-level resampling, fixed seeds, and
  interval values remain identical to the prior row-pooling calculation.

- Reject duplicate and YAML merge keys in CI policies instead of silently
  replacing thresholds. Policies and run configuration share safe mapping
  parsing; syntax/type errors report context without configured values.

- Distinguish scored observations from unique scored tasks in run summaries.
  JSON retains `n` and adds `unique_tasks_scored`; repeated/padded observations
  and request errors cannot inflate the distinct-task count.

- Add `callprobe doctor` for suite and endpoint setup diagnostics using model
  discovery and public server metadata only. No generation, downloads, retries,
  redirects, or output files; unavailable catalogs remain inconclusive warnings.

- Validate CI gate coverage by membership and count without expanding planned
  repeats into memory. Very large incomplete plans fail promptly, with accurate
  missing/unexpected counts and unchanged complete-run gate behavior.

- Validate a second serving backend with 154 live Qwen2.5 observations through
  llama.cpp, archived with full coverage, suite snapshots, and offline report
  checks. Both cross-backend regression gates detect case regressions despite
  higher totals; differing templates/settings preclude a causal ranking.

- Include recorded server name and version in text and Markdown comparisons,
  without exposing endpoint URLs or inferring missing backend identities.

- Treat every non-null request error, including an empty error message,
  consistently across scoring, reports, comparisons, CI gates, and resume.
  Endpoint failures cannot count as successful abstentions or cached results.

- Recognize llama.cpp build metadata for run provenance and resume checks;
  unknown or protected server metadata remains unset.

- Add `repeat_variation` to `callprobe explain` (JSON and text) that groups
  observed records by `(task_id, pad)` and reports mixed-outcome groups with
  passing/failing repeat ids and any excluded request-error repeats. Pads are
  never mixed, `--task` scopes the summary, duplicate `(task,pad,repeat)` rows
  are rejected, and the caveat explains that tool-order changes prevent
  isolating model randomness.

- Archive 1,386 live observations across nine local model configurations, with
  repeated core cases, mail padding sweeps, and verified offline CI reports.

- Save sweep manifests atomically so interrupted writes preserve the last
  complete checkpoint.

- Add opt-in `sweep --junit` reports for each model, including preserved partial
  results after failed runs; manifest links distinguish successful exports.

- Add offline JUnit export for saved results, with model failures, endpoint errors,
  incomplete coverage and targeted debug scope represented explicitly. Raw
  responses and argument/error values are omitted from exported diagnostics.

## 0.9.0rc2

Published tester prerelease on 2026-10-01.

- Add offline `compare-contracts` for controlled schema/description experiments:
  verify matching suite snapshots, prompts, model settings and full coverage;
  report paired regressions, errors and changed assertions without weakening
  the existing same-suite CI gate. Scores remain recorded, never rescored.
- Add `demo --contracts` with frozen Hermes3 nested/flat runs and matching suites.
  The higher-scoring contract still has two regressions; no endpoint is needed.
- Add configurable HTTP request timeouts to `run` and `sweep`, including YAML
  defaults, dry-run plans, and recorded run metadata. The default remains 120
  seconds; historical files without this field remain readable.
- Make the two literal-text mail example cases explicitly ask to send a reply,
  aligning the prompts with their expected send mode. This changes the active
  example suite hash: generate a fresh suite and baseline. Archived benchmark
  suites and responses retain their original wording and results.

### Upgrading from rc1

- Scoring remains **version 3** and padding still defaults to **zero**. Existing
  version-3 baselines remain usable when the suite and model settings match.
- The regenerated `mail-sandbox` example has two clarified send instructions.
  Preserve old results with their original suite snapshot. Generate a fresh
  suite and baseline for the updated example; never edit old hashes or verdicts.
- `compare-contracts` is informational and accepts deliberate contract changes
  only with matching prompts and experimental controls. It does not migrate
  baselines, prove assertion equivalence, or replace the same-suite CI gate.
- Runs now record the HTTP request timeout. Older files keep `null` (unknown);
  transport timeout differences are disclosed by contract comparisons.
- Users upgrading from 0.8.0 or earlier must also follow the rc1 scoring and
  padding migration notes below.

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
