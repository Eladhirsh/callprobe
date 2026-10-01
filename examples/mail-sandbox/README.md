# Synthetic mail sandbox

Reusable fixtures and a scripted QA agent that test CallProbe with itself.

**This is a synthetic mail workflow, authored here. It is not MailOps and does not
reproduce MailOps compatibility or any figure (for example a 92% pass rate) reported
by anyone else.** We have neither that API nor its code. All addresses use
`example.invalid`, and no real mail API is ever called.

## Try the installed example

In the development build / next release (not PyPI 0.8.0):

```sh
callprobe init --example mail-sandbox --out my-mail-suite
callprobe validate --suite my-mail-suite
callprobe sweep --suite my-mail-suite --models qwen2.5:7b llama3.1:8b \
  --out /tmp/mail-model-plan --dry-run
callprobe sweep --suite my-mail-suite --models qwen2.5:7b llama3.1:8b \
  --out /tmp/mail-model-results
```

Use models already served by your endpoint. The first command writes the tools,
18 active tasks, and four distractors. The last command makes 36 model requests
with the default pad 0 and one repeat; it never executes mail operations.

The missing-ID prompt now explicitly forbids searching. Earlier saved smoke
results use the previous suite hash and must not be combined with this revision.

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

## Sweep several local models

`callprobe sweep` (development build / next release) runs one suite against several models that are already served at
an OpenAI-compatible endpoint, one at a time, through the public CLI only. It never
downloads or pulls a model. The self-test above leaves a ready suite in
`/tmp/callprobe-selftest/suite`.

```sh
# Plan first: dry runs for every model, prints total planned requests, sends nothing.
callprobe sweep --models model-a model-b \
  --suite /tmp/callprobe-selftest/suite --out /tmp/sweep --dry-run

# Then run for real (--out must not exist, so use a new directory).
callprobe sweep --models model-a model-b \
  --suite /tmp/callprobe-selftest/suite --out /tmp/sweep-real
```

Options: `--endpoint` (default `http://127.0.0.1:11434/v1`; embedded credentials, query,
and fragment are rejected), `--python`, `--pad` (default `0`), `--repeats` (default `1`),
`--max-tokens` (default `4096`), `--timeout` (seconds per step, positive, default `1800`).

- Every model is dry-run first; real runs follow, at temperature 0, concurrency 1,
  retries 0. `PYTHONPATH` and `PYTHONHOME` are removed. `API_KEY` is inherited from the
  environment and never placed on a command line.
- Files in `--out` are numbered (`01-run.stdout.txt`, `01-result.json`, ...), never named
  after the model. `manifest.json` records each step's command, status, duration, and
  output files. A failed or timed-out step does not stop the next model. Failed runs are
  left out of the leaderboard; any raw result file is retained.
- `leaderboard.md` uses only result files from successful runs of this invocation. Offline
  `explain` output is saved only when `--suite` is given. Exit status is 1 if any
  subprocess failed. Runs with request errors fail the sweep even when some
  observations succeeded; ordinary model mistakes remain scored findings.

Scores are reported as the CLI produced them, with no repair. A few tasks and repeats is a
small sample: the leaderboard does not show that the model order is robust.

## Development suite revision

After 0.9.0rc1, the two literal-text reply prompts explicitly say “Send a reply”
to match their expected send mode. Regenerating this example from the development
version changes its suite hash. Collect a new baseline; do not compare or resume
it as if it were the archived benchmark suite. Historical results retain their
original matching snapshots.
