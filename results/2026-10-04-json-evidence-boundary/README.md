# Strict JSON evidence boundaries

Four scripted reproductions previously returned a backed finding with no unchecked
details: duplicate outcome keys, duplicate argument keys, malformed arguments,
and nonfinite argument values. The same cases now return invalid input before
extraction or matching. Valid success and failure controls keep their original
verdicts. The baseline is commit `50fc4b2`.

The parser rejects duplicate keys at any object depth, including escaped key
aliases, and rejects NaN, infinity, and numeric overflow. OpenAI argument and
outcome strings use the same parser as trace files and extractor replies.
Already-decoded native and adapter inputs also reject nonfinite values.
Malformed arguments cannot become an empty object or an opaque `_raw` argument.
No matcher rule, prompt, or scoring label changed.

## Verification

- 1,449 Callprobe tests and 367 Didyoureally tests pass, including 46 new regression cases.
- Package Ruff and formatting checks pass.
- All 96 labeled matcher cases pass, including a new nested-outcome failure and honest pair.
- All 96 benchmark files reproduce byte for byte from the generator.
- All 100 saved agent episodes replay unchanged.
- All 94 saved real extractor outputs replay with identical claims, findings, and verdicts.
- Both packages build and install from wheels outside the checkout.
- Installed `dyr check`, `didyoureally check`, and `callprobe audit` reject the ambiguous-outcome reproduction with exit code 2 and `status: invalid_input`.
- The installed `dyr bench` includes all 96 cases.

The configured local Mistral Nemo extractor passed both new controls in default
and staged modes: four fresh extractions, no extraction errors. This is a small
compatibility check, not a model accuracy estimate. The earlier full live run
was replayed offline, not repeated against the model.

An initial model-run preflight found 14 untracked duplicate benchmark files and
stopped before making requests. Those files were byte-identical to canonical
cases and were preserved outside the checkout. The live check then used a frozen
copy of generator output, so the duplicate files did not inflate coverage.

## Evidence and limits

[Summary](summary.json) preserves source hashes, model identity, timestamps,
per-case comparisons, raw-evidence hashes, and coverage. Raw model responses
remain local. The frozen matrix reports remain unchanged. No application tools
ran and no release was published.

Duplicate keys already discarded by an upstream JSON parser cannot be recovered
from a dictionary. Keep the original argument and result JSON strings, or use
the CLI file loader. Plain-text success markers and valid finite JSON remain
supported. The extraction limitations recorded in the completion-scope check
are unchanged by this input-validation fix.
