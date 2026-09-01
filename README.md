# toolprobe

Test whether a model can actually call **your** tools.

Every local model claims tool calling support. Existing leaderboards test
somebody else's function schemas. `toolprobe` points at any
OpenAI-compatible endpoint, runs your own tool definitions against it, and
tells you where it breaks.

```bash
pip install toolprobe
toolprobe run --model qwen3:8b --endpoint http://localhost:11434/v1
```

```
model            qwen3:8b  (q4_K_M)
tasks scored     360

                 selection   schema     args      success
  overall          91.4%    88.1%    72.5%    68.9%

  tool count sweep
    +0   distractors   success  81.1%   selection  96.7%   sd  2.1
    +8   distractors   success  70.0%   selection  91.1%   sd  3.4
    +16  distractors   success  55.6%   selection  86.1%   sd  4.8

  by category
    abstain     41.7%
    args        62.2%
    depth       70.0%
    select      88.9%
    sequence    75.0%

  cost per success   1840 tokens   0.94 s
```

## Why three scores instead of one

`selection`, `schema`, and `args` fail for different reasons, and the gap
between them is the whole point.

- **selection** picked the right tool, or correctly called nothing
- **schema** the arguments validate against the tool's JSON Schema
- **args** the values are actually right

A model with high selection and schema but low args is the dangerous case.
It emits well-formed calls with wrong values, which pass every check most
people currently run. That is the failure that reaches production.

## What it measures that other harnesses do not

**Abstention.** Roughly a third of the suite is tasks where the correct
behavior is to call nothing and ask a question. Small models are far worse
at declining than at choosing, and almost nobody tests it.

**Tool count.** Accuracy with 5 tools tells you little about accuracy with
20. `--pad` adds plausible but irrelevant tools from a distractor pool and
reports the curve. Tool order is shuffled per run, because position bias is
real and should not be allowed to hide.

**Conversation depth.** Turn one accuracy is not turn nine accuracy.

**Variance.** Tool calling is not deterministic even at temperature 0.
`--repeats` runs each task more than once and reports a standard deviation,
so you get a number with an error bar instead of a number.

**Cost per success.** Tokens and seconds divided by *correct* calls. Raw
latency flatters models that fail quickly.

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

## Usage

```bash
# a single model
toolprobe run --model llama3.1:8b --pad 0,8,16 --repeats 3 --out results/llama31-q4.json

# any OpenAI-compatible endpoint
toolprobe run --model gpt-4.1-mini --endpoint https://api.openai.com/v1 --api-key $OPENAI_API_KEY

# build the comparison table
toolprobe leaderboard results/*.json > LEADERBOARD.md
```

Works against Ollama, LM Studio, llama.cpp server, vLLM, and hosted
providers. `--quant` is a free-text label so quantizations of the same model
stay distinguishable in the leaderboard.

## The failure digest

Every run ends with the specific failures, not just the rates. These are
worth reading, and they are frequently upstream bugs rather than model
weaknesses. If a server drops `additionalProperties`, mangles nested
objects, or returns arguments as an object where the spec says string, you
will see it here first.

## Status

Early. The seed suite is 12 tasks, which is enough to try the tool and not
enough to publish numbers from. Target is roughly 30 per category.

Contributions most wanted, in order:

1. Tasks, especially abstention and argument-correctness cases drawn from
   real tool schemas you use
2. Adapters for endpoints that deviate from the OpenAI shape
3. Runs against models not yet in the leaderboard

## License

MIT
