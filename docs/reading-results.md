# Reading results

How to read a run's failures, explain a saved run offline, and export summaries without calling a model.

## The failure digest

Every run ends with the specific failures, not just the rates. These are
worth reading, and they are frequently upstream bugs rather than model
weaknesses. If a server drops `additionalProperties`, mangles nested
objects, or returns arguments as a string where the schema says integer,
you will see it here first, including what the model actually said, with
any reasoning trace stripped, when it produced no call at all.

## Explaining a saved run (since 0.7.0)

`callprobe explain RESULTS.json --suite DIR` turns a results file back into
a debugging session, offline: no model calls, and it never modifies the
results file or the suite. It requires the same suite the run was scored
against; a missing or mismatched suite hash is a clear, non-zero-exit error
rather than a diagnosis built on a suite that has since changed.

Using the committed GitHub issues example and its recorded Qwen3 8B run:

If `github-issues-suite` already exists from the walkthrough, reuse it and
skip the first two commands.

```bash
callprobe init --from-openapi examples/github-issues/openapi.json --out github-issues-suite
cp examples/github-issues/tasks.yaml github-issues-suite/tasks.yaml
callprobe explain results/github-issues/qwen3-8b.json --suite github-issues-suite
```

Only failing `(task, pad, repeat)` cases are shown; a run with no failures
prints a short pass report instead. Failures are grouped into recurring
diagnostic categories, counted per case rather than per failure message
(`request_error`, `truncated`, `no_call`, `unexpected_call`,
`multiple_calls`, `wrong_tool`, `malformed_arguments`, `schema`,
`argument_value`), and then shown one case at a time: the task's user
prompt(s), what was expected, every call the model actually produced
(parsed arguments, or the raw text and parse error for one that didn't
parse), and the failure reasons already recorded at run time. Records from
before structured call evidence existed say so plainly instead of guessing
at what was called.

`--task TASK_ID` scopes this to one task across every pad and repeat it
ran with, and says so plainly if that task passed with no failures.
`--format json` prints the same report as deterministic, structured JSON
instead, for scripting:

```bash
callprobe explain results/github-issues/qwen3-8b.json --suite github-issues-suite \
  --task get-issue-details --format json
```

### Inspect a specific recorded observation

The development checkout supports `--pad` and `--repeat` on `explain`:

```bash
callprobe explain results.json --suite my-suite --task my-task --pad 0 --repeat 1
```

`--pad` selects the recorded distractor count; `--repeat` selects the zero-based
repeat index (`1` is the second repeat). Either filter works independently or
with `--task`. Text output labels the selection and JSON adds `observation_filter`.
Counts, task verdicts, shape hints, and repeat-variation summaries cover only
matching observations. A single selected repeat cannot establish variation.
If nothing matches, the report says there are no recorded results in that
selection; it does not infer a pass. These filters never rescore, rerun, or modify
saved results.

For one common, fixable shape of bug, a correctly chosen tool whose
arguments were flattened or under-wrapped relative to an OpenAPI-imported
`path`/`query`/`body` schema, `explain` proposes a corrected argument
shape, e.g. moving top-level `owner`/`repo`/`issue_number` under `path`, or
wrapping a flat `body` string as `{"body": {"body": "..."}}`. This is
always labeled advisory: nothing is executed or re-scored, and expectation
and value correctness are never guaranteed. The hint only appears when the
mapping from stray arguments to the tool's missing nested groups is
unambiguous and the resulting candidate fully validates against the tool's
complete schema; anything involving `$ref`, `oneOf`/`anyOf`/`allOf`,
`patternProperties`, or a schema-valued `additionalProperties` is refused
rather than guessed at. Relocation hints also require the root schema to
forbid extra properties. Supported schemas get error paths, messages, and
expected types; unsupported schemas retain the recorded failure reasons
with an explanation of the diagnostic limitation.

When an expected call is missing, `explain` can also flag bounded, parseable
JSON in ordinary assistant text that names a tool from the suite. This is an
advisory to check the model/provider's response format or tool-call parser;
it does not establish the cause. Text that resembles a call is never executed,
converted into a call, or re-scored. Malformed or ambiguous text is left as
recorded evidence rather than guessed at.

The JSON report also carries `argument_shape_summary`:
`affected_observations` (failing task/pad/repeat records that already have
a `shape_hint`), `unique_tasks`, and `by_kind` counts. Only existing hints
are counted; nothing is inferred from other schema failures, and `--task`
limits it to that task. The text report adds a short note when any hints
exist: inspect the proposed arguments, make sure your application adapter
and the tool contract agree, and rerun with the same suite. Nothing is
repaired or re-scored automatically.

Multi-repeat runs also gain a `repeat_variation` block grouped by
`(task_id, pad)`: `groups_examined` counts groups with at least two
distinct scored repeats, and `mixed_groups` lists each group where the
scored verdict changed, with `passing_repeat_ids`, `failing_repeat_ids`,
and `excluded_error_repeat_ids` for request errors that are kept out of
the counts. Pads are never mixed, `--task` scopes the summary, duplicate
`(task_id, pad, repeat)` rows raise a clear error rather than averaging
silently. Repeats vary deterministic tool order, so differences do not
isolate model randomness; a partial run does not establish stability. For example, the archived October 2026
granite3.3:8b core run scored 24/50 and 27/50 but moved 11 task verdicts
across its two repeats; phi4-mini stayed at 11/50 with two mixed groups.

Server provenance is detected when public metadata is available: Ollama via
`/api/version` and llama.cpp via its build and generation metadata at `/props`.
Unknown or protected metadata stays unset. Older llama.cpp results without
server identity may require a fresh run for `--resume`; their recorded scores
remain readable and are never changed.

## Read saved summaries (development checkout)

Inspect a recorded run without contacting its model endpoint or rebuilding its
suite:

```bash
callprobe report results.json --format text
callprobe report results.json --format json --out summary.json
```

These formats use recorded score fields and omit endpoint URLs, raw responses,
arguments, notes, and server error messages. They report scored observations,
distinct scored tasks, request errors, truncations, and
`scored/recorded/planned` coverage. Missing/duplicate/unexpected records are
marked; old runs without a recorded plan say coverage is unknown. Malformed
plans, including duplicate tasks/pads or invalid targeted selections, say
`invalid planned coverage` instead of appearing complete. Targeted runs remain
labeled as debug runs. JSON uses `null` for undefined cost per
success instead of nonstandard `Infinity`.

This is informational reporting, not a CI gate or a fresh evaluation. Export
returns `0` on success even when the recorded model failed. Use
`compare --fail-on-regression` for a matched gate. Existing output files require
`--force`, and the source results can never be overwritten, including through
symlinks or hard links. With no `--format`, `report` still exports JUnit XML.
