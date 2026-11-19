# AGENTS.md

## What this project is

Callprobe tests AI agents in two independent ways:

- **Decisions:** whether a model chooses the right tool calls, with valid and correct arguments, and abstains when no tool applies.
- **Accounts (Didyoureally):** whether the agent's description of completed actions agrees with its recorded tool calls. Verdicts are backed, contradicted, phantom, masked_failure, and unmentioned.

Both ship in the single `callprobe` package under the MIT license. Didyoureally was a separate Apache-2.0 package until 0.9.0; its sole author relicensed it to MIT when it was merged.

## Repository layout

- `src/callprobe`: decision scoring, the CLI, the mock agent runner, reports, and CI gates.
- `src/callprobe/didyoureally`: claim extraction and deterministic trace matching (`callprobe audit`).
  - `schema.py`: Trace, ToolSpec, ToolCall, Message, Claim. Every event has an `index` in session order.
  - `matcher.py`: deterministic matching and verdicts. `values_agree` holds all normalization.
  - `extract.py`: `GivenClaims` and `LLMExtractor` (OpenAI-compatible, stdlib HTTP, injectable transport).
  - `adapters.py`: format detection and the OpenAI chat messages adapter.
  - `strict_json.py`: duplicate-key and finite-number validation for evidence.
  - `bench.py`, `report.py`, `cli.py`: benchmark runner, output, and the `callprobe audit` command.
  - `benchmark/*.json`: generated benchmark cases. Never hand-edit them.
- `tests/didyoureally`, `scripts/didyoureally`, `examples/didyoureally`, `results/didyoureally`: tests, generators and runners, frozen suites, and evidence for the account checks.

## Setup and checks

Use the repository-root virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Always call tools through `.venv/bin/` so commands work whether or not the venv is activated. If a command is "not found", run the setup above instead of stopping.

Before each development commit, run:

```bash
.venv/bin/pytest -q tests
.venv/bin/ruff check src/callprobe/didyoureally tests/didyoureally scripts/didyoureally
.venv/bin/ruff format --check src/callprobe/didyoureally tests/didyoureally scripts/didyoureally
.venv/bin/callprobe audit bench
```

Also run Ruff on changed shared agent workflow modules (`agent_session.py`, `agent_compare.py`, and their tests; see the `agent-lint` CI job). Do not reformat unrelated legacy Callprobe modules. Tests must use scripted transports; existing loopback integration tests need local socket access but no external services. Stop and report a failing baseline before implementation changes.

Other useful commands:

```bash
.venv/bin/callprobe audit bench --llm
.venv/bin/python scripts/didyoureally/build_benchmark.py
```

## Development rules

- Preserve independent decision and account results; no blended trust score.
- The LLM extracts claims only. Matcher verdicts are always decided by plain code in `matcher.py`. Do not add LLM judging.
- A claim can only be backed by a call that happened before the message containing it.
- Details that can't be compared go in `unchecked`. Never pass them silently or fail them silently.
- Mock outcomes are independent of expected decisions. Never treat a proposed call as successful execution.
- Never execute real business tools in the agent validation runner.
- Incomplete model output, extraction, or evidence cannot produce a passing gate.
- Keep `src/callprobe/didyoureally` dependent on the standard library only, so it never needs more than Callprobe's core dependencies.
- Expose account checks through `callprobe audit` and `callprobe agent`. There are no separate `dyr` or `didyoureally` commands.
- Frozen suite generators are the source of truth. Do not hand-edit generated benchmark or suite JSON; change `scripts/didyoureally/build_*.py` or `scripts/build_agent_validation.py` and regenerate.
- Every new verdict rule or adapter needs tests, and every new failure pattern needs a benchmark case plus an honest control case that must not be flagged.
- Keep live model evidence separate from scripted plumbing checks. Use configured endpoints and installed models only. Do not fabricate results or describe labeled-claim scores as end-to-end scores.
- Save source hashes, frozen suites, errors, and coverage. Do not claim accuracy from pass counts alone.
- Never commit credentials, local virtual environments, or assistant metadata. Keep credentials out of logs and result files.
- Commit completed steps separately and push authorized work. Do not bump versions, create release tags, or publish packages without explicit approval.

## Account check scope

- Check whether the agent's account of completed actions agrees with the recorded calls. Do not evaluate whether the agent chose the right action (that is the decision check) or claim to verify real-world outcomes beyond the trace.
- Support offline trace inspection for CI and eventual sampling of production logs, without controlling the agent.
- Treat future actions and offers as non-claims. Test partial actions, vague completion claims, units and currencies, read-only lookups, corrections, retries, and repeated calls.
- Prioritize OpenTelemetry GenAI as the next trace adapter. Consult current official semantic conventions before implementing it.

## Writing style for docs and output

Use plain US English, direct language, and sentence-case headings and labels. No em dashes, no all-caps, and no forward slashes as connectors in prose.
