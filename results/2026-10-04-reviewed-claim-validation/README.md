# Reviewed claim validation

Supplied claims could previously point at a user message or a nonexistent future
message, allowing a later result to back an earlier assistant claim. Boolean
indices and blank claim text were also accepted. Empty claim objects and strings
silently became empty claim lists. Six scripted reproductions now return invalid
input. The baseline is commit `02404f2`.

Reviewed claim collections must be arrays. Their text, tool, arguments, group ID,
and optional message index have explicit types. A supplied index must identify a
nonempty assistant message in the normalized trace. Validation runs for file
loading, `GivenClaims`, and the matcher, including directly constructed or
modified Python claims.

## Verification

- All 1,449 Callprobe tests and 540 Didyoureally tests pass, including 54 new regression cases.
- Ruff and formatting checks pass.
- All 102 labeled matcher cases pass and reproduce byte for byte from the generator.
- All 100 archived agent episodes and 94 saved real extractor outputs replay unchanged.
- Both wheels build and install outside the checkout. The installed benchmark contains all 102 cases, and mock agent setup succeeds.
- Fifteen installed CLI checks across `dyr check`, `didyoureally check`, and `callprobe audit` preserve invalid-input, finding, honest, and legacy outcomes.

The new frozen pair places an assistant completion before or after a send, then
ends with a user acknowledgment. Local Mistral Nemo produced the expected verdict
and tool counts in default and staged extraction modes: four fresh checks and
zero extraction errors. This small development test is compatibility evidence,
not held-out accuracy or a measurement of full extracted-argument correctness.
Saved outputs were replayed offline, not generated again.

## Evidence and migration

[Summary](summary.json) records source hashes, the frozen-suite hash, before-and-after
results, replay counts, model identity, run timestamps, coverage, and installed
CLI outcomes. Raw replies remain local; existing saved reports remain unchanged.
The benchmark generator wrote a temporary directory. Only the two new cases were
copied after verifying all 100 existing files were unchanged.

Use explicit arrays for supplied claims and normalized assistant event indices
for chronology. For compatibility, omitted or null indices keep session-wide
manual matching. That legacy form does not establish that a call preceded the
message making the claim. Explicit empty claim arrays remain valid, and unknown
tool names remain phantom findings. Reviewed text and arguments remain trusted
annotations; these checks do not verify semantic fidelity to the original reply.

Invalid claims return exit code 2 even when finding gates are disabled, and CLI
batches continue with later files. No extraction prompt, valid-evidence scoring
rule, version, or publication changed. The staged future-plan false alarm remains
open.
