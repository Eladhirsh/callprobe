# didyoureally

Part of the [Callprobe unified repository](../../README.md). Development and issues for both engines live here. Didyoureally remains independently installable from this package directory.

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
# From the Callprobe repository root, using the shared environment:
python3 -m venv .venv
.venv/bin/python -m pip install -e packages/didyoureally
source .venv/bin/activate
cd packages/didyoureally
```

Didyoureally is not yet published. It has no runtime dependencies beyond the standard library.
The relative example and script paths below are resolved from this package directory.
See the [root setup guide](../../CONTRIBUTING.md) to install both development packages.

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
# Also fail when a stated detail has no comparable recorded argument:
dyr check trace.json --fail-on-unchecked
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

Legacy `function_call` messages and populated top-level `functions` definitions
are not supported. They fail as invalid input before model extraction, including
when modern tool calls appear in the same recording. Normalize definitions to
`tools`, calls to `tool_calls`, and results to `role: "tool"` messages with matching
`tool_call_id` values. Preserve result order and explicit outcomes; do not invent
a successful result for a proposed or unfinished call. A null `function_call`
and empty or null `functions` metadata contain no legacy evidence and are allowed.

Planned: OpenTelemetry GenAI spans, OpenAI Agents SDK traces, LangSmith and Langfuse exports.

## Benchmark

`dyr bench` runs 102 bundled sessions with planted failures and honest controls:

```text
102/102 cases exact. Problem detection: precision 100%, recall 100% (52 caught, 0 false alarms, 0 missed).
```

That score uses labeled claims and tests the deterministic matcher. The real LLM extraction
results depend on the model and workload. The latest completed argument-repair regression
run used the same 84-case snapshot with Mistral in both modes:

| Extraction mode | Exact | Precision | Recall | Honest controls with any alarm | Incomplete checks |
|---|---|---|---|---|---|
| Default | 84/84 | 100.0% | 100.0% | 0/39 | 0 |
| Staged | 74/84 | 93.0% | 93.0% | 4/39 | 2 |

These are known development cases, and exact verdict counts do not prove perfect extraction.
Default mode also had one detail-free claim disagreement and one intentionally unchecked
recipient. The run predates the two identical-action cases and the subsequent repair-count fix.
See the [complete regression evidence](results/argument-repair-regression/README.md).

An earlier staged evaluation used 32 synthetic
sessions across deployment, inventory, billing, and publishing:

| Model | Exact | Precision | Recall | Honest controls with any alarm | Incomplete checks |
|---|---|---|---|---|---|
| mistral-nemo:latest | 32/32 | 100.0% | 100.0% | 0/20 | 0 |
| qwen2.5:7b | 30/32 | 92.3% | 100.0% | 1/20 | 1 |
| hermes3:8b | 24/32 | 66.7% | 83.3% | 5/20 | 3 |
| granite3.3:8b | 11/32 | 45.5% | 41.7% | 6/20 | 15 |

The honest-alarm count includes unmentioned-action warnings. The earlier broader staged
Mistral run scored 61/82, or 63/82 after a [label audit](results/partial-action-label-audit/README.md)
of its saved predictions. Staged mode remains opt-in. The
[earlier fixed-action evaluation](results/fixed-action-validation/README.md) retains the
original comparisons and raw evidence. These small synthetic evaluations do not establish production accuracy.

`dyr bench --llm --json-mode` evaluates extraction with the configured model. Add cases in
`scripts/build_benchmark.py` and regenerate; do not edit generated JSON directly.

## Scope and limits

- Corrections do not erase earlier claims. A session can contain an earlier contradicted claim and a later backed correction. There is no separate resolved status yet.
- Numeric comparisons use exact decimal values, not relative tolerance. Explicit currency and percentage labels are preserved; bare numbers use the same argument's convention. Dollar symbols and cents currently mean USD. Unknown field mappings, including `amount` versus `amount_cents`, remain unchecked rather than being guessed.
- A backed finding can still have unchecked details. Use `--fail-on-unchecked` to make these exit 1 in CI, even when the action itself is backed. It does not detect details omitted by the extractor.
- Unmentioned calls are advisory by default. Two successful duplicate calls are separate events; the trace does not establish whether the backend deduplicated their effects.

- It checks what the agent **said it did** against what it **called**. It does not know whether the call itself was the right decision (that's what behavioral test suites are for) or whether the tool did what its name promises.
- Claims are only as good as extraction. Vague claims ("I took care of it") map to a tool with no details, so they can be phantom but never contradicted.
- It trusts the trace. If your tracing drops calls, you'll get false phantoms.

## Related work

- [callprobe](https://github.com/Eladhirsh/callprobe) now provides an experimental shared agent workflow:
  `callprobe agent run` checks decisions and accounts against recorded mock outcomes, while
  `callprobe audit` exposes this project's trace checks. Agent and extractor models are configured
  separately. See the [joint workflow guide](https://github.com/Eladhirsh/callprobe/blob/main/docs/agent-workflow.md)
  for source installation, the 12-case pilot, evidence, and limits. Didyoureally remains usable independently.
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
the normal source repair hides the earlier request. If that repair still asserts completion but loses the resolved tool and
there are no grounded argument details, one additional focused recovery attempt can restore the
mapping. There are at most three model calls for that message. Failure to retain the mapping
returns an incomplete check with `lost_action_mapping`; the application never inserts a claim
itself. An empty repair can correctly reclassify an acknowledgment and is accepted without recovery.
Literal details already grounded in the message must survive repair. If a parsed
repair drops any, one focused recovery can re-extract from the original isolated
target and grounded details. It does not copy fields into claims automatically.
There are still at most three model calls for that message. Unrecovered details
return `lost_source_detail`; malformed or unsupported values still fail validation.

A backed vague claim means a successful matching action was recorded. It does not establish that
the requested amount, recipient, or other unstated details were correct. Offers such as "I can take
care of it" and disclosures such as "That failed" are not completion claims.

A [mixed-action scope experiment](../../results/2026-10-04-mixed-action-scope/README.md)
improved focused Llama results but regressed contextual completion extraction on
Mistral. That prompt change was rejected; the frozen controls and comparison
evidence remain available for follow-up work.

### Experimental staged extraction

`--extraction-mode staged` separates contextual action identification from argument extraction.
The first stage includes completed read-only actions, which code excludes from side-effect checks.
The second stage sees only the target message and fixed action IDs with tool parameter definitions.
It returns arguments for those IDs; code attaches the resolved tool names. It cannot copy requested
amounts or recipients from earlier messages. Missing IDs or invalid details produce an incomplete
check. Completion classification belongs to the first stage, so its mistakes can still reach the matcher.

```bash
dyr check trace.json --extractor llm --extraction-mode staged --json-mode \
  --base-url http://localhost:11434/v1 --model YOUR_MODEL
