# Contributing

Both engines are developed in this repository. The historical Didyoureally repository
is retained as a reference; open issues and pull requests here.

## Install one checkout

```sh
git clone https://github.com/Eladhirsh/callprobe.git
cd callprobe
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]" -e "packages/didyoureally[dev]"
```

Callprobe and Didyoureally keep separate package metadata and licenses. This installs
both development packages into one environment. It does not publish either package.

## Verify changes

```sh
.venv/bin/pytest -q tests
.venv/bin/pytest -q packages/didyoureally/tests
.venv/bin/ruff check packages/didyoureally
.venv/bin/ruff format --check packages/didyoureally
.venv/bin/dyr bench
```

Run the two test directories separately to keep their independent configurations.
The test suites use fake transports and local loopback servers, not live model APIs.
The benchmark command uses labeled claims to test the matcher. Real model runs must
be reported separately and require an explicitly configured endpoint.

For the shared agent workflow, see [the workflow guide](docs/agent-workflow.md).
The 28-case validation suite is regenerated with
`.venv/bin/python scripts/build_agent_validation.py`.

For packaging changes, build both wheels and install them in a separate environment.
Run the CLIs from outside the checkout so source imports cannot hide missing resources.
CI checks Python 3.10 through 3.13 and exercises installed wheels.
Keep changes focused, describe user-visible behavior and validation, and never include
private prompts or credentials in submitted evidence.

## History and releases

Didyoureally was imported with an unsquashed Git subtree merge under
`packages/didyoureally`, preserving its commit history. New development happens
here; no further synchronization with the old repository is required.

The current package versions remain unchanged. Root release automation still applies
to Callprobe. Didyoureally is not published and requires a separately authorized
release. The nested historical workflow files do not run as root GitHub Actions.

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
callprobe run --model your-model --pad 0,8 --repeats 3 \
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

### Testing several models

Use `callprobe sweep --models MODEL_A MODEL_B --out /tmp/model-plan --dry-run`
to inspect the planned requests, then a new output directory for the real run.
Add `--suite` for your application suite. The command is available in development
builds and does not pull model weights.

Start with a small, identical suite on every model before expanding coverage.
For imported tools, include nested arguments, missing identifiers, abstention,
conversation corrections, and literal text preservation. Keep the suite and
scoring version fixed within a comparison; save raw responses and endpoint/model
provenance alongside the generated report.

Use a staged experiment:

1. **Smoke test:** one repeat and no distractors. Check transport errors,
   truncation, tool selection, argument structure, and authoring mistakes.
2. **Coverage test:** the core suite plus application-specific suites. Expand
   tool counts with the same padding settings for every model.
3. **Repeatability:** multiple repeats at the intended production settings.
   Report uncertainty and per-task regressions, not just an overall percentage.

Small smoke tests identify failure patterns; they do not establish a general
model ranking. Keep reasoning/token settings explicit: a model that exhausts
its completion budget needs a separate budget-controlled experiment. Report
that limit rather than silently giving selected models more tokens.

If diagnostics propose a corrected argument shape, inspect the values too.
A wrapper can fix JSON structure while retaining a wrong email address or ID.
Change the adapter or contract deliberately, then collect a new run; never
rewrite the recorded response to make an existing evaluation pass.
