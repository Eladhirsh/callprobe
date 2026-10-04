# Live recording round-trip validation — 2026-10-04

All **108 observations across nine installed models** preserved their scored results through
Python recording export and installed-CLI replay. There were no request errors,
no truncations, and no argument parse failures. Five model/task pairs had mixed
pass/fail outcomes across the two repeats.

This is an integration smoke test on six fictional support tasks, not a general
model ranking or a MailOps integration test. Model responses were generated live;
they were not scripted fixtures.

## Observed results

| Model | Successful observations | Mixed task/pad groups | Exact export/replay match |
| --- | ---: | ---: | --- |
| llama3.2:3b | 5/12 | 1 | yes |
| hermes3:8b | 6/12 | 0 | yes |
| granite3.3:8b | 9/12 | 1 | yes |
| qwen2.5:7b | 4/12 | 0 | yes |
| llama3.1:8b | 5/12 | 1 | yes |
| phi4-mini:latest | 6/12 | 0 | yes |
| command-r7b:latest | 6/12 | 0 | yes |
| mistral-nemo:latest | 9/12 | 1 | yes |
| qwen3:8b | 7/12 | 1 | yes |

Each model completed all 12 planned observations. These are six distinct tasks
repeated twice, not 12 independent tasks. Repeats change deterministic tool order
and do not isolate sampling randomness.

## Method

- Clean installed wheel from commit `e5d35cbe38d93d30d997666ff94f6c0c6f1bbe48`.
- Package `0.9.0rc3.dev0`, Python 3.14.2, Ollama 0.34.2, one request at a time.
- Bundled `support` example with nested OpenAPI argument groups; suite hash `e8df4b7287151eba`.
- Pads `[0]`, two repeats, temperature 0, maximum 4096 output tokens, 60-second transport timeout, zero retries.
- Existing model installations only; no downloads, API purchases, or application tool execution.
- Capture each `ChatClient.complete` response and retain its task/pad/repeat coordinate.
- Score with `score_recordings`, export with `recordings_to_json`, then run installed `python -m callprobe replay`.
- Compare every TaskResult field, including calls, errors, text, token counts, latency, and verdicts.
- Compare summaries after replacing the original endpoint label with `recorded://local`.
- Check an exact failed observation using task/pad/repeat diagnostic filters for each model.
- Verify all nine model digests again after the run.

Full model digests, settings, and UTC timestamps are in [summary.json](summary.json).
Only aggregate validation data is committed here. Response recordings and
per-observation files remain local, so this note is not a public replay dataset.

## Limits

This covers one serving backend, one small suite, and zero distractors. It does
not establish performance on other prompts, tool contracts, providers, or real
application integrations. No live response in this sample exercised the new
duplicate-key/nonfinite argument failures; those cases are covered by synthetic
parser regression tests. The same candidate passed 1,232 tracked tests before
its parser change was merged in PR #29.
