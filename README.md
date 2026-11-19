# callprobe

**Does this model reliably call _your_ tools?**

Callprobe sends your tool schemas and test prompts to any OpenAI-compatible
model endpoint (Ollama, LM Studio, llama.cpp, vLLM, or a hosted API) and scores
every response:

- **Selection:** did it pick the right tool, or correctly call nothing?
- **Schema:** do the arguments validate against the tool's JSON Schema?
- **Arguments:** are the values actually right?
- **Abstention:** when no tool applies, does it hold back instead of acting?

It only evaluates what the model proposes. It never executes your tools or
calls your API, so you can test a refund or delete operation safely.

It also checks the other half of an agent's job: whether what it **tells the
user** it did matches what its tools actually did. See
[Check what your agent claims](#check-what-your-agent-claims).

## Quickstart

You need Python 3.10 or newer. Setup and validation work offline:

```bash
pip install callprobe
callprobe init --example support --out callprobe-demo
callprobe validate --suite callprobe-demo
```

`validate` should report 6 tasks and `no problems found`. The suite is a small
fictional order and refund API that ships inside the package. You can also
install with `uv tool install callprobe` or `pipx install callprobe`.

To score a model, start [Ollama](https://ollama.com) and pull a model that
supports tool calling:

```bash
ollama pull qwen2.5:7b
callprobe run --suite callprobe-demo --model qwen2.5:7b \
  --pad 0 --repeats 1 --max-tokens 4096 --out callprobe-demo/baseline.json
callprobe explain callprobe-demo/baseline.json --suite callprobe-demo
```

`explain` shows each failure, what was expected, and what the model actually
sent. An excerpt from a real run:

```
[status-by-id pad=0 repeat=0] category=select  diagnostics=schema, argument_value
  prompt: Check the status of order ORD-448120.
  expected: call get_order
    args {'path': {'order_id': 'ORD-448120'}}
  called: get_order
  reason: schema: (root): 'path' is a required property
  call: get_order arguments={'order_id': 'ORD-448120'}
  shape hint [nested_move] advisory only: not executed or re-scored
    moved: {'order_id': 'path'}
```

The model chose the right tool and the right order ID, but flattened the
arguments, so a real API call would have failed. Failed cases are findings,
not installation errors. On this suite, `qwen2.5:7b` passed 2 of 6.

For another server, add `--endpoint` and `--api-key`:

```bash
callprobe run --suite callprobe-demo --model gpt-4.1-mini \
  --endpoint https://api.openai.com/v1 --api-key "$OPENAI_API_KEY"
```

`--api-key` falls back to `API_KEY`, then `OPENAI_API_KEY`.

## Help test it

Callprobe is looking for first users. If you try it, please
[report your first-run experience](https://github.com/Eladhirsh/callprobe/issues/new?template=first-run-feedback.yml):
which endpoint and model you used, whether the quickstart worked, and one
thing that confused you. Short answers are useful.

## Test your own tools

Import an OpenAPI 3.0 or 3.1 document, write the expected behavior for each
drafted task, then validate and run:

```bash
callprobe init --from-openapi openapi.yaml --out my-suite
# Edit my-suite/tasks.yaml: uncomment drafts and write expected behavior.
callprobe validate --suite my-suite
callprobe run --suite my-suite --model qwen2.5:7b --pad 0 --out baseline.json
```

You can also start from an OpenAI-format `tools.json` with
`callprobe init --from tools.json`, or write the YAML by hand. See
[Testing your own tools](https://github.com/Eladhirsh/callprobe/blob/main/docs/own-tools.md).

## Catch regressions in CI

Save a baseline, then fail the build when a change makes a previously passing
case fail:

```bash
callprobe run --suite my-suite --model qwen2.5:7b --out candidate.json
callprobe compare baseline.json candidate.json --fail-on-regression
```

A GitHub Action is included:

```yaml
- uses: Eladhirsh/callprobe@v0.9.1
  with:
    model: llama3.1:8b
    endpoint: http://localhost:11434/v1
    fail-under: '0.7'
```

See [Comparing runs and CI gates](https://github.com/Eladhirsh/callprobe/blob/main/docs/comparing-and-ci.md) for policies,
critical tasks, and JUnit export.

## What it has found

Results from local runs, with raw data in [`results/`](https://github.com/Eladhirsh/callprobe/tree/main/results):

- **Acting when it should ask.** On questions where no tool applied,
  `llama3.1:8b` declined correctly 9.8% of the time. Asked about a return
  policy, it called `issue_refund`.
- **Right values, wrong types.** 19.1% of `llama3.1:8b` calls had correct
  values serialized wrong, such as `"1299"` instead of `1299`. Callprobe
  reports a strict score and a type-lenient score so you can see the difference.
- **Truncation that looks like incapability.** `qwen3:8b` scored 66.7% with a
  512-token budget and 91.7% with 4096 on the same tasks. Callprobe counts
  truncated responses separately.
- **Higher score, new failures.** `qwen3:8b` beat `qwen2.5:7b` overall but
  broke cases that `qwen2.5:7b` passed, so the regression gate failed.

More in [Findings and methodology](https://github.com/Eladhirsh/callprobe/blob/main/docs/findings.md) and
[`LEADERBOARD.md`](https://github.com/Eladhirsh/callprobe/blob/main/LEADERBOARD.md). These are integration findings from
specific local setups, not a general model ranking.

## Check what your agent claims

Your agent says *"I refunded $40 and emailed you the receipt."* The trace says
it refunded $400 and never called the email tool. `callprobe audit` reads an
agent's messages and its tool-call trace, extracts every claim about a
completed action, and checks each one against the recorded calls:

| Verdict | Meaning |
|---|---|
| **Contradicted** | The call happened with different details than the agent stated |
| **Phantom** | The agent claimed an action that no earlier call performed |
| **Masked failure** | The call returned an error, but the agent reported success |
| **Unmentioned** | A side-effecting call the agent never told the user about |
| **Backed** | The claim matches a successful call |

This runs offline with claims that are already labeled:

```bash
git clone https://github.com/Eladhirsh/callprobe.git && cd callprobe
callprobe audit examples/didyoureally/openai_masked_failure.json \
  --claims examples/didyoureally/openai_masked_failure.claims.json
```

```
[Masked failure] "Your Pro plan (sub_9) is cancelled"
    cancel_subscription returned an error, but the agent reported success.
    Call call_2: cancel_subscription({"subscription_id": "sub_9"}) -> error
```

For your own traces (OpenAI chat messages or a native JSON format), a model
extracts the claims and plain code decides every verdict, so the model never
grades its own work. A local model works:

```bash
export DYR_BASE_URL=http://localhost:11434/v1 DYR_MODEL=mistral-nemo:latest
callprobe audit my-trace.json
```

Contradicted, phantom, and masked failure findings exit with code 1 for CI.
`callprobe audit bench` runs the bundled benchmark. See the
[account checks guide](https://github.com/Eladhirsh/callprobe/blob/main/docs/didyoureally.md)
for trace formats, options, and limits. These checks were developed as
Didyoureally and are now part of Callprobe.

## Agent workflow (experimental)

`callprobe agent` runs a model against mock tools across multi-step scenarios
and applies both checks separately: whether it made the expected calls, and
whether its final message accurately describes what those calls returned. In
the first pilot, both tested models reported success after refunds that had
failed.

```bash
callprobe agent init --out refund-pilot.json
callprobe agent run --suite refund-pilot.json --model qwen2.5:7b \
  --extractor-model mistral-nemo:latest --json-mode --out agent-pilot
```

See [the agent workflow guide](https://github.com/Eladhirsh/callprobe/blob/main/docs/agent-workflow.md) for gates, limitations,
and results across four models.

## Upgrading from 0.8.0

0.9.0 changes lenient scoring and makes `--pad 0` the default. Rerun your
baseline before comparing it with 0.9.0 results; see the
[upgrade notes](https://github.com/Eladhirsh/callprobe/blob/main/CHANGELOG.md#upgrading-from-080).
Each guide notes which version a feature needs.

## Documentation

- [Running Callprobe](https://github.com/Eladhirsh/callprobe/blob/main/docs/running.md): endpoint checks, run options, saved
  settings, dry runs, resuming, and targeted reruns
- [Reading results](https://github.com/Eladhirsh/callprobe/blob/main/docs/reading-results.md): the failure digest, `explain`,
  and `report`
- [Scenario formats](https://github.com/Eladhirsh/callprobe/blob/main/docs/scenario-formats.md): every field of the
  tool-decision, agent, and account-check formats, with validated examples
- [Testing your own tools](https://github.com/Eladhirsh/callprobe/blob/main/docs/own-tools.md): OpenAPI import, bundled
  examples, writing suites, and scoring recorded application decisions
- [Comparing runs and CI gates](https://github.com/Eladhirsh/callprobe/blob/main/docs/comparing-and-ci.md): `compare`,
  policies, the GitHub Action, JUnit, and tool contract comparisons
- [Account checks](https://github.com/Eladhirsh/callprobe/blob/main/docs/didyoureally.md): `callprobe audit`, trace
  formats, verdicts, benchmarks, and limits
- [Agent workflow](https://github.com/Eladhirsh/callprobe/blob/main/docs/agent-workflow.md): decision and account checks
  in mock agent sessions
- [Findings and methodology](https://github.com/Eladhirsh/callprobe/blob/main/docs/findings.md): scoring rules, what the
  numbers mean, and results so far
- [Changelog](https://github.com/Eladhirsh/callprobe/blob/main/CHANGELOG.md)

## Repository layout

- `src/callprobe`: tool-decision scoring, the CLI, the mock agent runner,
  reports, and CI gates
- `src/callprobe/didyoureally`: claim extraction and deterministic trace
  matching behind `callprobe audit`
- `examples/`: bundled and walkthrough suites; `examples/didyoureally` holds
  account-check traces and frozen suites
- `results/`: raw evidence behind every published number

## Contributing

Most wanted: tasks drawn from real tool schemas, runs against models not yet in
the leaderboard, and adapters for endpoints that differ from the OpenAI shape.
See [CONTRIBUTING.md](https://github.com/Eladhirsh/callprobe/blob/main/CONTRIBUTING.md) for setup, checks, and how to submit a
task or a run.

## License

[MIT](https://github.com/Eladhirsh/callprobe/blob/main/LICENSE), including the account checks.
