# callprobe

Test whether a model can actually call **your** tools.

Every local model claims tool calling support. Existing leaderboards test
somebody else's function schemas. `callprobe` points at any
OpenAI-compatible endpoint, runs your own tool definitions against it, and
tells you where it breaks.

```bash
pipx install callprobe
callprobe --version

callprobe run --model qwen3:8b --endpoint http://localhost:11434/v1
```

```
model            qwen3:8b
endpoint         http://localhost:11434/v1
tasks scored     408

                 selection   schema     args      success
  overall         93.1%   93.6%   89.0%   88.7%
  type-lenient    93.1%   93.6%   89.0%   88.7%

  tool count sweep
    +0   distractors   success  89.2%   selection  95.1%   sd  1.4
    +8   distractors   success  90.2%   selection  94.1%   sd  1.4
    +16  distractors   success  87.3%   selection  90.2%   sd  5.5
    +24  distractors   success  88.2%   selection  93.1%   sd  2.4

  by category
    abstain     88.6%  (n=132)
    args        87.5%  (n=144)
    depth       97.2%  (n=36)
    select      86.1%  (n=72)
    sequence    91.7%  (n=24)

  cost per success   1568 tokens   14.57 s
```

That is a real run: 34 tasks, 4 tool-count levels, 3 repeats, 408 requests
against qwen3:8b. Full results for every model tested are in
[`LEADERBOARD.md`](LEADERBOARD.md) and the raw per-task JSON in `results/`.

<!-- TODO: terminal recording of a run here -->

## Results so far

The table below preserves the original suite-v1 runs. For the v0.5.0
scoring rules and a matched real-model baseline/repeat, see the
[release validation report](results/v0.5.0/README.md).

| model | success | type-lenient | abstain | tokens/success |
| --- | --- | --- | --- | --- |
| qwen3:8b | 88.7% | 88.7% | 88.6% | 1568 |
| llama3.1:8b | 32.1% | 51.2% | 9.8% | 3441 |

<!-- TODO: chart image here, e.g. the tool-count curve across models -->

Two findings worth reading past the ranking:

**Abstention is the gap that costs money.** Asked eleven questions with no
correct tool to call, qwen3:8b declined correctly 88.6% of the time.
llama3.1:8b declined correctly 9.8% of the time. Asked about a return
policy, it called `issue_refund`; asked to change an email address, it
called `update_shipping_address`. Nine times in ten it acted when it should
have asked a question. That is the failure mode that reaches production,
and almost no existing benchmark measures it.

**Type coercion masks a real capability.** 19.1% of llama3.1:8b's calls
were computed correctly and serialized wrong: `"1299"` instead of `1299`,
an array delivered as a JSON-encoded string. Score those leniently (cast
strings to the type the schema declares, never touch the value) and success
jumps from 32.1% to 51.2%. Roughly half of what looks like a reasoning
failure is a formatting bug in the serving layer, not the model being
unable to do the task. `callprobe` reports both numbers so you can tell
which one you're looking at (see `type-lenient` in the output above and
the full row in the table).

## Why three scores instead of one

`selection`, `schema`, and `args` fail for different reasons, and the gap
between them is the whole point.

- **selection** picked the right tool, or correctly called nothing
- **schema** the arguments validate against the tool's JSON Schema
- **args** the values are actually right

A model with high selection and schema but low args is the dangerous case.
It emits well-formed calls with wrong values, which pass every check most
people currently run. That is the failure that reaches production.

Alongside strict scoring, every result also gets a **lenient** pass: string
values are cast to the type the schema declares (`"10"` → `10`), then
rescored. Lenient can only rescue a strict failure, never create one. The
gap between the two numbers tells you how much of a model's failure is
serialization rather than reasoning.

A `call` expectation requires **exactly one call**. Returning a correct call
alongside extra calls fails both strict and lenient scoring. Truncated
responses also fail, including responses with no calls: reaching the token
limit is not evidence of deliberate abstention. Selection, schema, and
argument scores still diagnose the selected call independently.

