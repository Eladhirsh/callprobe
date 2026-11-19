# Testing your own tools

How to build a suite from an OpenAPI document, a bundled example, or hand-written YAML, and how to score decisions your application already recorded.

## Build a suite

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

Since 0.9.0, validation checks every tool and
distractor's JSON Schema, including unused tools. Duplicate names within a
bundle or the distractor pool are rejected. Expected-argument checks resolve
local references offline; external or unresolvable references produce a
diagnostic when encountered, without fetching them. Validation checks the
authored expectations, not every possible argument or reference path.

Try the [six-test support API walkthrough](../examples/openapi/README.md) for a
complete example with human-authored expectations. The imported API is never
executed, and no API credentials are needed.

For a real API contract, try the [GitHub issue and comment evaluation](../examples/github-issues/README.md):
18 authored cases against three operations from a pinned copy of GitHub's
official OpenAPI specification. It covers identifiers, pagination, comment
text, conversation corrections, and abstention without executing GitHub calls.

`--from-openapi` is available since 0.6.0. Install it with
`uv tool install callprobe@latest`. Earlier versions only support `--from tools.json`.

### Try a bundled example (since 0.8.0)

`callprobe examples` and `callprobe init --example NAME` ship the OpenAPI
documents and human-authored tasks above *inside the installed package*, so
setup and validation need no checkout of this repository or network access.
Running the suite requires a model endpoint; the command below assumes
`qwen2.5:7b` is available in Ollama at `http://localhost:11434/v1`:

```bash
callprobe examples
callprobe init --example support --out my-support-suite
callprobe validate --suite my-support-suite
callprobe run --suite my-support-suite --model qwen2.5:7b --pad 0 --repeats 1 --out my-support-suite/baseline.json
```

Unlike `--from-openapi`, `--example` writes a suite with its tasks already
active; there is nothing to uncomment first. Available since 0.8.0; install
with `uv tool install callprobe@latest`.

Starting with 0.9.0, `mail-sandbox` includes 18 fictional mail cases
covering search, retrieval, draft/send, missing identifiers, and literal text.
Run `callprobe init --example mail-sandbox --out my-mail-suite` to get active
cases and four distractors without downloading or copying repository files.
It is not a MailOps integration.

### Write a suite directly

