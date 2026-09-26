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

- **OpenAI chat messages**: a list of messages, or `{"messages": [...], "tools": [...]}`. Tool errors are detected from `{"error": ...}` payloads or text starting with "Error". Tools named `get_`, `list_`, `search_`, `read_` and similar are treated as read-only unless the tool entry sets `"side_effect"`.
- **Native**: `{"id", "tools": [{"name", "side_effect"}], "events": [...]}` where events are `message` or `tool_call` with `status: "ok" | "error"`.

Planned: OpenTelemetry GenAI spans, OpenAI Agents SDK traces, LangSmith and Langfuse exports.

## Benchmark

`dyr bench` runs 50 bundled sessions with planted lies: wrong amounts, wrong recipients, phantom emails, masked failures, claims made before the action happened, silent side effects, and honest cases that must not be flagged.

```text
$ dyr bench
50/50 cases exact. Problem detection: precision 100%, recall 100% (27 caught, 0 false alarms, 0 missed).
```

With labeled claims this tests the matcher. `dyr bench --llm` runs extraction too, which measures the whole pipeline with the model you configure. That end-to-end number is the one worth publishing per model.

The suite includes 22 honest controls, plus partial actions, vague completions, currency and unit traps,
offers, read-only lookups, corrections, retries, duplicate calls, and file and order identifiers.
These are development cases, not a held-out evaluation set. No real-model result has been measured yet.
Exact-case scoring compares counts of verdict and tool pairs, not claim text or matched call identity.
Problem precision and recall cover contradicted, phantom, and masked failure; they exclude unmentioned.

Add a case in `scripts/build_benchmark.py` and run it to regenerate the files.

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
