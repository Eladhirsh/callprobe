# callprobe

Test whether a model can actually call **your** tools.

Every local model claims tool calling support. Existing leaderboards test
somebody else's function schemas. `callprobe` points at any
OpenAI-compatible endpoint, runs your own tool definitions against it, and
tells you where it breaks.

```bash
git clone https://github.com/Eladhirsh/callprobe.git
cd callprobe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

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

## Results so far

| model | success | type-lenient | abstain | tokens/success |
| --- | --- | --- | --- | --- |
| qwen3:8b | 88.7% | 88.7% | 88.6% | 1568 |
| llama3.1:8b | 32.1% | 51.2% | 9.8% | 3441 |

Two findings worth reading past the ranking:

**Abstention is the gap that costs money.** Asked eleven questions with no
correct tool to call, qwen3:8b declined correctly 88.6% of the time.
llama3.1:8b declined correctly 9.8% of the time — asked about a return
policy, it called `issue_refund`; asked to change an email address, it
called `update_shipping_address`. Nine times in ten it acted when it should
have asked a question. That is the failure mode that reaches production,
and almost no existing benchmark measures it.

**Type coercion masks a real capability.** 19.1% of llama3.1:8b's calls
were computed correctly and serialized wrong — `"1299"` instead of `1299`,
an array delivered as a JSON-encoded string. Score those leniently (cast
strings to the type the schema declares, never touch the value) and success
jumps from 32.1% to 51.2%. Roughly half of what looks like a reasoning
failure is a formatting bug in the serving layer, not the model being
unable to do the task. `callprobe` reports both numbers so you can tell
which one you're looking at — see `type-lenient` in the output above and
the full row in the table.

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
rescored. Lenient can only rescue a strict failure, never create one — the
gap between the two numbers tells you how much of a model's failure is
serialization rather than reasoning.

## What it measures that other harnesses do not

**Abstention.** Roughly a third of the suite is tasks where the correct
behavior is to call nothing and ask a question. Models vary enormously here
— see Results above — and almost nobody tests it.

**Tool count.** Accuracy with 5 tools tells you little about accuracy with
25. `--pad` adds plausible but irrelevant tools from a distractor pool and
reports the curve. Tool order is shuffled per run, because position bias is
real and should not be allowed to hide. Tasks can declare
`exclude_distractors` for tools that would make the expected answer wrong.

**Conversation depth.** Turn one accuracy is not turn nine accuracy.

**Variance.** Tool calling is not deterministic even at temperature 0.
`--repeats` runs each task more than once and reports a standard deviation,
so you get a number with an error bar instead of a number.

**Cost per success.** Tokens and seconds divided by *correct* calls. Raw
latency flatters models that fail quickly, and rewards models that fail
cheaply over models that succeed expensively. In the table above,
llama3.1:8b is faster per request but costs more than twice as much per
usable call.

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

**Type coercion masks correct reasoning.** Covered above — 19.1% of one
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
actually happened, not just a rate — the failures worth reading first are
usually your own.

## Bring your own tools

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

## Usage

```bash
# a single model
callprobe run --model llama3.1:8b --pad 0,8,16,24 --repeats 3 \
  --max-tokens 4096 --out results/llama31-8b.json

# any OpenAI-compatible endpoint
callprobe run --model gpt-4.1-mini --endpoint https://api.openai.com/v1 \
  --api-key $OPENAI_API_KEY

# build the comparison table — name the files explicitly.
# a glob like results/*.json will pick up old or archived runs
# and silently corrupt the table.
callprobe leaderboard results/llama31-8b.json results/qwen3-8b.json \
  > LEADERBOARD.md
```

`--max-tokens` defaults to 2048. Reasoning models can need more — see the
truncation section above.

For a multi-model overnight sweep, `scripts/overnight.sh` pulls each model,
runs it, and rebuilds the leaderboard at the end:

```bash
REPEATS=3 caffeinate -is ./scripts/overnight.sh qwen3:8b llama3.1:8b
```

Works against Ollama, LM Studio, llama.cpp server, vLLM, and hosted
providers. `--quant` is a free-text label so quantizations of the same
model stay distinguishable in the leaderboard.

## The failure digest

Every run ends with the specific failures, not just the rates. These are
worth reading, and they are frequently upstream bugs rather than model
weaknesses. If a server drops `additionalProperties`, mangles nested
objects, or returns arguments as a string where the schema says integer,
you will see it here first — including what the model actually said, with
any reasoning trace stripped, when it produced no call at all.

## Status

The suite is 34 hand-written tasks: 6 select, 11 abstain, 12 args, 3 depth,
2 sequence. Two models have full sweeps (see Results above and
`LEADERBOARD.md`) — enough to see a real, large gap between models, not yet
enough to call any single number final. `depth` and `sequence` are thin (2–3
task templates each) and shouldn't be over-read; growing every category
toward 30 is the current priority.

Task expectations are validated by the test suite: every asserted argument
key must exist in the tool's schema, and every asserted value must be legal
for it. A typo in an expectation would otherwise fail every model silently.

Contributions most wanted, in order:

1. Tasks, especially `depth` and `sequence`, and anything drawn from real
   tool schemas you use
2. Runs against models not yet in the leaderboard
3. Adapters for endpoints that deviate from the OpenAI shape

## License

MIT
