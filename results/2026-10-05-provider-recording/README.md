# Provider recording diagnostics

A refusal without a `content` field previously became a generic provider error
in the model benchmark recorder, with zero saved responses. Direct extraction
correctly classified the same reply as a refusal. The recorder now observes
available metadata without validating the envelope before the extractor does.

Received replies without content save `null` plus the request hash and available
model, usage, and finish metadata. The original response goes unchanged to the
extractor. Refusals, truncation, and malformed envelopes remain extraction errors;
no partial claims or passing verdict are produced. A connection failure before
receiving any response still leaves the received-response list empty. Refusal
and provider-error messages are not copied into diagnostics.

Twenty-two scripted regressions exercise both extraction modes, malformed reply
shapes, missing-content refusals, truncation, refusal during the staged detail
step, connection failures, successful capture metadata, and safe diagnostics.
Four existing default-mode records and nine complete staged records replayed
unchanged with verified request hashes. The staged subset remains explicitly
incomplete coverage of its original run, which had one extraction error.

Required checks pass: 1,465 Callprobe tests, 802 tracked Didyoureally tests,
package Ruff checks, and 102 labeled matcher cases. Another 48 preserved local
duplicate tests pass and are excluded from tracked totals. `summary.json` saves
runner and input hashes. Raw replies remain local. No fresh model inference,
model-accuracy claim, prompt change, or publication is part of this fix.