A suite is a directory of four YAML files: `suite.yaml`, `tools.yaml`,
`distractors.yaml`, and `tasks.yaml`. Drop your real tool schemas into `tools.yaml`,
write tasks against them, and run. The [scenario format guide](scenario-formats.md#tool-decision-suites)
documents every field.

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

## Score application recordings (since 0.9.0)

Applications can score their captured tool decisions directly in Python without
an OpenAI-compatible HTTP proxy. Install Callprobe 0.9.0 or later into the application's
Python environment, then create a suite with `callprobe init --example support
--out support-suite`. For example, this **synthetic recorded decision** exercises
the adapter without calling a model or executing an order lookup:

```python
from pathlib import Path

from callprobe.client import Completion
from callprobe.loader import load_suite
from callprobe.models import Call, RunConfig
from callprobe.recordings import RecordedCompletion, score_recordings

suite = load_suite(Path("support-suite"))
config = RunConfig(
    model="application-model", endpoint="recorded://local", suite="support-suite",
    pads=[0], repeats=1, temperature=0.0, max_tokens=4096,
)
record = RecordedCompletion(
    task_id="status-by-id",
    completion=Completion(calls=[Call(
        name="get_order", arguments={"path": {"order_id": "ORD-448120"}},
    )]),
)
run = score_recordings(suite, config, [record])
with Path("recorded-results.json").open("x", encoding="utf-8") as output:
    output.write(run.model_dump_json(indent=2) + "\n")
```

Inspect the output with `callprobe report recorded-results.json --format text`.
Only one of six tasks was supplied, so coverage remains incomplete. Supply every
planned `(task_id, pad, repeat)` for a complete run; targeted selections remain
labeled as debug runs. Duplicate and out-of-plan records are rejected before any
scoring. Missing observations are never invented. The Python adapter also rejects
invalid completion field types before scoring the batch: calls must be a list of
`Call` objects, text fields must be strings, token counts must be nonnegative
integers (not booleans or strings), and latency must be finite and nonnegative.
Use `parse_completion` for provider-specific normalization first. Invalid adapter
data raises `ValueError`; it is not a model failure or a successful abstention.

Replace the synthetic `Completion` with your application's captured final model
decision, retaining **every** tool call, parse failure, finish reason, request
error, token count, and latency. `Completion(error="...")` represents a failed
request; an empty error string is also a request error. An empty successful
`Completion` means the model made no tool call. OpenAI-compatible response bodies
can be decoded with `callprobe.client.parse_completion(body, latency_ms=...)`;
malformed response envelopes raise an exception and must not become successful
empty completions. Other providers need an adapter to the same `Completion`
fields. This API evaluates one decision, not a whole agent execution trace.

Explicit provider refusals and unsupported legacy `function_call` responses are
request errors. Normalize legacy calls to the supported `tool_calls` format
before importing them. Interrupted or unsupported finish reasons, including
`content_filter`, and a `tool_calls` finish without calls cannot pass scoring.
These failures survive export and replay. Omitted finish metadata remains
compatible; `length` remains a scored truncation failure.

Rebuild affected baselines and candidates before CI comparisons. Scoring version
3 is unchanged; `report`, `compare`, and `--resume` do not revalidate saved provider
responses. Replay can correct normalized recordings that retained an unsupported
finish reason. Older exports may have discarded refusal or legacy call fields,
which replay cannot recover. Reimport the original provider responses with the
current parser, or collect fresh responses when the originals are unavailable.
Write new result files and do not resume affected saved runs.

Use the same task messages, tools, padding, and generation settings that produced
the recordings. For padded runs, `callprobe.runner.build_toolset(suite, task, pad,
seed=repeat)` supplies the deterministic tool bundle/order. The model and generation
metadata are caller assertions: CallProbe cannot verify how external recordings
were produced. Evaluation timestamps describe this scoring pass. Scores use the
current rubric and suite provenance; this differs from `report`, which only reads
saved scores. No model request or application tool is executed by this API.

### Native Ollama recordings

For applications using Ollama's native `/api/chat` endpoint, normalize the full
response captured with `stream: false` before passing it to the recording API:

```python
from callprobe.adapters import parse_ollama_completion

# body is your already-captured native response, not an OpenAI-compatible one.
completion = parse_ollama_completion(body, latency_ms=measured_request_ms)
record = RecordedCompletion(task_id="status-by-id", completion=completion)
run = score_recordings(suite, config, [record])
```

This offline adapter preserves every native tool call, `thinking` text, prompt
and generated token counts, and the finish reason (including `length` for
truncation). It expects the [native chat response format](https://docs.ollama.com/api/chat);
SDK callers can pass `response.model_dump()`. It rejects error envelopes,
incomplete responses, and load/unload acknowledgements. Do not pass individual
stream chunks, including the terminal chunk: collect the complete non-streaming
response instead. Server duration is not used as client latency; supply your
measured milliseconds, or leave latency unknown/zero. The adapter makes no HTTP
requests and changes neither the CLI's OpenAI-compatible endpoint nor scoring.
The response's `raw` field retains the input body locally; recordings export
continues to exclude raw provider bodies while preserving decision evidence.

### Export application recordings

Use `recordings_to_json` to export the same normalized records for offline replay,
without constructing the JSON document by hand:

```python
from callprobe.recording_io import recordings_to_json

payload = recordings_to_json(config, [record])
with Path("recordings.json").open("x", encoding="utf-8") as output:
    output.write(payload)
```

Serialization validates the v1 format before any file is opened. It preserves all
calls, errors, text, token counts, latency, and supplied coordinates. Raw provider
bodies, endpoint settings, local suite paths, and run notes are excluded. Response
text and tool arguments can still contain private data; this is not a redaction
function. Non-JSON argument values (including tuples and non-string object keys)
are rejected rather than converted. Suite membership, duplicate coordinates, and
coverage remain checks for scoring/replay. No model or file is accessed by the
serializer; the example uses exclusive creation to avoid overwriting an export.

### Replay a recordings file

Since 0.9.0, `replay` accepts normalized JSON recordings directly. The example file below is in this repository:

```bash
callprobe init --example support --out replay-suite
callprobe replay examples/recordings/support.json --suite replay-suite --out replay-results.json
callprobe report replay-results.json --format json
```

The bundled file is a **synthetic single-decision example**, not model accuracy
evidence. It scores one of six support tasks and reports five missing observations.
Your application can emit this version 1 format:

```json
{
  "schema_version": 1,
  "config": {
    "model": "application-model",
    "pads": [0],
    "repeats": 1,
    "temperature": 0.0,
    "max_tokens": 4096
  },
  "records": [
    {
      "task_id": "status-by-id",
      "pad": 0,
      "repeat": 0,
      "completion": {
        "calls": [{"name": "get_order", "arguments": {"path": {"order_id": "ORD-448120"}}}],
        "finish_reason": "tool_calls"
      }
    }
  ]
}
```

All five shown config fields are required; generation settings must describe the
original request. Optional config fields are `quantization` and
`selected_task_ids`. Each record requires `task_id` and `completion`; `pad` and
`repeat` default to zero. Completion fields are `calls` (default `[]`), `content`,
`reasoning`, `finish_reason` (default empty strings), `error` (default `null`),
`prompt_tokens`, `completion_tokens`, and `latency_ms` (default zero). Preserve
actual measurements when available; omitted measurements are unknown zeros, not
fresh measurements. Calls require `name`; optional fields are `arguments`
(default `{}`), `id`, `raw_arguments`, and `parse_error`. Keep malformed arguments
in `raw_arguments` with `parse_error` set, and retain every call.

An explicit `"completion": {}` means a successful response with no tool calls;
an omitted completion is invalid. Use `"completion": {"error": "timeout"}` for
a request failure, never an empty completion. Unknown fields, duplicate JSON
keys, non-finite numbers, coerced types, and unsupported versions are rejected.
This format accepts normalized decisions, not raw provider response envelopes or
already-scored CallProbe results.

`replay` reads the suite and recordings locally, scores with the current rubric,
and writes ordinary results with endpoint `recorded://local`. It does not contact
a model, execute tools, or infer missing observations. The same provenance and
single-decision limitations as the Python API apply. Existing output requires
`--force`; source recordings and suite files are protected even through file
aliases. Invalid input or failed writes leave existing results intact. A successful
export exits `0` even for model failures or partial recordings; invalid input exits
`2`. Use `compare --fail-on-regression` on complete matched results for CI gating.
