# Request-bound replay validation

A fresh local Mistral run completed four existing frozen synthetic cases: 73, 74,
80, and 94. All four matched their expected verdict and tool counts without
extraction errors. The small selection covers contextual completion recovery,
a group with an offer, and JSON future-plan wording. It is a recording and
replay check, not a broad model-accuracy estimate.

All four saved records replayed unchanged with verified request hashes and exit
code 0, including the recovery requests in cases 73 and 74. A separate offline
negative control changed saved JSON mode without changing request hashes. All
four then stopped with `request_mismatch`, returning exit code 1.

The model was the installed `mistral-nemo:latest` on the configured local Ollama
endpoint, with temperature zero and JSON mode enabled. `summary.json` records
the model digest observed after the run, runtime and runner hashes, fixture
hashes, request counts, errors, and coverage. The run preceded the implementation
commit; source hashes identify the evaluated code. Raw replies remain local.

Hashes identify request bodies, not server identity or model weights. Older
recordings lack this evidence and retain their explicit unverified replay mode.
The offline replay and mismatch control make no model requests. No real business
tools were executed.