```

This mode is opt-in. Each stage allows one validation retry, so a message can require up to four
model calls. Read-only actions and nonclaims stop after the first stage. The default mode keeps
its existing extraction flow and shares source-validation rules. Evaluate staged mode on
representative traces before choosing it for a workload.

Both extractors reject unquoted pronouns used as explicit identifiers or recipients and request
one repair. A quoted identifier such as the filename `"it"` remains valid. This is a narrow check;
literal source validation still cannot prove that a model assigned a word the correct meaning.
Repair feedback identifies invalid argument fields and preserves valid literal details. Default-mode
repairs for null placeholders and unresolved references use only the target message and provisional
tool identities, keeping earlier requested values out of the repair. Invalid details are not silently removed.

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

Incomplete extraction reports include a safe `error.reason`, the target `message_index`, and a recovery `hint`. Reasons distinguish provider failures, unfinished responses, invalid claim format, source mismatches, malformed action groups, and null argument placeholders. The extractor uses the same specific feedback for its normal repair attempt. A lost contextual tool mapping or dropped grounded detail can trigger one additional focused recovery as described above. For source mismatches, that attempt sees the target message, tool definitions, provisional tool names, and literal details already grounded in the target. Earlier conversation values and unsupported arguments are excluded. Format errors retain the rejected reply for a targeted correction. It never repairs claims by copying values from tool results.


## Explicit calendar timestamps

Extraction accepts equivalent full ISO timestamps and English month-name dates
with a year, clock time, and explicit UTC offset. For example, `November 9, 2026
at 10:00 AM with UTC offset -05:00` can ground `2026-11-09T10:00:00-05:00`.
The date, time, and offset must occur together in the target assistant message.
This applies only to `starts_at`, `ends_at`, `start_time`, `end_time`, `datetime`,
and `timestamp`. Identifiers and generic text keep their existing matching rules.

Repair must retain a grounded timestamp, even when another field needs repair.
If an identified timestamp argument is invalid or incomplete, a single unambiguous
full timestamp in the target is retained as repair evidence. Multiple different
timestamps are not assigned to fields by guesswork.
The matcher compares local date, clock time, and offset individually; a different
clock and offset are not equivalent just because they denote the same UTC instant.
Missing years or zones, relative dates, numeric locale-dependent dates, zone
abbreviations, fractional seconds, and unknown `-00:00` offsets are not normalized.
Unsupported forms retain literal handling. No values are inferred from user
requests or recorded calls.

This closes the observed ISO-normalization repair gap. It does not detect details
that the extractor omits on its first attempt. Existing saved claims are not
expanded or rewritten; rerun extraction to evaluate newly preserved date details.

## Completion scope and retry counts

Both extractor modes are instructed to distinguish attempts from asserted successful actions.
"Archived after two attempts" describes one success; "successfully sent two
copies" describes two, even with identical arguments. JSON examples inherit the
surrounding statement's scope: "I will execute these calls" describes a plan,
while "I executed these calls" asserts completion and requires recorded evidence.
A mixed reply keeps its completed actions separate from its future plans.

These are extraction instructions, not keyword-based verdict overrides. The
matcher is unchanged and still checks every extracted claim against the trace.
The new labeled controls exercise both false-alarm patterns and genuine missing
actions. Real extraction remains model-dependent; the labeled benchmark does
not establish that the extractor follows these distinctions on every reply.

A [focused local model check](../../results/2026-10-04-completion-scope/README.md)
records the improvement and remaining limits. In that check, the staged extractor
still flags one future-tense JSON plan. Prefer the default extractor for this
pattern; verify it against your own traces before using its account gate.

## Strict JSON evidence

Trace files, reviewed claim files, and model extraction responses reject duplicate
JSON keys and nonfinite numbers, including overflowing numeric literals such as
`1e400`. OpenAI message adapters apply the same checks to JSON strings inside
recorded arguments and results. Already-decoded native and adapter inputs also
reject nonfinite values. Distinct objects may use the same key normally.

Malformed tool arguments are invalid input instead of becoming empty arguments
or an opaque `_raw` field. Arguments must be an object or a string containing a
JSON object. Omitted arguments still describe an empty object; an explicit null,
empty string, array, or scalar is invalid. Plain-text outcome markers such as
`ok` and `Success!` remain supported.

`dyr check` returns input-error exit code 2 for invalid recordings, with
`status: invalid_input` and no summary in JSON output. Invalid model responses
exhaust their bounded repair or produce an incomplete extraction; they cannot
be a clean empty result. Fix ambiguous recordings at the export source instead
of choosing whichever duplicate value appears last. If a caller has already
parsed duplicate keys with another JSON library, the discarded values cannot
be recovered; use the CLI file loader or retain the original JSON strings.

## Native trace structure

Native traces now validate field shapes before extraction. `tools` and `events`
are arrays of objects. Tool names must be unique, and explicit `side_effect`
values must be JSON booleans. Descriptions are strings; parameter schemas and
recorded arguments are objects. Arrays of key and value pairs are not argument objects.
Reviewed claim arguments follow the same object requirement.

Call IDs must be nonempty strings and unique across the whole trace, including
calls to different tools. Omitted IDs keep their generated `call_<event index>`
form, but cannot collide with explicit IDs. The matcher checks ID uniqueness
again for traces constructed or modified through the Python API. Duplicate IDs
cannot make an extra write disappear from unmentioned-action reporting.

Message content must be a string. Supported roles are `user`, `assistant`,
`system`, `developer`, and `tool`; only user and assistant messages supply
extraction context. Normalize other role names before importing. Trace IDs and
tool names must be nonempty strings. Invalid native records return input-error
exit code 2 instead of silently coercing fields or raising an attribute error.

Omitted optional fields retain their existing defaults: empty tool and event
lists, empty arguments, generated call IDs, and `status: "ok"` for native calls.
Native call events represent already-completed execution. Record explicit
`status: "error"` when execution failed, and use the OpenAI message adapter when
working with proposals and subsequent results. Validation does not verify the
real-world outcome of a supplied native status.

## Chat recording structure

The OpenAI message adapter requires a message array, either directly or under
`messages`. Message and tool entries must be objects. Roles are validated, and
only assistant messages may propose tool calls. Calls require function objects
with nonempty names and IDs; missing names no longer become an invented
`unknown` tool. Unsupported call and tool-definition types return an input error.

Message content may be a string, null, or an array of text parts. A text part has
`type: "text"` and a string `text`; existing untyped objects with string `text`
also work. Refusal parts with `type: "refusal"` preserve their string `refusal`
content. Part text is concatenated in order without adding characters. Other
content parts must be normalized to text before import; they are not silently
dropped or converted to Python object strings.

Missing or null `tool_calls` fields still mean no proposal. Other non-array
values are invalid, even when empty or false. Tool results still need an earlier
pending call and an explicit recognized outcome. Text in a call-proposing
assistant message remains before its result in the trace, so the result cannot
retroactively back that message's completion claim.

Malformed chat recordings return input-error exit code 2 and JSON
`status: invalid_input`, allowing later files in a batch to continue. Empty
message arrays remain valid empty traces. These checks validate the recording
format; they do not establish that all claims were extracted correctly.

## Supplied claim validation

Reviewed claims supplied through `--claims`, embedded `claims`, or `GivenClaims`
must be an array of claim objects. An explicit empty array is valid. Empty objects
and strings are input errors instead of becoming an empty claim set.

Each claim requires nonempty string `text`. Its `tool` is a nonempty string or
null; an unknown tool remains a phantom finding. Arguments must be an object
with finite numeric values. Optional `group_id` values must be nonempty strings.
An explicit `message_index` must be a nonnegative integer identifying a nonempty
assistant message in the normalized trace. User messages, tool-call events,
blank assistant turns, booleans, and nonexistent indices are rejected. The
matcher validates these fields again for directly constructed or modified
Python claims.

Omitted or null `message_index` is resolved only when the normalized trace has
exactly one nonempty assistant message. Matching still requires the supporting
call to precede that message. Traces with multiple possible source messages, or
none, require an explicit index. Previously these claims matched across the
whole session and could use later calls; regenerate reviewed baselines that
relied on that behavior.

Supply the assistant event index when checking multi-message traces. Do not use
a raw chat-array position because adapters omit some turns; inspect `Trace.messages`
for normalized indices. Resolution returns a copy and does not alter the supplied
claim. These checks validate structure and references, not whether reviewed text
and arguments faithfully describe the original reply.
Invalid claims return input-error exit code 2 and `status: invalid_input`, including
when finding gates are disabled. Later files in a CLI batch are still checked.

## Repeated extraction checks

The development benchmark runner supports `--repeats` from 1 to 100 (default 1).
It saves a one-based `repeat_index` and an `endpoint_id` on each record. Targets
with the same model name stay separate; repeated identical endpoint and model
pairs are rejected. Endpoint IDs correspond to command-line order and do not
record endpoint URLs.

From the repository root, use a new output directory:

```bash
.venv/bin/python packages/didyoureally/scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --cases packages/didyoureally/examples/repeat-validation \
  --repeats 3 --json-mode --out /tmp/extraction-repeat-check
