# AGENTS.md

## Repository layout

Callprobe is the unified development home for tool-decision checks and Didyoureally trace checks.

- `src/callprobe` contains the decision scorer, shared CLI, mock agent runner, and comparison gates.
- `packages/didyoureally` contains the independently packaged claim extractor and deterministic matcher.
- Read `packages/didyoureally/AGENTS.md` before changing that engine.
- Keep Callprobe's MIT license and Didyoureally's Apache-2.0 license with their respective code.

## Setup and checks

Use the shared repository-root virtual environment. Install with:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]" -e "packages/didyoureally[dev]"
```

Before each development commit, run:

```bash
.venv/bin/pytest -q tests
.venv/bin/pytest -q packages/didyoureally/tests
.venv/bin/ruff check packages/didyoureally
.venv/bin/ruff format --check packages/didyoureally
.venv/bin/dyr bench
```

Run Ruff on changed shared-workflow modules using the Didyoureally configuration.
Do not reformat unrelated legacy Callprobe modules. Tests must use scripted transports;
existing loopback integration tests need local socket access but no external services.
Stop and report a failing baseline before implementation changes.

## Development rules

- Preserve independent decision and account results; no blended trust score.
- The LLM extracts claims only. Matcher verdicts remain deterministic.
- Mock outcomes are independent of expected decisions. Never treat a proposed call as successful execution.
- Never execute real business tools in the agent validation runner.
- Incomplete model output, extraction, or evidence cannot produce a passing gate.
- Keep Didyoureally runtime dependency-free. Do not copy its source into the Callprobe wheel.
- Preserve standalone `dyr` and `didyoureally` commands and the shared `callprobe` commands.
- Frozen suite generators are the source of truth. Do not hand-edit generated benchmark JSON.
- Keep live model evidence separate from scripted plumbing checks. Use configured endpoints and installed models only.
- Save source hashes, frozen suites, errors, and coverage. Do not claim accuracy from pass counts alone.
- Never commit credentials, local virtual environments, or assistant metadata.
- Commit completed steps separately and push authorized work. Do not bump versions, create release tags, or publish packages without explicit approval.

Use plain US English, sentence-case headings, and no em dashes in new documentation.
