# v0.5.0 real-model validation

Two independent invocations of the same 150-request benchmark produced
identical pass/fail outcomes. Both the strict regression gate and the
example tolerance policy passed. The stricter call-count rule rejected
six responses per run that the previous rule would have passed.

## Setup

- Date: 2026-09-21 UTC.
- Callprobe: 0.5.0; scoring version 2.
- Suite: core v2, hash `e597c986302b5596`, 50 tasks.
- Model: `qwen2.5:7b`, Q4_K_M, installed model digest prefix `845dbda0ea48`.
- Server: Ollama 0.34.2 at `http://localhost:11434/v1`.
- Hardware: Apple M4 Pro, 24 GiB memory; Ollama reported 100% GPU.
- Runtime context: 4,096 tokens as reported by `ollama ps`.
- Requests: 3 repeats, temperature 0, `--pad 0`, `--max-tokens 4096`,
  sequential execution. Each repeat uses a different deterministic tool
  order; corresponding repeats in both runs use the same order.

The candidate was a fresh run, not a resumed baseline. This checks the
stability of an unchanged configuration, not a model upgrade. This is a
no-padding validation, not a replacement for the historical multi-padding
leaderboard. The historical sweeps also used an older scoring rubric.

## Results

| Metric | Baseline | Candidate |
| --- | --- | --- |
| Scored requests | 150 | 150 |
| Successful requests | 118 | 118 |
| Strict / type-lenient success | 78.7% / 78.7% | 78.7% / 78.7% |
| Success 95% task-bootstrap interval | 68.7–88.0% | 68.7–88.0% |
| Selection | 94.7% | 94.7% |
| Schema | 93.3% | 93.3% |
| Argument values | 83.3% | 83.3% |
| Abstention | 87.9% (29/33) | 87.9% (29/33) |
| Argument tasks | 66.7% (24/36) | 66.7% (24/36) |
| Conversation depth | 81.8% (27/33) | 81.8% (27/33) |
| Selection tasks | 94.4% (17/18) | 94.4% (17/18) |
| Sequence tasks | 70.0% (21/30) | 70.0% (21/30) |
| Request errors / truncations | 0 / 0 | 0 / 0 |
| Seconds per success | 2.60 | 2.29 |

There were **zero passing-to-failing cases and zero failing-to-passing
cases** across the 150 matched `(task, pad, repeat)` keys. This does not
mean every response byte was identical: call IDs, token totals, and timing
can differ without changing a verdict.

Within each run the three tool-order repeats scored 76%, 82%, and 78%.
That six-percentage-point spread is tool-order sensitivity, not an observed
between-run regression. Comparing identical coverage and repeat keys is
important.

## Failures inspected

The new call-count rule caught two task IDs in all three repeats:

- `sequence-address-before-status`: returned `update_shipping_address`
  and `get_order_status` together instead of only the expected first call.
- `sequence-cancel-before-rebook`: returned two or three calls together,
  including `cancel_meeting` and subsequent scheduling actions.

Each of these six responses per run had correct selection, schema, and
arguments for the expected call. The old rubric would therefore have
scored 124/150 (82.7%) on these same responses; scoring version 2 correctly
scores 118/150 (78.7%). These are two distinct tasks repeated three times,
not six independent scenarios. This is an inference from the old success
condition applied to the captured calls, not a comparison with an older
live benchmark.

Other inspected failures included a 4,250-cent refund instead of 4,225,
an incorrect relative date, booking before checking availability, and a
`null` optional refund amount where the schema requires an integer if the
field is present. None of the observed failures were rescued by type
coercion. Truncation handling remains covered by automated tests because
these two live runs produced no truncated responses.

## CI policy decision

Keep `--fail-on-regression` as the default for this fixed configuration:
it passed the unchanged rerun without suppressing any case regressions.
One pair does not establish a long-term false-alarm rate or generalize to
other servers, models, hardware, temperatures, or tool sets.

[`examples/ci-policy.yaml`](../../examples/ci-policy.yaml) illustrates a
less strict option: at most a five-percentage-point overall drop, at least
70% overall success, at least 80% abstention, zero request errors, and a
required pass on `abstain-missing-identifier`. Its thresholds were chosen
before the second run and both runs satisfy them. No observed noise in
this pair required that tolerance. Calibrate a policy with repeated runs
of your own suite; do not treat these thresholds as production guarantees.

The live incomplete candidate was rejected with exit code 2 for missing
coverage. Resuming the completed baseline preserved all 150 result records
and its original start time exactly. Offline replay of all 300 saved call
records reproduced their scoring flags and failure explanations.

## Reproduce

With the model installed and Ollama running, execute from the repository
root using Callprobe 0.5.0. Use new output paths to preserve this evidence:

```bash
callprobe run --model qwen2.5:7b --endpoint http://localhost:11434/v1 \
  --pad 0 --repeats 3 --temperature 0 --max-tokens 4096 --quant Q4_K_M \
  --out results/local-baseline.json
callprobe run --model qwen2.5:7b --endpoint http://localhost:11434/v1 \
  --pad 0 --repeats 3 --temperature 0 --max-tokens 4096 --quant Q4_K_M \
  --out results/local-candidate.json
callprobe compare results/local-baseline.json results/local-candidate.json \
  --fail-on-regression
callprobe compare results/local-baseline.json results/local-candidate.json \
  --policy examples/ci-policy.yaml
```

Artifacts:

- [Baseline call records](qwen2.5-7b-baseline.json)
- [Candidate call records](qwen2.5-7b-candidate.json)
- [Metrics, gate outcomes, and replay audit](validation-summary.json)

Release checks also passed all 108 automated tests on Python 3.14 and on
Python 3.12 with Pydantic 2.6.0, HTTPX 0.27.0, jsonschema 4.21.0,
PyYAML 6.0.1, and pytest 8.0.0. The installed 0.5.0 wheel validated all
50 bundled tasks from outside the source checkout.
