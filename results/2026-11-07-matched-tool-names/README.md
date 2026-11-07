# Matched tool-name controls

Ordinary tool names did not eliminate Llama's extraction failures in this
small matched comparison. The error classifications differ by name, so the
results do not isolate one common cause or prove names have no effect.

| Model | `archive_note` matches | `none` matches | `null` matches | Extraction errors |
|---|---|---|---|---|
| Llama 3.2 3B | 0 of 4 | 2 of 4 | 0 of 4 | 10 of 12 |
| Phi-4 Mini | 4 of 4 | 4 of 4 | 4 of 4 | 0 of 12 |

All four Llama ordinary-name attempts ended in `source_mismatch`. The alias-like
names produced six `invalid_claims` errors; the `none` phantom case matched in
both repeats. Phi matched all 12 attempts. Each model's verdict or error
classification agreed across both repeats of all six cases. This does not mean
identical responses or establish long-run stability.

## Method

The existing generator now creates a third honest and phantom pair using
`archive_note`. A scripted invariant verifies that the three names have identical
messages, parameters, tool descriptions, outcomes, and event order after
normalizing tool identity and removing the derived trace ID. The two new JSON
fixtures were generated and validated before inference. The four original
fixtures remain byte-identical to the prior experiment.

We evaluated the whole six-case suite again using the same two installed models,
default extraction, JSON mode, temperature zero, and two repeats. All 24 planned
attempts completed. The runner returned exit code 1 because 10 extractions failed.
This run is separate from the earlier 16-attempt literal-name evaluation.

The first Llama response on each inspected first-repeat case lacked a `claims`
wrapper. Existing recovery returned a wrapper. That structural observation does
not explain every remaining failure: ordinary-name attempts failed source
grounding, while the alias-like cases often failed claim validation. No runtime
prompt, recovery behavior, or deterministic matcher rule was changed for this run.
Incomplete extraction remains a failure.

## Evidence and limits

`summary.json` includes actual runtime and generator hashes, individual fixture
hashes, runner and prompt hashes, complete coverage, sanitized outcomes, error
classifications, a raw-record hash, and model digests captured after inference.
The metadata revision precedes the generator changes; the separate generator
hash identifies the frozen source used to create the six fixtures. Raw model
replies remain local in temporary storage.

These are six reused synthetic controls and two model configurations, not a
production accuracy benchmark. Inference order was fixed, and two repeats are
not enough to measure model stability. Verdict agreement does not establish
argument accuracy. A broader frozen suite must test any proposed recovery change,
including honest false alarms, before adoption. This evidence supports retaining
the strict failure behavior while investigating output compatibility.
