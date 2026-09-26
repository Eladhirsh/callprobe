# AGENTS.md

## What this project is

didyoureally checks whether an AI agent told the user the truth about what it did. It reads an agent transcript plus its tool-call trace, extracts claims about completed actions, and matches each claim against the actual calls.

Verdicts: backed, contradicted, phantom, masked_failure, unmentioned.

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

## Writing style for docs and output

- No em dashes. No forward slashes as connectors in prose.
- Sentence case for headings and labels. No all-caps.
- US spelling. Direct, plain language.
