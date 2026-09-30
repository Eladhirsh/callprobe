# AGENTS.md

## What this project is

didyoureally checks whether an AI agent told the user the truth about what it did. It reads an agent transcript plus its tool-call trace, extracts claims about completed actions, and matches each claim against the actual calls.

Verdicts: backed, contradicted, phantom, masked_failure, unmentioned.

These instructions apply to any coding assistant working in this repository. This file is the source of truth; no assistant-specific tooling or external instruction files are required.

## Product scope

- Check whether the agent's account of completed actions agrees with the recorded calls. Do not evaluate whether the agent chose the right action or claim to verify real-world outcomes beyond the trace.
- Support offline trace inspection for CI and eventual sampling of production logs, without controlling the agent.
- Keep the MVP focused on the native JSON schema, one or two adapters, LLM claim extraction, deterministic matching, readable and JSON reports, and configurable CI exit codes.
- Grow the seeded benchmark to about 50 realistic sessions, including planted failures and at least one third honest controls. Separate matcher results using labeled claims from end-to-end results using a real extractor.
- Treat future actions and offers as non-claims. Test partial actions, vague completion claims, units and currencies, read-only lookups, corrections, retries, and repeated calls.
- Prioritize OpenTelemetry GenAI as the next adapter. Consult current official semantic conventions before implementing it. Other framework adapters remain future work.

## Setup

Before running anything, make sure the project is installed in a local virtual environment. If `.venv` is missing or `.venv/bin/dyr` does not exist, run:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Always call tools through `.venv/bin/` so commands work whether or not the venv is activated. If a command is "not found", run the setup above instead of stopping.

## Commands

```bash
.venv/bin/pytest -q                 # all tests, no network
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/dyr bench                 # benchmark with labeled claims (tests the matcher)
.venv/bin/dyr bench --llm           # end to end, needs DYR_BASE_URL, DYR_API_KEY, DYR_MODEL
.venv/bin/python scripts/build_benchmark.py   # regenerate benchmark JSON after editing cases
```

If the commands are missing, install the development environment first. Missing executables are setup failures, not evidence of failing project tests. After setup, stop and report any failing baseline check before changing implementation. The initial scaffold expects 23 tests and 10 benchmark cases; update those expectations as coverage grows.

The same commands can be run through `.venv/bin/` without activating the environment. Never commit the environment, credentials, or local assistant metadata.

## Layout

- `src/didyoureally/schema.py`: Trace, ToolSpec, ToolCall, Message, Claim. Every event has an `index` in session order.
- `src/didyoureally/matcher.py`: deterministic matching and verdicts. `values_agree` holds all normalization.
- `src/didyoureally/extract.py`: `GivenClaims` and `LLMExtractor` (OpenAI-compatible, stdlib HTTP, injectable transport).
- `src/didyoureally/adapters.py`: format detection and the OpenAI chat messages adapter.
- `src/didyoureally/bench.py`, `report.py`, `cli.py`: benchmark runner, output, CLI (`didyoureally` and `dyr`).
- `scripts/build_benchmark.py`: source of truth for benchmark cases. Never hand-edit `src/didyoureally/benchmark/*.json`.

## Rules

- The LLM only extracts claims. Verdicts are always decided by plain code in `matcher.py`. Do not add LLM judging.
- A claim can only be backed by a call that happened before the message containing it.
- Details that can't be compared go in `unchecked`. Never pass them silently or fail them silently.
- No runtime dependencies. Stdlib only in `src/`. Dev tools go in the `dev` extra.
- Tests must not touch the network. Use the `transport` argument to fake LLM responses.
- Every new verdict rule or adapter needs tests, and every new failure pattern needs a benchmark case plus an honest control case that must not be flagged.
- Run `.venv/bin/pytest -q`, `.venv/bin/ruff check .`, and `.venv/bin/dyr bench` before committing. All must pass.
- Commit each completed development step separately and report what changed and any unexpected findings.
- Run real model benchmarks only with configured endpoints and credentials. Do not fabricate results or describe labeled-claim scores as end-to-end scores. Keep credentials out of logs and result files.
- Prepare release infrastructure without changing the version or publishing until the user explicitly authorizes publication. A package-name availability check is time-sensitive and does not reserve the name.

## Writing style for docs and output

- No em dashes. No forward slashes as connectors in prose.
- Sentence case for headings and labels. No all-caps.
- US spelling. Direct, plain language.