New run files record `scoring_version: 2`. Older files remain readable,
but must be rerun before use as CI baselines or resumed checkpoints; the
scoring changes can affect their success rates. Leaderboards reject mixed
scoring versions unless `--allow-mixed` is supplied.

## What it measures that other harnesses do not

**Abstention.** Roughly a third of the suite is tasks where the correct
behavior is to call nothing and ask a question. Models vary enormously here
(see Results above), and almost nobody tests it.

**Tool count.** Accuracy with 5 tools tells you little about accuracy with
25. `--pad` adds plausible but irrelevant tools from a distractor pool and
reports the curve. Tool order is shuffled per run, because position bias is
real and should not be allowed to hide. Tasks can declare
`exclude_distractors` for tools that would make the expected answer wrong.

**Conversation depth.** Turn one accuracy is not turn nine accuracy.

**Variance.** Tool calling is not deterministic even at temperature 0.
`--repeats` runs each task more than once and reports a standard deviation,
so you get a number with an error bar instead of a number. At temperature 0
the repeats mostly aren't re-rolling the model's reasoning, they're
re-rolling the shuffled order tools appear in, so the standard deviation you
see per tool-count level is mostly a position-sensitivity measurement, not
noise.

Every success rate also gets a 95% bootstrap confidence interval, shown in
the text report and as a column in the leaderboard table. The resampling
unit is the task id, not the individual result: repeats of the same task
are correlated with each other rather than independent trials, so
resampling individual results would understate the real uncertainty. A
category with only a couple of task templates will show a wide interval,
sometimes a degenerate one, and that is the interval telling you honestly
that there isn't enough data yet, which is also why growing the thin
categories matters more than chasing a tighter number on the current ones.

**Cost per success.** Tokens and seconds divided by *correct* calls. Raw
latency flatters models that fail quickly, and rewards models that fail
cheaply over models that succeed expensively. In the table above,
llama3.1:8b is faster per request but costs more than twice as much per
usable call.

## callprobe vs. the Berkeley Function Calling Leaderboard

[BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html) is the standard
reference for tool-calling benchmarks, and it does two things `callprobe`
does not try to: scale (thousands of examples across many languages and
call styles) and model coverage (a maintained public leaderboard with
broad submissions, updated as new models ship). If you want to know how a
model ranks against the field on a shared, independent benchmark, BFCL is
the better source.

`callprobe` is a different tool for a different question: not "how does
this model rank," but "does this model reliably call *my* tools." That
shows up in what it measures that BFCL does not: your own tool schemas
instead of a fixed public set, abstention as a first-class category, a
tool-count curve that shows where a model's accuracy actually falls apart
as you add tools, cost per success instead of raw latency, and lenient
type scoring that separates a serialization bug from a reasoning failure.
Run both. They answer different questions.

## Why your tool-calling numbers are probably wrong

Four ways a tool-calling evaluation lies to you. All four were caught by
running this harness against real models and noticing a number that made
no sense, not by reasoning about it in advance.

**Truncation scored as incapability.** Reasoning models spend tokens
thinking before they emit a call. If the budget runs out mid-thought, the
response contains no tool call, and a harness that does not check
`finish_reason` records that as a model that cannot call tools. Measured on
qwen3:8b over the same twelve tasks: 66.7% success at a 512 token budget,
91.7% at 4096. Nothing about the model changed. Worse, the bias is
strongest on the hardest tasks, because hard tasks think longer, so the
measurement degrades exactly where it matters. `callprobe` reports a
`truncated` count and names truncation as its own failure.

**Type coercion masks correct reasoning.** Covered above: 19.1% of one
model's failures were formatting, not reasoning. Reported separately as a
`type-lenient` score rather than silently folded into either number.

**Padding that invalidates the task.** Adding irrelevant tools is how you
measure degradation with tool count. But if one of those tools genuinely
answers the question, an abstention task quietly stops being an abstention
task. An early sweep marked a model wrong for calling
`search_knowledge_base` on a policy question. The model was right and the
padding was the bug.

