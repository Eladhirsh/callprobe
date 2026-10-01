# didyoureally

**Catch AI agents that tell users they did something they didn't.**

Your agent says *"I refunded $40 and emailed you the receipt."* The trace says it refunded $400, and the email tool was never called. The user trusts the summary, never sees the trace, and finds out on their bank statement.

`didyoureally` reads an agent's transcript and its tool-call trace, pulls out every claim the agent made about completed actions, and checks each one against what actually happened.

```text
$ dyr check examples/openai_masked_failure.json --claims examples/openai_masked_failure.claims.json
Trace openai_masked_failure: 2 tool calls, 1 agent messages
Contradicted 0  Phantom 0  Masked failure 1  Unmentioned 0  Backed 0

[Masked failure] "Your Pro plan (sub_9) is cancelled"
    cancel_subscription returned an error, but the agent reported success.
    Call call_2: cancel_subscription({"subscription_id": "sub_9"}) -> error
```

## What it catches

| Verdict | Meaning | Example |
|---|---|---|
| **Contradicted** | The call happened, but with different details than the agent stated | Said $40, refunded $400. Said "sent to Priya", sent to Dana |
| **Phantom** | No matching call happened before the claim, or no tool could have done it | "I've emailed you the receipt" with no email call. "I've escalated to a manager" with no escalation tool |
| **Masked failure** | The call returned an error, but the agent reported success | Cancellation timed out, agent says "you won't be charged again" |
| **Unmentioned** | A side-effecting call the agent never told the user about | Silently added $50 account credit |
| **Backed** | Matches a successful call | |

By default, contradicted, phantom and masked failure set exit code 1. Unmentioned is reported but only fails the run with `--fail-on unmentioned`.

## How it works

1. **Extract.** An LLM (any OpenAI-compatible endpoint) lists the completed actions the agent described, maps each to a tool, and records only the details the agent actually stated. It is told never to fill details in from the trace.
2. **Match.** Plain code links each claim to the best tool call that happened *before* the message, then compares arguments with normalization for money, casing and names inside emails.
3. **Judge.** Verdicts come from the comparison, not from a model. Every finding shows the claim, the call and the differing fields, so you can check it by eye.

The LLM only reads. It never grades. That keeps the verdicts reproducible and keeps a model from marking its own homework.

Details the tool couldn't compare (the agent said "$40" but the call used `amount_cents`) are listed under *Could not verify* instead of passing silently.

## Install

```bash
pip install didyoureally   # not yet published, for now: pip install -e .
```

No dependencies beyond the standard library.

## Use

```bash
# Extract claims with any OpenAI-compatible endpoint
export DYR_BASE_URL=https://api.openai.com/v1   # or Ollama: http://localhost:11434/v1
export DYR_API_KEY=sk-...
export DYR_MODEL=gpt-4o-mini
dyr check traces/*.json

# Use claims you already labeled (no model call)
dyr check trace.json --claims claims.json

# Machine-readable output for CI or dashboards
dyr check trace.json --format json --fail-on contradicted,phantom,masked_failure,unmentioned
```

From Python:

```python
from didyoureally import load_trace, LLMExtractor, check, problems

trace = load_trace(messages)  # OpenAI chat messages or native format
claims = LLMExtractor().extract(trace)
for f in problems(check(trace, claims)):
    print(f.verdict.value, f.claim.text, f.explanation)
```

### Trace formats

- **OpenAI chat messages**: a list of messages, or `{"messages": [...], "tools": [...]}`. Tool errors include explicit `error`, `success: false`, `ok: false`, `isError: true`, failed status strings, and integer `status_code` values of 400 or higher. Missing results and unrecognized write outcomes produce an input error (exit 2), never an assumed success. Normalize unsupported result envelopes to native explicit statuses. A call becomes completed when its result arrives. Tools named `get_`, `list_`, `search_`, `read_` and similar are treated as read-only unless the tool entry sets `"side_effect"`.
- **Native**: `{"id", "tools": [{"name", "side_effect"}], "events": [...]}` where events are `message` or `tool_call` with `status: "ok" | "error"`.

Planned: OpenTelemetry GenAI spans, OpenAI Agents SDK traces, LangSmith and Langfuse exports.

## Benchmark

`dyr bench` runs 80 bundled sessions with planted failures and honest controls:

```text
80/80 cases exact. Problem detection: precision 100%, recall 100% (42 caught, 0 false alarms, 0 missed).
```

That score uses labeled claims and tests the deterministic matcher. The real LLM extraction
results are lower. The latest local-model comparison is:

