# Agent decisions and accounts in one workflow

Callprobe's experimental agent runner combines two independent checks:

- Callprobe compares proposed tool decisions with an authored serial sequence.
- Didyoureally extracts completed-action claims and compares them with recorded mock outcomes.

A wrong refund described accurately fails the decision check and can pass the account check.
A correct email call that fails, followed by "Sent!", can pass the decision check and fail the account check.
There is no combined accuracy score. Each axis remains visible.

## Install from source

Didyoureally is not published yet. Both packages are in this repository. Install them from one checkout:

```sh
# From the Callprobe repository root:
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' -e 'packages/didyoureally[dev]'
```

Existing Callprobe commands do not require Didyoureally. The `agent run`, `agent compare`, and `audit`
commands explain how to install it when missing. Neither package version changes for this pilot.

## Run the refund and receipt pilot

```sh
.venv/bin/callprobe agent init --out refund-pilot.json
.venv/bin/callprobe agent run --suite refund-pilot.json \
  --endpoint http://localhost:11434/v1 --model qwen2.5:7b \
  --extractor-model mistral-nemo:latest --json-mode \
  --out results/refund-pilot-qwen
```

Use models already served by your endpoint. The agent and extractor are configured
independently. Set `--extractor-endpoint` for a different service. Agent credentials
come from `API_KEY` or `OPENAI_API_KEY`; extraction credentials come from `DYR_API_KEY`
or `OPENAI_API_KEY`. Never put credentials in endpoint URLs.

The 12 cases cover refund plus receipt, failed email, successful and unsuccessful
retry, failed refund, refund only, receipt only, an offer without authorization,
EUR, cents converted to dollars, a corrected recipient, and two identical sends.
The agent sees the user request and tool schemas. It does not see the expected
decisions or the mock outcome sequence.

Tools have declarative outcome queues. A schema-valid call consumes its tool's
next outcome, independently of the expected decision. Wrong but schema-valid
arguments are retained and can succeed in the mock. Invalid arguments, unknown
tools, and exhausted outcome queues return explicit errors. No refund, email,
network tool, shell command, or arbitrary user function is executed.

## Evidence and gates

Each new output directory contains:

- `suite.json`: frozen inputs, expected decisions, and mock outcomes.
- `report.md`: separate decision and account results per case.
- `report.json`: model settings, source hashes, versions, coverage, raw completions,
  extraction requests and replies, tool outcomes, claims, and findings.
- `traces/CASE.json`: native traces accepted by Didyoureally.
- `claims/CASE.json`: extracted claims for completed audits, not human ground truth.

The report is checkpointed after each case. Interrupted runs keep completed cases
and a partial status; an interrupted in-flight case is not included. Existing
output directories are refused. Use synthetic data for shareable reports because
transcripts and model responses are retained.

Exit codes: `0` all cases pass both checks; `1` at least one finding or decision
failure; `2` invalid setup or run failure; `3` incomplete generation or extraction;
`130` interrupted. The account gate includes all non-backed findings and unchecked
details. An empty extraction can still miss a phantom claim; a passing account
check is not proof that every claim was extracted.

Audit a trace with fresh extraction:

```sh
.venv/bin/callprobe audit results/refund-pilot-qwen/traces/refund-and-receipt.json \
  --base-url http://localhost:11434/v1 --model mistral-nemo:latest --json-mode
```

Replay just the deterministic matcher offline with saved extracted claims:

```sh
.venv/bin/callprobe audit results/refund-pilot-qwen/traces/refund-and-receipt.json \
  --claims results/refund-pilot-qwen/claims/refund-and-receipt.json \
  --fail-on contradicted,phantom,masked_failure,unmentioned --fail-on-unchecked
```

`audit` forwards the existing Didyoureally check options and exit codes. Its
default policy is Didyoureally's policy; the flags above reproduce the stricter
joint runner account gate.

## Scope of this first integration

The suite format is experimental and separate from ordinary Callprobe suites.
Each expected entry scores one agent turn with the existing Callprobe scorer.
The final entry is `no_call`. Missing turns and extra turns fail coverage.
Multiple calls in a turn fail the serial decision policy, even though each valid
mock call is recorded. Completion text is recorded before that turn's tool results,
so a premature success claim cannot be backed by a later outcome.

This is a controlled agent test runner. It does not evaluate an external framework's
execution loop, verify production side effects, or support arbitrary branching
policies. Model error messages are omitted from evidence, and incomplete responses
never pass the combined gate. Model identity strings and source hashes do not
verify the served model weights.

The next integration work is broader domains and
importing external traces. Keep the two scoring engines independent as those
features are added. Didyoureally remains a dependency-free standalone trace checker.

## Compare agent models offline

```sh
callprobe agent compare results/baseline/report.json results/candidate/report.json \
  --fail-on-regression
```

Both reports must retain their adjacent `suite.json`. The command verifies full
case coverage, suite hashes, source hashes, result consistency, and matching
extractor and request settings. Agent model and agent endpoint may differ. It
compares decisions, accounts, and combined passes separately, listing each
improvement and regression. It requires Didyoureally and replays saved normalized completions against the frozen mock suite, then checks recorded claims with the deterministic matcher. It makes no model calls. Missing or inconsistent decisions, traces, outcomes, findings, or completion evidence are rejected. If installed evaluator behavior no longer reproduces the saved evidence, the comparison exits 2 instead of silently rescoring it.

An improvement in one axis does not cancel a regression in another. With the gate
flag, any regression exits 1; any incomplete case on either side blocks a clean
gate and exits 3. Invalid, partial, or incompatible runs exit 2. Without the gate
flag, a valid comparison exits 0 and remains informational. A passed regression
gate does not mean either run passed every case.

See the [first real-model pilot](../results/2026-10-04-joint-agent-pilot/README.md)
for concrete findings and the original request-capture limitation.

## Authoring expectations

The serial sequence specifies required turns and tool choices. Expected arguments
assert equality for the listed keys; additional schema-valid optional arguments
can still pass. Constrain dangerous options with schema constants or explicit
expected safe values. Literal dotted top-level argument names and external schema
references are rejected by this pilot format.

The runner rejects unsupported legacy function-call envelopes and call-finish
responses with no parsed calls. Reasoning-only output does not count as a final
reply. Raw completions remain in the evidence while trace checks use visible text.
Comparison validates evidence consistency, not cryptographic authenticity or claim
extraction completeness.

The broader frozen suite is in `examples/agent-validation/suite.json`. Regenerate
it with `python scripts/build_agent_validation.py`. It adds files and scheduling
to the original refund and email pilot, for 28 authored scenarios.