```

`report.md` keeps attempt-level error and detection metrics separate from unique
case coverage. `repeat_summary.json` records complete cases, cases exact on every
attempt, mixed exactness, changed outcomes, changed parsed claims, and missing
attempts. An interrupted run retains every completed record and all planned
repeat slots. A case cannot be exact on every attempt when coverage is missing
or an extraction errored. A complete case means all attempts were recorded; its
extractions can still fail.

Changed outcomes compare verdict and tool multisets or extraction error
categories. Changed claims compare parsed claim multisets including arguments
and message positions. Neither stability nor exact verdict counts establish full
claim accuracy. Repeats use the same prompt and temperature zero, so they are
not independent new cases and do not justify independent-sample confidence
intervals. Any non-exact attempt makes a completed run exit with code 1;
interruption returns 130.

The eight cases in `examples/repeat-validation` pair honest controls with phantom,
masked-failure, wrong-detail, and unmentioned-action cases across four domains.
Their generator is `scripts/build_repeat_validation.py`. Freeze cases before
inference and keep the first results before tuning prompts. These are synthetic
development checks, not real MailOps captures or held-out production accuracy.

The [first repeated evaluation](../../results/2026-10-04-extraction-repeats/README.md)
records 72 attempts across three local extractor families. It shows why stable
outputs can still contain repeatable mistakes and why extraction errors need
separate coverage reporting.

### Compare saved extraction runs

Use the offline development comparison script on complete `run_llm_bench.py`
output directories. It makes no model requests and writes a JSON report to stdout:

```bash
.venv/bin/python packages/didyoureally/scripts/compare_llm_runs.py \
  /tmp/extraction-baseline /tmp/extraction-candidate > /tmp/extraction-comparison.json
