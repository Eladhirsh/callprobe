# Literal tool-name model validation

The merged parser fix preserves available tools literally named `null` or
`none`. Fresh local model checks show that parser correctness alone does not
ensure that every model returns a valid claim envelope.

| Model | Verdict matches | Extraction errors | Cases agreeing across both repeats |
|---|---|---|---|
| Llama 3.2 3B | 2 of 8 | 6 | 4 of 4 |
| Phi-4 Mini | 8 of 8 | 0 | 4 of 4 |

Llama matched the `none` phantom control in both repeats. Its two honest controls
and the `null` phantom control each produced `invalid_claims` in both repeats.
Phi matched all four controls twice. Incomplete extractions remain failures.
The six errors are extraction outcomes, not failures of the scripted test suite.

## Method and evidence

We ran the four committed `examples/tool-identity-validation` controls through
`scripts/run_llm_bench.py` using default extraction, JSON mode, temperature zero,
and two repeats per model. All 16 planned attempts completed. The runner returned
exit code 1 because six attempts did not match their expected findings.

`summary.json` records the source revision, runtime and runner hashes, prompt
hash, per-fixture hashes, complete coverage, sanitized outcome identities,
error classifications, and the raw local records hash. The installed model
digests were captured after inference; their names and digests matched the
inventory inspected before the run. Inventory identity does not prove which
serving process produced a response. Raw replies remain in temporary local storage.

The controls pair honest execution with phantom completion for each literal
name. They were generated before this evaluation and were already used in
scripted regression checks. Four synthetic cases and two repeats cannot establish
general accuracy or long-run stability. Agreement here refers only to verdict
and error classification, not identical replies or argument accuracy. No real
business tools were executed, and no extraction prompt was tuned to these results.

The next useful comparison is to freeze matched controls using an ordinary tool
name before further inference. That can help distinguish general extraction
format failures from issues specific to alias-like names. Preserve the current
failures when comparing any proposed recovery change across broader controls.
