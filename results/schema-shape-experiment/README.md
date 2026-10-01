# Flat versus nested tool contracts: Qwen 2.5 7B

Tested the PyPI-installed Callprobe 0.9.0rc1 against local Ollama. Same 18 fictional mail prompts, tool names/descriptions, field constraints, temperature 0, pad 0, concurrency 1, max tokens 4096, retries 0. Three runs per variant, ordered nested/flat, flat/nested, nested/flat. No email operations executed.

| Contract | Success | Selection | Schema | Arguments |
| --- | --- | --- | --- | --- |
| nested | 12/54 (22.2%) | 48/54 (88.9%) | 12/54 (22.2%) | 12/54 (22.2%) |
| flat | 39/54 (72.2%) | 48/54 (88.9%) | 48/54 (88.9%) | 39/54 (72.2%) |

All 108 requests completed with zero request errors and zero truncations. Every nested run scored 4/18; every flat run scored 13/18. Nine tasks improved in all three paired rounds, with no success regressions. Selection accuracy stayed unchanged.

## Interpretation

For this model and suite, changing argument nesting produced a 50 percentage-point success increase. The field constraints and prompts were held fixed; the shape presented to the model and corresponding expectation paths changed. This supports schema shape as a major contributor to the earlier failures. It does not establish a universal benefit across models or integrations. Temperature-zero repeats are consistency checks, not independent statistical samples.

## Remaining failures

- Sender search includes a trailing period in the email filter.
- Unsupported delete and forward requests still trigger a tool call.
- Literal reply text includes unwanted brackets in one case; two reply cases choose draft instead of the expected send mode. These expectations should also be checked against a real application’s reply/send policy.

## Contract-equivalence checks

Flat tools retain the same scalar schemas, required fields, enums, patterns, limits, and descriptions. Colliding field names are rejected by the builder. Nested exact-object expectations become flat exact-value checks plus explicit absence checks for omitted optional fields; flattening does not make these optional fields free to appear. The check script confirms 68 paired valid, missing, wrong-type, and unexpected-optional-field outcomes agree. Prompts and abstention expectations match.

The suites have intentionally different hashes. This is a contract experiment, not a matched CI regression comparison. No saved responses were repaired or rescored.

## Reproduce and inspect

Install `callprobe==0.9.0rc1` in a Python environment with Qwen 2.5 7B already served by Ollama. The scripts use that environment’s interpreter. Run from a fresh copy of this directory without numbered result files:

```bash
python build_suites.py
python check_equivalence.py
python run_experiment.py
python analyze.py
```

Offline inspection of existing evidence:

```bash
callprobe explain 02-flat.json --suite flat
callprobe explain 01-nested.json --suite nested
```

`manifest.json` records model digest, quantization, installed package version, commands and order. Each raw result records suite hash, scoring version, endpoint/server version, responses and verdicts. `summary.json` preserves per-task outcomes.

## Per-task successes across three runs

| Task | Nested | Flat |
| --- | --- | --- |
| search-by-sender | 0/3 | 0/3 |
| search-by-subject | 0/3 | 3/3 |
| search-archive-folder | 0/3 | 3/3 |
| search-with-limit | 0/3 | 3/3 |
| get-by-id | 0/3 | 3/3 |
| get-id-with-punctuation | 0/3 | 3/3 |
| reply-send | 0/3 | 3/3 |
| reply-draft-only | 0/3 | 3/3 |
| no-send-chat-only | 3/3 | 3/3 |
| get-missing-id | 3/3 | 3/3 |
| reply-missing-id | 3/3 | 3/3 |
| search-missing-criteria | 3/3 | 3/3 |
| unsupported-delete | 0/3 | 0/3 |
| unsupported-forward | 0/3 | 0/3 |
| reply-body-quotes | 0/3 | 0/3 |
| reply-body-symbols | 0/3 | 0/3 |
| correction-search-sender | 0/3 | 3/3 |
| correction-reply-target | 0/3 | 3/3 |