```

Exit code 0 means no individual verdict regression and no candidate extraction
errors. Exit code 1 means a regression or extraction error. Exit code 2 means
invalid, incomplete, or incompatible evidence. Improvements cannot cancel a
regression on another case. An extraction error fails the gate even when the
baseline had the same error. Existing verdict mismatches are counted explicitly
but do not by themselves constitute a regression.

Runs must have matching suite and runner hashes, model names, case coverage,
repeat counts, JSON mode, and temperature. Every planned record must be present
exactly once. Duplicate JSON keys, nonfinite numbers, inconsistent pass flags,
and changed labels are rejected. Different extraction modes can be compared;
both modes appear in the report. Runtime source and prompt hashes may differ
because changing them is the purpose of a candidate comparison.

Pairing uses model name, case ID, and repeat index; endpoint order can differ.
For multiple endpoints serving the same model name, save separate runs for each
endpoint. Model names do not prove identical weights or server configuration;
retain model digests separately. The report includes input file hashes, but
excludes raw responses, claim arguments, and provider error text.

The gate checks verdict and tool counts. It does not establish argument accuracy,
model stability, or complete claim extraction. Compare the full frozen suite as
well as focused cases: the [mixed-action experiment](../../results/2026-10-04-mixed-action-scope/README.md)
passed the focused comparison while regressing two broader cases.
