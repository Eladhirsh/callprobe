# Comparing runs and CI gates

How to compare two runs, fail CI on regressions, use the GitHub Action, export JUnit reports, and compare two versions of a tool contract.

`callprobe compare A.json B.json` diffs two runs: per-category success and
type-lenient deltas, then which task ids went from passing every time they
ran to failing at least once, and vice versa. Useful for "did this change
help" between two runs of the same model, or between two models on the
same suite:

```bash
callprobe compare results/before.json results/after.json
```

It warns if the two runs' suite hashes differ, since part of the delta
could then be the suite changing rather than the model.

To save a readable report for review (since 0.9.0):

```bash
callprobe compare results/before.json results/after.json --format markdown > comparison.md
```

Markdown includes scored observation counts, request errors, category deltas,
and task changes. Categories without scored observations show `n/a`.
Targeted-run and provenance warnings remain in the saved report. Add
`--fail-on-regression` or `--policy` to include a CI verdict; without one,
the report says **not requested**. A failing gate still writes its report
and exits `1`, so shell scripts should preserve that status.

To enforce a baseline in CI:

```bash
callprobe compare results/baseline.json results/candidate.json --fail-on-regression
callprobe compare results/baseline.json results/candidate.json \
  --policy callprobe-policy.yaml --format json
```

The default gate rejects any previously passing `(task, pad, repeat)` case
that now fails and allows no request errors in either run. Both files must
have matching suite hashes and scoring versions, identical task/pad/repeat
coverage, and every planned result present. Different models and generation
settings are allowed: evaluating those changes is the purpose of comparison.
Incomplete, duplicate, legacy, or incompatible inputs cannot pass the gate.

A policy can set application-specific requirements (all rates are 0–1):

```yaml
fail_on_regression: false
critical_tasks: [args-partial-refund, abstain-missing-identifier]
min_success: 0.80
min_category_success:
  abstain: 0.95
max_success_drop: 0.02
max_error_rate: 0.01
```

Critical tasks must pass every candidate case, even if they failed in the
baseline. Success-drop comparisons use only cases with non-error results in
both files; candidate minimums use all its non-error results. Error limits
apply to each run separately. With no matched scored cases the gate fails.
Policies reject unknown fields, unknown task/category targets, and invalid
rates. Development builds also reject duplicate keys (including nested category
thresholds) and YAML merge keys, so a later entry cannot silently weaken a
threshold. Use explicit unique string keys. `--fail-on-regression` overrides a
policy's `false` setting.

Exit codes are `0` for a passing gate, `1` for policy violations, and `2` for
invalid inputs. Without a gate flag, `compare` remains an informational
comparison and supports older files. These gates apply deterministic
thresholds; they do not claim statistical significance for a change.

## CI mode

Development summaries distinguish **observations scored** (each task/pad/repeat
result without a request error) from **unique tasks scored** (distinct task IDs
with at least one scored result). JSON keeps the existing `n` observation count
and adds `unique_tasks_scored`. A task with only request errors is excluded from
both; a truncated response remains a scored failure. Repeats are not independent
new tasks. Historical text output in [the findings](findings.md) predates these labels.

`--format json` prints the summary (the same numbers as the text report)
as machine-readable JSON instead, and `--fail-under FLOAT` exits 1 when
overall success falls below that fraction:

```bash
callprobe run --model llama3.1:8b --format json --fail-under 0.7
```

When `--fail-under` is set, incomplete runs and request errors also fail CI,
even if the success rate of the remaining results exceeds the threshold.

`action.yml` at the repo root wraps this as a composite GitHub Action:

```yaml
- uses: Eladhirsh/callprobe@v0.9.1
  with:
    model: llama3.1:8b
    endpoint: http://localhost:11434/v1
    fail-under: '0.7'
```

It installs callprobe, runs it, and writes the JSON summary to the job's
step summary. `suite` and `api-key` inputs are optional; leave `suite`
unset to use the packaged core suite.

The action installs Callprobe from the selected action revision. Its
`baseline` input enables regression gating; `policy` optionally supplies a
YAML policy. Use `pad`, `repeats`, and `max-tokens` to configure the run.
For example, after checking out your repository and starting your endpoint:

```yaml
- uses: Eladhirsh/callprobe@v0.9.1
  with:
    model: your-model
    endpoint: http://localhost:11434/v1
    baseline: results/baseline.json
    policy: callprobe-policy.yaml
    pad: '0,8'
    repeats: '3'
    max-tokens: '4096'
```

Baseline inputs require v0.5.0 or newer. Keep the baseline separate from the action's
`callprobe-results.json` output. The action also writes
`callprobe-comparison.json` and includes it in the job summary.

