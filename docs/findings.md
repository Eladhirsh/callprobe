# Findings and methodology

What Callprobe measures, why it reports several scores, and what real runs against local models have shown so far.

## A concrete regression example

On our saved 18-case GitHub API suite, Qwen3 8B passed 11 cases versus
Qwen2.5 7B's 5, but regressed on two previously passing cases. The regression
gate correctly failed despite the higher overall score. These are individual
local runs, not a general model ranking. [Read the comparison report](../results/github-issues/comparison.md)
or the [conditions and raw results](../results/github-issues/README.md).

## September 2026 core smoke test

[Nine local models, 450 observations](../results/2026-09-30-smoke/README.md) on the
current 50-case core suite: Qwen 3 passed 42/50 versus Qwen 2.5's 38/50, but
regressed two previously passing cases. The [matched CI gate fails](../results/2026-09-30-smoke/qwen-comparison.md)
despite the higher total. Raw results, coverage, model digests, and source
provenance are included. These single-repeat runs are integration findings,
not a general model ranking.

## October 2026 repeated validation

[Nine models, 1,386 recorded observations](../results/2026-10-01-rc3-model-validation/README.md)
cover two core repeats and mail tools at three padding settings. Qwen3 scored
85/100 versus Qwen2.5’s 79/100 on core, but five matched observations regressed,
so the CI gate fails. The runs contain zero request errors and seven token-limit
truncations, all counted as failures. The archive includes raw results, frozen
suites, model identities, JUnit exports, and offline report/resume checks.
These local Ollama configurations are integration evidence, not a general ranking.

## Historical core benchmark

The output below is an archived suite-v1 run, not the expected output of the
six-case quickstart or a current model leaderboard.

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
[`LEADERBOARD.md`](../LEADERBOARD.md) and the raw per-task JSON in `results/`.

## Results so far

The table below preserves the original suite-v1 runs. For the v0.5.0
scoring rules and a matched real-model baseline/repeat, see the
[release validation report](../results/v0.5.0/README.md).

| model | success | type-lenient | abstain | tokens/success |
| --- | --- | --- | --- | --- |
| qwen3:8b | 88.7% | 88.7% | 88.6% | 1568 |
| llama3.1:8b | 32.1% | 51.2% | 9.8% | 3441 |

Two findings worth reading past the ranking:

**Abstention is the gap that costs money.** Asked eleven questions with no
correct tool to call, qwen3:8b declined correctly 88.6% of the time.
llama3.1:8b declined correctly 9.8% of the time. Asked about a return
policy, it called `issue_refund`; asked to change an email address, it
called `update_shipping_address`. Nine times in ten it acted when it should
have asked a question. These cases illustrate why abstention needs explicit tests.

**Type coercion masks a real capability.** 19.1% of llama3.1:8b's calls
were computed correctly and serialized wrong: `"1299"` instead of `1299`,
an array delivered as a JSON-encoded string. Score those leniently (cast
strings to the type the schema declares, never touch the value) and success
jumps from 32.1% to 51.2%. Lenient scoring identifies recoverable type
mismatches; it does not establish whether the model or serving layer caused
them. `callprobe` reports both numbers (see `type-lenient` in the output above and
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

**Starting with 0.9.0rc1:** new run files record `scoring_version: 3`.
Published Callprobe 0.8.0 uses scoring version 2. Version 3 fixes lenient
integer coercion: `"4225.9"` and `"4225.00000000000001"` stay incorrect
instead of being truncated or rounded to `4225`. Exact integral strings
such as `"4225.0"` and `"4.225e3"` still coerce, and large integers retain
their exact value. Nonfinite numeric strings and integer values requiring
more than 4300 decimal digits remain strings. Stringified arrays and objects
use the same numeric safety limits. Strict scoring is unchanged.

Historical files retain their recorded verdicts and remain readable; the
offline demo still uses its original version-2 evidence. Complete, compatible
version-2 runs can still be gated against each other. Gates, resume, and
`--failed-from` refuse mixed scoring versions. Leaderboards also reject mixed
versions unless `--allow-mixed` is supplied.

When upgrading to version 3, rerun both baseline and candidate using the same
suite and comparison settings, writing new files rather than replacing the
old evidence. Corrected precision can raise or lower lenient scores; changing
a saved file's version label is not a migration.

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

## Status

The suite (version 2) is 50 hand-written tasks: 6 select, 11 abstain, 12
args, 11 depth, 10 sequence, spread across three tool bundles (a support
desk, a calendar, and a file manager). The two full sweeps in the Results
table above predate this growth and were run against suite version 1
(34 tasks, no file bundle). `LEADERBOARD.md` contains seven suite-v2 sweeps
and lists the two suite-v1 runs separately. Those historical sweeps predate
scoring version 2 and need reruns to establish baselines under the stricter
call-count and truncation rules. Fresh v0.5.0 baseline and repeat results
are stored separately in [`results/v0.5.0`](../results/v0.5.0/README.md).
`callprobe leaderboard` will refuse to mix results from the two suite
versions in one table unless you pass `--allow-mixed`.

Every task in the suite passes `callprobe validate` (see [Testing your own
tools](own-tools.md)), and CI runs it on every push, so a typo in an expectation
can't silently fail every model.

Contributions most wanted, in order:

1. Tasks, especially `depth` and `sequence`, and anything drawn from real
   tool schemas you use
2. Runs against models not yet in the leaderboard
3. Adapters for endpoints that deviate from the OpenAI shape

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for how to write a task and
submit a run.
