# Running Callprobe

How to check an endpoint, run a suite, save settings, preview a run, and rerun failures. Start with the [quickstart](../README.md#quickstart) if you have not run Callprobe before.

## Install the development version

The `main` branch is the unpublished `0.9.0rc3.dev0`. From a checkout, run
`uv tool install . --force`, or install into a virtual environment and use the
same interpreter to run it:

```bash
python -m pip install .
python -m callprobe --version
python -m callprobe examples
```

`python -m callprobe` works wherever these guides use `callprobe` and avoids
relying on the environment's scripts directory being on `PATH`. The module
entry point is not available in 0.9.0rc2 or earlier.

## Check endpoint setup (unreleased 0.9.0rc3.dev0)

With this development checkout installed, check your suite and endpoint before
starting a benchmark:

```bash
callprobe doctor --model qwen2.5:7b --suite callprobe-demo
callprobe doctor --model your-model --endpoint http://localhost:8080/v1 --format json
callprobe doctor --config callprobe.yaml --format json
```

`doctor` validates the suite locally, then uses `GET /models` to check endpoint
access and look for the exact model ID. It may also read public server metadata.
It never generates tokens, downloads models, executes tools, follows redirects,
or writes files. Authentication uses `--api-key`, `API_KEY`, or `OPENAI_API_KEY`,
in that order; response bodies, endpoint URLs, and credentials are omitted from
endpoint diagnostics. `--timeout` sets a positive HTTP operation timeout
(default 5 seconds), not a total command deadline.

A missing model or unsupported model-listing route is a warning: some providers
accept aliases or restrict their catalogs. A catalog match verifies discovery,
not tool-calling support or model quality. Run a small suite to test those.
Exit codes are `0` for completed checks (possibly with warnings), `1` for endpoint
failures, and `2` for invalid local input or suites. JSON includes `status`,
individual `checks`, `model_listed`, and `generation_tested: false`.

`doctor --config FILE` reads the same explicit YAML file as `run`. It uses the
file's model, endpoint, and suite defaults; explicit CLI flags take precedence.
A suite path from the file resolves relative to that file, while a CLI suite
path resolves relative to the current directory. The whole file must be valid,
including settings that doctor does not use. Credentials remain outside the file.

Run-only settings such as `out`, retries, padding, and `request_timeout` do not
change doctor's behavior or cause writes. Its discovery timeout remains 5 seconds
unless `--timeout` is supplied. Use `run --config FILE --dry-run` to validate the
planned experiment and preview coverage without endpoint access.

## Usage

```bash
# a single model
callprobe run --model llama3.1:8b --pad 0,8 --repeats 3 \
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

In 0.9.0rc2, use `--request-timeout 300` to allow
longer waits for slow local models, or set `request_timeout: 300` in a YAML
run config. The default is 120 seconds. Values must be positive and finite.
This configures HTTPX connect/read/write/pool operation timeouts; it is not
a total wall-clock deadline for a request or a run. Retries can add more time.
The effective value is included in dry-run plans and saved run metadata;
historical files leave it unknown. Changing a transport timeout does not
change scoring or make otherwise compatible baselines incompatible.

`sweep --request-timeout 300` forwards the same setting to each model run.
The GitHub Action in this checkout exposes the same `request-timeout` input.
`sweep --timeout` controls the entire subprocess step (default 1800
seconds); increase that separately when a whole suite needs more time.

`--max-tokens` defaults to 2048. Reasoning models can need more (see
[truncation](findings.md#why-your-tool-calling-numbers-are-probably-wrong)).

Starting with 0.9.0rc1, `run` and the GitHub Action default to `--pad 0`:
a baseline without distractors. Additional counts are explicit, for example
`--pad 0,8` on the core suite or `--pad 0,2,4` on the mail example. The requested
count must fit every selected task after exclusions and tool-name collisions;
impossible counts fail before endpoint access instead of silently sending fewer
tools. The core suite supports up to 15 distractors for every task.

Earlier versions defaulted to `0,8,16` and could silently cap padding at the
available pool size. Collect a new baseline with valid, explicit counts when
migrating such experiments; do not relabel old observations.

For a controlled multi-model sweep, use already-served models (0.9.0rc1):

```bash
callprobe sweep --models qwen2.5:7b llama3.1:8b \
  --out /tmp/callprobe-model-plan --dry-run
callprobe sweep --models qwen2.5:7b llama3.1:8b \
  --out /tmp/callprobe-model-results
```

The runner plans requests first, uses a fresh output directory, and saves a
manifest, per-model evidence, and a leaderboard from that sweep alone.
Use `--suite` for your own tools; see the [mail sweep guide](../examples/mail-sandbox/README.md#sweep-several-local-models).
This command is available starting with 0.9.0rc1; it is
not included in PyPI 0.8.0. It does not download models. The older `scripts/overnight.sh` is a legacy
convenience script that pulls models and combines files in `results/`.

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

### Save run settings (since 0.8.0)

Use an explicit YAML configuration to repeat an experiment without copying
all its flags. For example, save this as `callprobe.yaml` beside your
`my-support-suite` directory:

```yaml
model: qwen2.5:7b
endpoint: http://localhost:11434/v1
suite: my-support-suite
pads: [0]
repeats: 1
max_tokens: 4096
```

```bash
callprobe run --config callprobe.yaml --out baseline.json
callprobe run --config callprobe.yaml --model qwen3:8b --out candidate.json
callprobe compare baseline.json candidate.json --fail-on-regression
```

The endpoint must be running with the requested model available. Explicit
CLI flags override file settings, and omitted settings keep the normal CLI
defaults. There is no automatic configuration discovery. `model` must be
provided in the file or with `--model`.

Accepted keys are `model`, `endpoint`, `suite`, `pads` (an integer list),
`repeats`, `temperature`, `max_tokens`, `quant`, `notes`, `retries`,
`concurrency`, and `out`; 0.9.0rc2 also accepts `request_timeout`. Unknown fields, duplicate keys, nulls, wrong
types, and invalid numeric values are rejected even when a CLI flag would
override them. `suite` and `out` in YAML resolve relative to the config
file; paths supplied on the CLI remain relative to your working directory.
The output cannot overwrite the configuration file.

Keep credentials in `API_KEY`/`OPENAI_API_KEY` or use `--api-key`; credential
fields are not accepted in YAML. Targeting, resume, and CI gate options
remain explicit CLI flags. Saved results record the effective experiment
settings, and the existing resume and suite-matching checks still apply.

Available since 0.8.0. Install with `uv tool install callprobe@latest`.

### Preview a run before spending tokens (0.9.0rc1)

In the unreleased development version, both `run` and `run --dry-run` validate
the complete suite before endpoint access, including unused distractors and
expected arguments. Invalid suites exit with code `2` without changing output
files. Run `callprobe validate --suite YOUR_SUITE` for detailed diagnostics
(or `callprobe validate` for the bundled suite).

`--dry-run` merges `--config` and CLI flags, resolves `--suite`, and applies
`--task`/`--failed-from` selection, then prints the resulting coverage and a
planned request count and completion-token cap &mdash; it never probes the endpoint, never
calls the model, and never writes `--out`:

```bash
callprobe run --config callprobe.yaml --model qwen3:8b --dry-run
```

The plan reports the model, suite label and hash, full vs. targeted scope
(selected task ids or the full task count), the requested distractor counts,
repeats, total planned requests (`tasks * pads * repeats`), temperature,
`max_tokens`, concurrency, and `max_completion_tokens`, the request count
times `max_tokens` &mdash; an upper bound a model could reach if every
response used its full budget. This excludes prompt tokens and retries; it
is not a billing estimate. Requested distractor counts must fit every selected task; impossible counts
are rejected before endpoint access. `--format json` emits
the same plan as JSON with `"dry_run": true`. It never prints API keys,
endpoint credentials, the endpoint URL, prompts, or tool arguments, and it
reports no benchmark percentages, since no model was called. `--failed-from`
with no failures still prints its existing no-op message and exits `0`
without producing a plan. `--dry-run` cannot be combined with `--resume` or
`--fail-under`, because a dry run neither resumes nor produces scored results; this is
rejected before any file is read. This flag is not yet available in the
published 0.8.0 package.

### Targeted debug reruns (since 0.8.0)

`--task ID` (repeatable) runs only those exact task ids instead of the whole
suite, using the current `--pad`/`--repeats`/model settings:

```bash
callprobe run --model llama3.1:8b --task args-partial-refund --task abstain-chitchat
```

`--failed-from RESULTS.json` reruns every task id that had a strict failure,
truncation, or request error anywhere in that saved run (it can be a partial
or interrupted run), deduplicated, in the suite's own task order. It does
not reuse or merge the saved observations, only the task ids; only the
current CLI settings decide how those tasks are re-probed. If nothing in the
source failed, it prints a no-op message and exits `0` without making any
endpoint request or touching `--out`. `--task` and `--failed-from` are
mutually exclusive, and neither can be combined with `--fail-under`:
targeted runs are for debugging, not CI gating. `--out` is rejected if it
would alias the `--failed-from` file, including via a symlink or hardlink,
so the evidence a rerun is diagnosing can never be overwritten. Unknown task
ids and a `--failed-from` file with an incompatible or missing suite/scoring
provenance are rejected before any endpoint probing, client creation, or
output write.

A targeted run's result file records which task ids were selected
(`selected_task_ids`) alongside the full suite's ids (`task_ids`), and
`--resume` only reuses a checkpoint from the same selection (or the same
full-suite run) &mdash; a full run and a `--task`-scoped run of the same
suite cannot resume each other. `callprobe run --format json`,
`callprobe run` (text), and `callprobe compare` all label targeted runs
plainly so a debug rerun is never mistaken for full benchmark coverage;
`callprobe compare` without a gate flag proceeds with a warning, but
`--fail-on-regression`/`--policy` and `callprobe leaderboard` (even with
`--allow-mixed`) both refuse a targeted run outright. `callprobe explain`
works the same way against a targeted run's results, since it only needs
the recorded suite hash to match.

Results include every structured tool call (`calls`), its ID, parsed and raw
arguments, parse errors, and `finish_reason`. This evidence is retained for
both passing and failing responses. Review result files before sharing:
tool arguments can contain application data.

`callprobe leaderboard` refuses to build a table across runs from
different suite versions or content, since the numbers would not be
comparable. Pass `--allow-mixed` to build it anyway.
