# Synthetic mail sandbox

Reusable fixtures and a scripted QA agent that test CallProbe with itself.

**This is a synthetic mail workflow, authored here. It is not MailOps and does not
reproduce MailOps compatibility or any figure (for example a 92% pass rate) reported
by anyone else.** We have neither that API nor its code. All addresses use
`example.invalid`, and no real mail API is ever called.

## Files

| File | Purpose |
| --- | --- |
| `openapi.yaml` | Three operations: `search_messages` (query), `get_message` (path), `send_reply` (path + body with `mode: draft\|send`). Arguments keep the imported nested shape. |
| `tasks.yaml` | 18 authored cases: search, get-message, reply, missing identifiers, draft-only and no-send, unsupported delete/forward, body punctuation, identifiers, conversation correction. |
| `distractors.yaml` | Four independent padding tools (calendar, contacts, reminders, documents). |

## Run the self-test

From a checkout, with an interpreter that has CallProbe installed:

```sh
.venv/bin/python scripts/selftest_agent.py --out /tmp/callprobe-selftest
```

To test a built wheel, install it into a clean environment and pass that interpreter:

```sh
python -m venv /tmp/wheel-env && /tmp/wheel-env/bin/pip install dist/callprobe-*.whl
.venv/bin/python scripts/selftest_agent.py --out /tmp/callprobe-wheel-selftest \
  --python /tmp/wheel-env/bin/python
```

`--out` must be new or empty (otherwise the runner exits 2 and touches nothing).
The CLI runs as `python -m callprobe.cli` from that directory, with `PYTHONPATH` and
`PYTHONHOME` removed and no shell. The runner exits 0 on PASS and 1 on any unexpected
failure; a report is written either way.

## What it does

`--version`, `init --from-openapi`, copy the authored tasks and distractors, `validate`,
`run --dry-run`, then two runs against a loopback-only scripted server (`/v1/chat/completions`):
18 tasks x pads 0,2,4 x 3 repeats = 162 observations each.

- **baseline** replies with exact calls built from each case's authored expectation: 162/162.
- **candidate** injects four fixed failures (two missing calls on `search-by-subject` and
  `get-by-id`, one unexpected call on `get-missing-id`, one malformed nested argument on
  `reply-send`): 126/162.

Then `compare --fail-on-regression` (JSON and Markdown; exit 1 is the expected gate result:
36 observations, 4 unique tasks), offline `explain`, a targeted `--failed-from` rerun
(pad 0, repeats 1, 4 rows), and a check that the targeted run is refused as a CI baseline (exit 2).
The server rejects any request whose message sequence is not authored, and never logs bodies.

## Evidence

In `--out`: `report.json` and `report.md` (each step's command, exit status, expected
status, duration, and stdout/stderr paths; assertions; limitations), `artifacts/NN-step.{stdout,stderr}.txt`,
`baseline.json`, `candidate.json`, `targeted.json`, and the generated `suite/`.
Values of `API_KEY`/`OPENAI_API_KEY` are withheld from fixture steps and redacted from artifacts.

## Fixtures versus live

The fixture pass rates are constructed, so they verify CallProbe's plumbing and gates only.
They are **not** model performance.

Optionally, `--live-model NAME --live-endpoint URL` (both required) also runs the same
suite once (pad 0, repeats 1) against that OpenAI-compatible endpoint, with credentials
from the usual `API_KEY` environment variable. Wrong model answers are listed as findings
in the report (`live.json` holds the raw run); transport errors fail the self-test. Only the
chat endpoint is called; the mail operations are never executed.
