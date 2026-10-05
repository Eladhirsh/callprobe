# Chat recording validation

An imported recording could previously put a tool proposal on a user message,
then use its result to back an assistant completion claim. Invalid message
containers, unknown roles, and string content parts could also become empty
traces; a null message entry caused an uncaught exception. All five scripted
reproductions now return invalid input. The baseline is commit `0ce5f03`.

The adapter checks message roles, collection shapes, call ownership, function
metadata, and supported text parts before extraction. Empty assistant call turns
remain valid. Text and refusal parts preserve their exact strings, and successful
results cannot retroactively back claims from earlier messages.

## Verification

- All 1,449 Callprobe tests and 486 Didyoureally tests pass, including 68 new regression cases.
- Ruff and formatting checks pass.
- All 100 labeled matcher cases pass and reproduce byte for byte from the generator.
- All 100 archived agent episodes and 94 saved real extractor outputs replay unchanged.
- Both wheels build and install outside the checkout; the installed benchmark includes all 100 cases.
- Installed `dyr check`, `didyoureally check`, and `callprobe audit` reject malformed chat input with exit code 2 and `status: invalid_input`, and pass the valid text-part control.

The new frozen pair places the same completion text before or after the tool
result. Local Mistral Nemo produced the expected verdict and tool counts for
both cases in default and staged extraction modes: four fresh checks, zero
extraction errors. This small development test does not measure held-out accuracy
or full argument correctness. The earlier saved outputs were replayed offline.

## Evidence and migration

[Summary](summary.json) records source hashes, the frozen-suite hash, before-and-after
results, replay counts, model identity, run timestamps, coverage, and installed
CLI checks. Raw model responses remain local. Existing saved reports remain
unchanged. Benchmark generation used a temporary directory and copied only the
two new cases after checking that the existing 98 files were unchanged.

Normalize malformed collections and unsupported content parts before import.
Use assistant messages for tool proposals and nonempty string names and IDs.
Missing or null call fields still mean no proposal; an explicit empty message
array remains a valid empty trace. Unsupported multimodal parts and legacy
`function_call` recordings need conversion to the documented format.

No scoring rule, extraction prompt, version, or publication changed. The prior
staged extraction false alarm on a future JSON plan remains open.
