# Contributing

## Development setup

Use Python 3.10 or newer. From a checkout, create an environment and install
the project with its test dependencies:

```bash
uv venv
uv pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/callprobe validate
```

The automated suite uses local fixtures and does not require API keys,
Ollama, or paid model calls. Add a regression test for a behavior change,
then run the relevant tests and the full suite before opening a PR.

For packaging changes, also build a wheel with `uv build` and install it in
a separate environment. Run the CLI from outside the checkout: importing
from `src/` can hide missing package resources. CI checks Python 3.10–3.13
and validates the examples from an installed wheel.

Keep changes focused. Describe the user-visible behavior and how you
verified it in the PR. Do not include API keys or private model prompts in
test fixtures or submitted results.

## Writing a task

A task lives in `tasks.yaml` and asserts what a model should do for one
conversation. Pick the category that matches what would actually break if
a model got it wrong:

- `select` picked the right tool, or correctly called nothing, when the
  choice between tools is the interesting part
- `abstain` no tool applies and the correct behavior is to say so or ask
  a question, not to guess
- `args` the right tool was the obvious choice, but the argument values
  are where a model can still get it wrong (arithmetic, units, enums,
  omitted optional fields, normalization)
- `depth` the conversation has multiple turns and the answer depends on
  something said earlier
- `sequence` several actions are implied, and the task checks which one
  is the correct first call, not the whole chain

Every task needs `id`, `category`, `bundle`, `messages`, and `expect`.
`expect.type` is `call` or `no_call`. For a call, `args` is exact match on
whichever keys you list (extra keys are judged by the tool's schema
instead), and `arg_checks` covers everything else you want to assert
about a value, at a dotted path like `address.postal_code` or
`attendees.0`.

`call` expects exactly one tool call; extra calls fail even when one is
correct. A truncated response cannot pass either expectation. Full call
evidence is retained in result JSON. Changes to these scoring semantics
must increment `SCORING_VERSION` in `scoring.py` and add regression tests,
so old and new observations are not silently combined.

| op | checks |
| --- | --- |
| `eq` / `neq` | equals / does not equal |
| `in` | value is one of a list |
| `contains` | value contains a substring or element |
| `gte` / `lte` | numeric comparison |
| `matches` | value matches a regex |
| `exists` / `absent` | the key is present / is not present |

Add `exclude_distractors: [tool_name]` when padding could hand the model
a distractor tool that would make your expected answer wrong, most often
on `abstain` tasks. See `abstain-policy-question` in
`src/callprobe/suites/core/tasks.yaml` for the pattern: the distractor
`search_knowledge_base` would genuinely answer the question, so it's
excluded from padding for that task specifically.

Once you've written a task, run:

```bash
callprobe validate
```

It checks that every key you asserted in `args` or `arg_checks` actually
exists in the tool's schema, and that every value you asserted is legal
for that schema. It runs with no model and exits nonzero on any problem.
A typo here fails every model silently, so this is not optional.

## Submitting a run

Runs against models not yet in the leaderboard are welcome. Create a fresh
baseline and candidate from the same suite, using identical pad counts and
repeats. The archived suite-v1 results are historical evidence, not a
baseline for the current suite and scorer.

For a new full-suite experiment, one possible configuration is:

```bash
callprobe run --model your-model --pad 0,8,16,24 --repeats 3 \
  --max-tokens 4096 --out results/your-model.json
```

Include the results JSON file in your PR. Don't hand-edit it or the
leaderboard, both are generated:

```bash
callprobe leaderboard results/your-model.json results/other-model.json \
  > LEADERBOARD.md
```

Say what endpoint and quantization you ran against in the PR description
if `--quant` doesn't already capture it.

Before submitting a comparison, run:

```bash
callprobe compare baseline.json candidate.json --fail-on-regression
```

A failed gate can be a useful result: include the regressions and the
conditions under which they occurred. Request errors and missing cases
must remain visible. Do not rewrite saved calls or remove failing cases to
improve a score. Targeted debug runs are useful for investigation but are
not eligible for a full-suite gate or leaderboard.

When submitting a new OpenAPI example, include its source revision and
license, authored expectations, and a small deterministic test that proves
the expected arguments satisfy the imported schema. Quote YAML messages
containing ` #` so issue numbers and similar text are not parsed as comments.