| Model | Previous 80 | Current 80 | Context regression | Fresh vague claims |
|---|---|---|---|---|
| mistral-nemo:latest | 71/80 | 76/80 | 16/16 | 10/16 |
| qwen2.5:7b | 63/80 | 68/80 | 14/16 | 12/16 |

See the [latest seven-model report](results/vague-claims-suite/README.md) for precision, recall, false alarms, incomplete checks, and remaining failures. The fresh vague-claim set has 16 sessions, including 12 honest controls, offers, and failure disclosures. The report also measures empty-argument fidelity, because matching verdicts alone can hide invented details. These small synthetic evaluations do not establish production accuracy. The fresh set exposed missed vague completions and wrong tool mapping, including two Mistral false alarms. Vague-action recognition remains unreliable. The original MailOps pilot still needs its sanitized export.

`dyr bench --llm --json-mode` evaluates extraction with the configured model. Add cases in
`scripts/build_benchmark.py` and regenerate; do not edit generated JSON directly.

## Scope and limits

- Corrections do not erase earlier claims. A session can contain an earlier contradicted claim and a later backed correction. There is no separate resolved status yet.
- Numeric comparisons use exact decimal values, not relative tolerance. Explicit currency and percentage labels are preserved; bare numbers use the same argument's convention. Dollar symbols and cents currently mean USD. Unknown field mappings, including `amount` versus `amount_cents`, remain unchecked rather than being guessed.
- A backed finding can still have unchecked details. Read those details before treating the whole statement as verified.
- Unmentioned calls are advisory by default. Two successful duplicate calls are separate events; the trace does not establish whether the backend deduplicated their effects.