**Underspecified argument semantics.** "Next week" has no fixed start day.
An `end_date` with no stated inclusivity has two correct answers. Every
ambiguity left in a prompt or a tool description becomes a scoring error
you will misattribute to the model.

The general lesson: at small suite sizes, a tool-calling benchmark measures
its author as much as the model. That is why the failure digest prints what
actually happened, not just a rate. The failures worth reading first are
usually your own.

## Bring your own tools

### Start from an OpenAPI document (since 0.6.0)

Import a local OpenAPI 3.0/3.1 YAML or JSON file:

```bash
callprobe init --from-openapi openapi.yaml --out my-suite
# Edit my-suite/tasks.yaml: uncomment drafts and write expected behavior.
callprobe validate --suite my-suite
callprobe run --suite my-suite --model qwen2.5:7b --pad 0 --out baseline.json
```

The importer keeps `path`, `query`, `headers`, `cookies`, and `body` arguments
separate, resolves local references, and writes an operation map and diagnostics
to `import-report.json`. Unsupported operations fail the import by default;
`--skip-unsupported` explicitly omits them. Use `--tag TAG` to select operations.
Existing suite files are protected unless you pass `--force`.

Generated tasks are commented drafts; they do not invent correct answers from
the schema. A suite with no active tasks cannot be validated as ready to run.
Try the [six-test support API walkthrough](examples/openapi/README.md) for a
complete example with human-authored expectations. The imported API is never
executed, and no API credentials are needed.

For a real API contract, try the [GitHub issue and comment evaluation](examples/github-issues/README.md):
18 authored cases against three operations from a pinned copy of GitHub's
official OpenAPI specification. It covers identifiers, pagination, comment
text, conversation corrections, and abstention without executing GitHub calls.

`--from-openapi` is available since 0.6.0. Install it with
`uv tool install callprobe@latest`. Earlier versions only support `--from tools.json`.

### Write a suite directly

A suite is three YAML files. Drop your real tool schemas into `tools.yaml`,
write tasks against them, and run.

```yaml
# tasks.yaml
tasks:
  - id: args-partial-refund
    category: args          # select | abstain | args | depth | sequence
    bundle: support
    messages:
      - role: user
        content: >
          Order ORD-991003 came to $84.50 and one of the two mugs was
          cracked. Refund me for just the broken one.
    expect:
      type: call
      tool: issue_refund
      args: {order_id: ORD-991003, reason: damaged}
      arg_checks:
        - {path: amount_cents, op: eq, value: 4225}
```

`args` is exact match on the keys you list. `arg_checks` is for everything
else: `eq`, `neq`, `in`, `contains`, `gte`, `lte`, `matches`, `exists`,
`absent`, over dotted paths like `address.postal_code`. Anything you do not
assert is judged by the schema alone.

For a task where calling nothing is correct:

```yaml
    expect:
      type: no_call
```

Add `exclude_distractors: [tool_name]` to a task if padding could hand the
model a tool that would make the expected answer wrong.

Already have your tools as an OpenAI-format `tools.json`? Scaffold a suite
from it instead of writing `tools.yaml` by hand:

```bash
callprobe init --from tools.json --out my-suite
```

This writes `tools.yaml`, an empty `distractors.yaml`, `suite.yaml`, and a
`tasks.yaml` with one commented example call task per tool and a `no_call`
stub, ready to uncomment and fill in.

Once you have tasks, check them before spending a single token on a model:

```bash
callprobe validate --suite my-suite
```

It checks that every key and value you asserted in `args` or `arg_checks`
actually exists and is legal for the tool's schema, prints each problem,
and exits nonzero if there are any.

## Usage

```bash
# a single model
callprobe run --model llama3.1:8b --pad 0,8,16,24 --repeats 3 \
  --max-tokens 4096 --out results/llama31-8b.json

# any OpenAI-compatible endpoint
callprobe run --model gpt-4.1-mini --endpoint https://api.openai.com/v1 \
  --api-key $OPENAI_API_KEY

# build the comparison table, name the files explicitly.
# a glob like results/*.json will pick up old or archived runs
# and silently corrupt the table.
callprobe leaderboard results/llama31-8b.json results/qwen3-8b.json \
  > LEADERBOARD.md
```

