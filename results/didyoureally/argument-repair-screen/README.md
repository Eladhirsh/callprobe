# Argument repair diagnostics

Commit `42d74da` gives the model field-specific feedback and uses target-only repair for null placeholders and unresolved references. Rejected fields are not silently removed; the returned extraction must pass validation. Valid literal arguments and distinct actions must be retained.

These are selected known failure cases and controls, not fresh validation. All runs completed on configured local models.

| Mode | Model | Exact | Incomplete checks | Honest controls with any alarm |
|---|---|---|---|---|
| default | mistral-nemo:latest | 7/7 | 0 | 0/3 |
| default | qwen2.5:7b | 4/7 | 3 | 0/3 |
| staged | mistral-nemo:latest | 8/8 | 0 | 0/3 |
| staged | qwen2.5:7b | 0/8 | 8 | 0/3 |

Mistral recovered the selected pronoun and placeholder cases. Qwen still repeatedly returned invalid fields, including null amounts and unresolved recipients. Its incomplete checks remain failures and do not establish that the agent was truthful. These runs do not support claiming a general repair across models.

The default screen includes offers as honest controls; the staged screen focuses on grouped actions and pronoun recipients. Their case sets differ, so the two mode totals must not be compared as a paired accuracy test.

[Default evidence](default/report.md), [staged evidence](staged/report.md). Raw replies, findings, source hashes, and completed record counts are retained. All 208 offline tests, Ruff checks, and 84 labeled cases passed before this experiment.