Since 0.9.0, the Action additionally writes
`callprobe-comparison.md` and shows that readable report in the job summary,
with raw run output collapsed below its heading. Both comparison formats
come from the same saved results and policy; rendering does not call the
model again. A `fail-under` violation still produces the baseline comparison
before the Action exits with failure. Missing baseline/policy files and
paths that alias generated outputs are rejected before model requests.
Only reports produced by the current invocation appear in its summary.

## Try the workflow offline (since 0.9.0)

With 0.9.0 or later installed, try recorded results
without a model or endpoint:

```bash
callprobe demo --out callprobe-offline-demo
```

The command writes two historical runs, their matching 18-case suite, and a
walkthrough with commands to compare and explain failures. The candidate
passed 11/18 cases versus the baseline's 5/18, but regressed two previously
passing cases. The regression gate therefore exits `1`, as intended.

These are [recorded observations](../results/github-issues/README.md), not a
fresh execution or a current model ranking. `demo` needs no network after
installation. This command is not available in 0.8.0.

## Compare tool contracts (since 0.9.0)

Use `compare-contracts` when testing a schema or tool-description change against
**the same model and prompts**. This is an informational experiment report;
`compare --fail-on-regression` still requires the same suite hash.

Try a complete, offline example with historical Hermes3 results:

```bash
callprobe demo --contracts --out contract-demo
callprobe compare-contracts contract-demo/baseline.json contract-demo/candidate.json \
  --suite-a contract-demo/nested --suite-b contract-demo/flat --format markdown
```

The flat contract improved 27 observations and regressed two, despite its
higher aggregate success rate (38/54 versus 13/54). These are frozen synthetic
mail cases, not a MailOps integration test or a general ranking.

For your own contracts, preserve both suite directories and run each with the
same model, endpoint, padding, repeats, temperature, and token budget:

```bash
callprobe run --suite nested-suite --model qwen2.5:7b --pad 0 --repeats 3 --out nested.json
callprobe run --suite flat-suite --model qwen2.5:7b --pad 0 --repeats 3 --out flat.json
callprobe compare-contracts nested.json flat.json --suite-a nested-suite --suite-b flat-suite --format json
```

The command verifies each run's suite hash, scoring version, planned coverage,
case IDs, prompts, expected tool choices, tool order, distractors and recorded
model settings. It rejects incomplete or targeted runs. It reports errors and
truncations, excludes request errors on either side from paired scores, and
lists changed tools/assertions plus every improvement and regression.
Request-timeout differences are disclosed because they can affect errors.
Unknown provenance stays unknown; matching a model tag does not verify weights.

**Review changed assertions for equivalent meaning.** The command does not
prove semantic equivalence or rescore responses. It exits zero for a valid
report even when regressions exist; there is no gate option. After choosing a
contract, record a new baseline and use the ordinary same-suite CI gate.
This command requires 0.9.0 or later.

## Export JUnit reports (since 0.9.0)

Put saved CallProbe observations into your CI test-report viewer without making
another model request:

```bash
callprobe report results.json --format junit --out callprobe-junit.xml
```

Omit `--out` to write XML to stdout. Existing reports are protected unless you
pass `--force`; the source results file is always protected, including aliases.
Export exits zero when it successfully writes a report, regardless of test
outcomes. Your CI test reporter can interpret the XML; keep using `compare
--fail-on-regression` for matched baseline gates.

Each `(task, pad, repeat)` becomes a test case. Model failures and truncations
are failures; endpoint errors are errors. Missing observations add a coverage
error case, and old results without a recorded plan add an unknown-coverage
error case. Targeted debug runs are labeled and include a skipped coverage
notice, so they do not appear to be full benchmark runs.

Reports include model/task names and provenance but omit raw prompts, responses,
argument values, endpoint URLs, and server error messages. Use `explain` with
the original results and suite when you need detailed diagnostics. Reports can
still reveal names you put in task IDs or model labels; review those before
sharing. Recorded scores are never recomputed.

Since 0.9.0, the Action also writes `callprobe-junit.xml` when results are
available, even when a threshold or regression gate fails. Its `junit-report`
output contains the path only after export succeeds. Upload it with an
`if: always()` artifact or test-report step to retain failure evidence.

For a multi-model run, add `--junit` to export a report per model:

```bash
callprobe sweep --models qwen2.5:7b llama3.2:3b --suite my-suite \
  --out model-results --junit
```

The manifest links each successful export as `junit_file`. Partial result files
from failed or timed-out runs are exported too, with coverage errors in their
XML; they remain excluded from the successful-run leaderboard. An export
failure makes the sweep fail without discarding its original results.
`--dry-run --junit` only plans requests and writes no XML.

This feature requires 0.9.0 or later.