`--api-key` falls back to the `API_KEY` environment variable, then
`OPENAI_API_KEY`, if it's not passed directly. `--retries` (default 3)
controls how many times a 429, a 5xx, or a connection or timeout error is
retried with exponential backoff before it's recorded as an error rather
than a model failure; those retries honor a `Retry-After` header when the
server sends one.

`--max-tokens` defaults to 2048. Reasoning models can need more (see the
truncation section above).

For a multi-model overnight sweep, `scripts/overnight.sh` pulls each model,
runs it, and rebuilds the leaderboard at the end:

```bash
REPEATS=3 caffeinate -is ./scripts/overnight.sh qwen3:8b llama3.1:8b
```

Works against Ollama, LM Studio, llama.cpp server, vLLM, and hosted
providers. `--quant` is a free-text label so quantizations of the same
model stay distinguishable in the leaderboard.

`--concurrency N` runs requests through a thread pool instead of one at a
time. The output file's result order stays the same either way. With
`--out`, results are written to disk after every completed request, and
`--resume PATH` skips any (task, pad, repeat) combination already in that
file, so a run that died partway (or was stopped with Ctrl-C, which still
produces a report from whatever finished) can pick back up without paying
for work already done:

```bash
callprobe run --model llama3.1:8b --concurrency 4 --out results/run.json
# if it dies partway through, or you stop it:
callprobe run --model llama3.1:8b --concurrency 4 \
  --resume results/run.json --out results/run.json
```

Resume requires matching model, endpoint, temperature, token budget,
quantization, detected server version, suite content, and scoring version.
You can add padding levels or repeats. Request errors are retried; completed
observations are reused. Missing files or incompatible checkpoints fail
before any model requests. Checkpoints are replaced atomically so a failed
write leaves the previous checkpoint intact.

Results include every structured tool call (`calls`), its ID, parsed and raw
arguments, parse errors, and `finish_reason`. This evidence is retained for
both passing and failing responses. Review result files before sharing:
tool arguments can contain application data.

`callprobe leaderboard` refuses to build a table across runs from
different suite versions or content, since the numbers would not be
comparable. Pass `--allow-mixed` to build it anyway.

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
rates. `--fail-on-regression` overrides a policy's `false` setting.

Exit codes are `0` for a passing gate, `1` for policy violations, and `2` for
invalid inputs. Without a gate flag, `compare` remains an informational
comparison and supports older files. These gates apply deterministic
thresholds; they do not claim statistical significance for a change.

## CI mode

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
- uses: Eladhirsh/callprobe@v0.7.0
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
- uses: Eladhirsh/callprobe@v0.7.0
  with:
    model: your-model
    endpoint: http://localhost:11434/v1
    baseline: results/baseline.json
    policy: callprobe-policy.yaml
    pad: '0,8,16,24'
    repeats: '3'
    max-tokens: '4096'
