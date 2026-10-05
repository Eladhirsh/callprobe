# Recorded-response replay validation

The hardened replay command checked 102 saved Mistral default-mode records from
the earlier [source-repair evaluation](../2026-10-04-source-repair/README.md).
It reported 100 unchanged records and two requiring a live recovery step, with
exit code 1. No new inference or business tools were executed.

Cases 73 and 74 require the focused recovery prompt. Replay stops before using
an unmatched response for that request, even though the earlier live evaluation
completed those cases. The result is deliberately incomplete; this is not a new
102-case model score or a claim that the two cases failed live extraction.

`summary.json` records source and input hashes, observed outcome counts, and the
two case identities. Raw replies and replay records remain local. Separate
scripted tests verify empty and invalid input rejection, staged-mode rejection,
duplicate identities, preserved repeats, and protection of existing output.
