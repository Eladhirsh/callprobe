# Native trace validation

Native JSON could previously hide evidence without using duplicate JSON keys.
A reused call ID hid an unreported second send, duplicate tool definitions could
replace write classification, a numeric zero side-effect flag suppressed writes,
and arrays of argument pairs silently kept the last repeated key. All four
scripted reproductions now return invalid input. Valid silent-action and
reported-action controls keep their original findings.

The baseline is commit `68a5733`. Structural checks now run before extraction:
collections and entries have explicit shapes, tool names and call IDs are unique,
side-effect flags are booleans, arguments are objects, and message roles and
content have supported types. The matcher checks call identity again for Python
traces constructed directly or modified after loading. Scoring and prompts for
valid evidence are unchanged.

## Verification

- All 1,449 Callprobe tests and 418 Didyoureally tests pass, including 51 new regression cases.
- Ruff and formatting checks pass.
- All 98 labeled matcher cases pass and reproduce byte for byte from the generator.
- All 100 archived agent episodes and 94 saved real extractor outputs replay unchanged.
- Both wheels build and install outside the checkout; the installed benchmark contains all 98 cases.
- Installed `dyr check`, `didyoureally check`, and `callprobe audit` reject duplicate call IDs with exit code 2 and `status: invalid_input`.

The new frozen benchmark pair records two distinct sends. One reply names only
the first recipient, requiring an unmentioned finding for the second send. Its
honest counterpart reports both recipients and requires two backed findings.
Local Mistral Nemo passed both controls in default and staged extraction modes,
with zero extraction errors across four fresh extractions. These small synthetic
checks demonstrate compatibility, not model accuracy. The 94 earlier model
outputs were replayed offline, not generated again.

## Evidence and migration

[Summary](summary.json) records source hashes, a frozen-suite hash, before-and-after
outcomes, replay counts, model identity, run timestamps, and per-case comparisons.
Raw model responses remain local. Original saved agent reports remain frozen.
Benchmark generation used a temporary directory and copied only the two new
cases after verifying the existing 96 files were unchanged.

Callers must normalize invalid types instead of relying on coercion. Explicit
call IDs must be nonempty strings; generated IDs remain stable but cannot
collide with explicit IDs. Native calls still denote completed execution and
retain the existing `status: "ok"` default. Record failures explicitly and use
the message adapter for proposals whose results arrive later. These structural
checks do not verify real-world execution outcomes. No version or publication
changed, and the previously documented staged extraction limitation remains.