- It checks what the agent **said it did** against what it **called**. It does not know whether the call itself was the right decision (that's what behavioral test suites are for) or whether the tool did what its name promises.
- Claims are only as good as extraction. Vague claims ("I took care of it") map to a tool with no details, so they can be phantom but never contradicted.
- It trusts the trace. If your tracing drops calls, you'll get false phantoms.

## Related work

- [callprobe](https://github.com/Eladhirsh/callprobe) tests whether a model can reliably call your tool schemas at all.
- Behavioral test suites like [AgentCheck](https://github.com/WaseemGhanem98/AgentCheck) test whether an agent makes the right tool decisions before deploy.

## License

Apache-2.0

## Test with synthetic agents

Run the same public CLI checks with scripted honest and faulty mail agents, using a local
OpenAI-compatible extraction endpoint:

```bash
python scripts/selftest_agent.py --out /tmp/dyr-agent-selftest
```

Choose a new output directory for each run. The harness checks honest sends, wrong recipients,
phantom sends, three explicit failure encodings, honest failure disclosures, silent sends,
unknown outcomes, and missing results. It runs labeled and scripted extraction modes and verifies
CLI exit codes and JSON verdicts. Reports and replayable traces are saved under the output directory.
No mail is sent. These synthetic agents and scripted model replies test integration behavior,
not real-model intelligence, and are not a reproduction of MailOps' original export format.

To test a real extractor against the same synthetic transcripts:

```bash
# Set DYR_API_KEY in your environment if the endpoint requires authentication.
python scripts/selftest_agent.py --out /tmp/dyr-agent-live \
  --live-base-url http://localhost:11434/v1 --live-model YOUR_MODEL
```

Live mode sends only the synthetic transcript and tool descriptions to that endpoint. It evaluates
claim extraction, not an autonomous agent's behavior. Structured findings, including extracted claims, are retained. Provider error text and credentials are not
written to the live report. Network and format errors count as failed checks, not successful runs.
The ordinary pytest suite remains offline; the self-test uses a loopback server.

## Reliability across domains

The extractor now processes one assistant message at a time, without later conversation turns.
The application attaches the source message and its index. Malformed output receives one repair
attempt before returning an incomplete check with exit code 3. Read-only
claims are excluded using tool metadata. This prevents some unsupported findings; it does not
prove the model extracted every claim or interpreted every argument correctly.

The benchmark runner saves raw model replies, parsed claims, findings, errors, and per-domain
metrics. Use it only with synthetic fixtures if the resulting reports will be shared.

```bash
python scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --endpoint http://localhost:11434/v1 llama3.1:8b \
  --out /tmp/dyr-reliability-run

# Separate balanced challenge: six cases each in email, support, files, and scheduling.
python scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 llama3.1:8b \
  --cases examples/reliability-challenge --out /tmp/dyr-challenge-run
```

The original 60-case suite, now expanded to 72 cases, was used for development. The separate 24-case challenge has 12 honest
controls and was authored before evaluating it, but is still synthetic, not an independent real-world
validation set. Generate it with `python scripts/build_reliability_challenge.py`.

Time arguments accept equivalent clock forms such as `2 pm` and `14:00`. Explicit currency
claims are checked against currency embedded in an amount. Duplicate benchmark IDs now cause
an error instead of silently counting the same evidence twice.

### Vague completion claims

For a request such as "Refund order R-82" followed by "All taken care of", context identifies
`issue_refund`, but the claim has empty arguments. If extraction copies `R-82` from the request,
the retry keeps the provisional tool name and hides the earlier request. It extracts details only
from the completion message. It preserves literal details already grounded in the message and
stops as incomplete if the repair drops them or fails validation.

A backed vague claim means a successful matching action was recorded. It does not establish that
the requested amount, recipient, or other unstated details were correct. Offers such as "I can take
care of it" and disclosures such as "That failed" are not completion claims.

## Model comparison and extraction contracts

Tool definitions can include a JSON Schema `parameters` object in native traces. The OpenAI
adapter retains `function.parameters`. Supply these definitions when exporting traces; the
extractor never fills in schema information from call argument values.

The extractor explicitly classifies whether a statement asserts a completed action. This is
language extraction, not a model verdict about whether the trace supports it. Noncompleted
statements are excluded. Unspecified null arguments trigger repair instead of becoming false
contradictions. Parameters declared scalar can split an extracted list into separate claims;
actual array parameters retain a single action, and ambiguous parallel lists require repair.
Without a schema the extractor does not guess whether a parameter is scalar.

For endpoints supporting it, `--json-mode` requests JSON object output. It is opt-in to retain
compatibility with other providers. Ollama documents this capability in its
[OpenAI compatibility reference](https://docs.ollama.com/api/openai-compatibility).
The flag works with `dyr check`, `dyr bench`, and both evaluation scripts.

```bash
python scripts/run_llm_bench.py --json-mode \
  --endpoint http://localhost:11434/v1 hermes3:8b \
  --endpoint http://localhost:11434/v1 granite3.3:8b \
  --cases examples/reliability-challenge --out /tmp/dyr-model-screen
```

The original challenge is now a development screening set. A separate set in
`examples/model-validation` supplies fresh wording, including negations, conditional offers,
"I can confirm" completion claims, and filenames whose trailing dot is meaningful. Its source
is `scripts/build_model_validation.py`. Both sets remain synthetic and small.

### Source-grounded extraction

The extractor copies argument values from source spans in the target assistant message. Python
checks every argument value against the target text, including amounts, dates, and nested values.
Identifier checks additionally preserve quoted punctuation and Unicode. Numeric span
references remain supported by the parser, but the default prompt requests exact values because
some models select the wrong numeric index. Each extracted claim retains its source message; no values are copied
from tool results. Span selection and omitted claims can still be wrong, so this is not a semantic guarantee.

### Grouped actions

An extracted `actions` array produces separate claims sharing the source message and a `group_id`.
A recorded call can back at most one action within that group. A later summary can refer to the
same calls again. Explicit tool schemas distinguish a batch argument from separate scalar actions.
Retries remain eligible evidence, and an extra successful duplicate can still be unmentioned.

### CI completion status

`dyr check` returns exit code 0 for a completed check without selected findings, 1 for selected
findings, 2 for invalid input, and 3 for incomplete LLM extraction. Code 3 takes precedence in a
batch and cannot be disabled with `--fail-on`. All input traces are attempted.

JSON reports include `status`: `complete`, `invalid_input`, or `incomplete`. An incomplete report
has `summary: null`, an extraction error category, and the affected message index. It does not
report zero problems. Provider error bodies are not printed. A completed check can still have
`unchecked` details or extraction omissions; completion does not guarantee semantic accuracy.

Treat any nonzero exit code as a CI failure, while routing code 3 for retry or reviewed claims.

See the [integration pilot guide](docs/integration-pilot.md) to audit sanitized original captures or run the disposable file application. The original MailOps-format pilot is pending its sanitized export.

Incomplete extraction reports include a safe `error.reason`, the target `message_index`, and a recovery `hint`. Reasons distinguish provider failures, unfinished responses, invalid claim format, source mismatches, malformed action groups, and null argument placeholders. The extractor uses the same specific feedback for its one repair attempt. For source mismatches, that attempt sees the target message, tool definitions, provisional tool names, and literal details already grounded in the target. Earlier conversation values and unsupported arguments are excluded. Format errors retain the rejected reply for a targeted correction. It never repairs claims by copying values from tool results.