```

Baseline inputs require v0.5.0 or newer. Keep the baseline separate from the action's
`callprobe-results.json` output. The action also writes
`callprobe-comparison.json` and includes it in the job summary.

## The failure digest

Every run ends with the specific failures, not just the rates. These are
worth reading, and they are frequently upstream bugs rather than model
weaknesses. If a server drops `additionalProperties`, mangles nested
objects, or returns arguments as a string where the schema says integer,
you will see it here first, including what the model actually said, with
any reasoning trace stripped, when it produced no call at all.

## Explaining a saved run (since 0.7.0)

Install or upgrade with `uv tool install callprobe@latest`. This also
replaces an older version-pinned installation.

`callprobe explain RESULTS.json --suite DIR` turns a results file back into
a debugging session, offline: no model calls, and it never modifies the
results file or the suite. It requires the same suite the run was scored
against; a missing or mismatched suite hash is a clear, non-zero-exit error
rather than a diagnosis built on a suite that has since changed.

Using the committed GitHub issues example and its recorded Qwen3 8B run:

If `github-issues-suite` already exists from the walkthrough, reuse it and
skip the first two commands.

```bash
callprobe init --from-openapi examples/github-issues/openapi.json --out github-issues-suite
cp examples/github-issues/tasks.yaml github-issues-suite/tasks.yaml
callprobe explain results/github-issues/qwen3-8b.json --suite github-issues-suite
```

Only failing `(task, pad, repeat)` cases are shown; a run with no failures
prints a short pass report instead. Failures are grouped into recurring
diagnostic categories, counted per case rather than per failure message
(`request_error`, `truncated`, `no_call`, `unexpected_call`,
`multiple_calls`, `wrong_tool`, `malformed_arguments`, `schema`,
`argument_value`), and then shown one case at a time: the task's user
prompt(s), what was expected, every call the model actually produced
(parsed arguments, or the raw text and parse error for one that didn't
parse), and the failure reasons already recorded at run time. Records from
before structured call evidence existed say so plainly instead of guessing
at what was called.

`--task TASK_ID` scopes this to one task across every pad and repeat it
ran with, and says so plainly if that task passed with no failures.
`--format json` prints the same report as deterministic, structured JSON
instead, for scripting:

```bash
callprobe explain results/github-issues/qwen3-8b.json --suite github-issues-suite \
  --task get-issue-details --format json
```

For one common, fixable shape of bug, a correctly chosen tool whose
arguments were flattened or under-wrapped relative to an OpenAPI-imported
`path`/`query`/`body` schema, `explain` proposes a corrected argument
shape, e.g. moving top-level `owner`/`repo`/`issue_number` under `path`, or
wrapping a flat `body` string as `{"body": {"body": "..."}}`. This is
always labeled advisory: nothing is executed or re-scored, and expectation
and value correctness are never guaranteed. The hint only appears when the
mapping from stray arguments to the tool's missing nested groups is
unambiguous and the resulting candidate fully validates against the tool's
complete schema; anything involving `$ref`, `oneOf`/`anyOf`/`allOf`,
`patternProperties`, or a schema-valued `additionalProperties` is refused
rather than guessed at. Relocation hints also require the root schema to
forbid extra properties. Supported schemas get error paths, messages, and
expected types; unsupported schemas retain the recorded failure reasons
with an explanation of the diagnostic limitation.

## Status

The suite (version 2) is 50 hand-written tasks: 6 select, 11 abstain, 12
args, 11 depth, 10 sequence, spread across three tool bundles (a support
desk, a calendar, and a file manager). The two full sweeps in the Results
table above predate this growth and were run against suite version 1
(34 tasks, no file bundle). `LEADERBOARD.md` contains seven suite-v2 sweeps
and lists the two suite-v1 runs separately. Those historical sweeps predate
scoring version 2 and need reruns to establish baselines under the stricter
call-count and truncation rules. Fresh v0.5.0 baseline and repeat results
are stored separately in [`results/v0.5.0`](results/v0.5.0/README.md).
`callprobe leaderboard` will refuse to mix results from the two suite
versions in one table unless you pass `--allow-mixed`.

Every task in the suite passes `callprobe validate` (see Bring your own
tools above), and CI runs it on every push, so a typo in an expectation
can't silently fail every model.

Contributions most wanted, in order:

1. Tasks, especially `depth` and `sequence`, and anything drawn from real
   tool schemas you use
2. Runs against models not yet in the leaderboard
3. Adapters for endpoints that deviate from the OpenAI shape

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to write a task and
submit a run.

## Development

With uv installed, use `uv sync --extra dev`, then prefix development commands
with `uv run` (for example, `uv run callprobe init --help` or `uv run pytest`).
Alternatively, use a standard Python virtual environment:

```bash
git clone https://github.com/Eladhirsh/callprobe.git
cd callprobe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest
```

## License

MIT
