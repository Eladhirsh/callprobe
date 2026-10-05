# Bounded recovery for dropped source details

A parsed argument repair can fix a timestamp while dropping an event ID it
previously extracted. The default extractor now gives that lost-detail repair
one final attempt using focused instructions and the original isolated target
and grounded details. It never merges argument fields into claims automatically.
Ordinary repairs and deterministic matching are unchanged. The maximum remains
three model calls per message; unrecovered details still fail as incomplete.

## Repeated model comparison

The eight paired cases from the [prior evaluation](../2026-10-04-extraction-repeats/README.md)
were rerun three times on each of the same three installed model families.
These are known development fixtures used to investigate the failure, not a
held-out evaluation. All 72 planned attempts completed.

| Extractor | Before | Final recovery | Incomplete attempts after | Honest false alarms after |
|---|---:|---:|---:|---:|
| Qwen 2.5 7B | 18 of 24 | 24 of 24 | 0 | 0 of 12 |
| Mistral Nemo | 24 of 24 | 24 of 24 | 0 | 0 of 12 |
| Llama 3.1 8B | 15 of 24 | 15 of 24 | 0 | 6 of 12 |

Qwen's six scheduling attempts now retain both the explicit event ID and complete
timestamp. Its earlier repair fixed the offset but dropped the event ID, which
correctly failed source validation. The additional recovery restores both.
Llama still extracts an unsent email draft and a pending account adjustment as
completed actions. These existing semantic errors do not trigger lost-detail
recovery because no grounded detail has been dropped.

There were six improved attempts and no regressed attempts when paired by model,
case, and repeat. Claims and outcomes remained stable within each model's three
repeats, including the remaining Llama errors. Temperature-zero repeats reuse
cases; they do not provide independent accuracy samples. Exactness compares
verdict and tool counts, not every argument or claim detail. The repeated runner
returned exit code 1 because nine Llama mismatches remain.

## Why recovery is narrowly triggered

The first candidate used focused instructions for every initial argument repair.
It improved Qwen to 24 of 24 and Llama to 21 of 24 on the repeated fixtures, with
Mistral unchanged at 24 of 24. A broader live Mistral run caught a regression:
it counted an offered invitation as completed in honest case 80, finishing
101 of 102 exact. That approach was not merged. Aggregate evidence and source
hashes for the rejected candidate are retained in `summary.json`.

The final implementation preserves ordinary repair and uses the focused prompt
only when grounded details have been lost. This avoids changing the successful
repair path that previously handled case 80 correctly. Recovery remains a model
extraction step, so it can still fail or misinterpret statements; passing this
regression set does not establish general reliability.

The final broader Mistral run matched all 102 expected verdict multisets, with
zero extraction errors and zero alarms across 48 honest controls. The separate
detail-free check remains 22 of 23 because case 35 labels omit the order ID that
appears in the target; that annotation review remains open. One intentionally
incomplete recipient-evidence case still reports an unchecked detail. Verdict
matches do not mean every claim detail was verified.

## Verification and provenance

The [repeat report](repeat-report.md) includes coverage, extraction errors,
honest alarms, and unmentioned-action diagnostics. The separate
[bundled report](bundled-report.md) records the final broader live Mistral run.
[Source and case hashes](summary.json) pin both runs and the prior comparison.
The final repeat run began before commit `a88d211`; its runtime source hashes
match that commit. The full bundled run began after it. Frozen case files were
unchanged throughout both approaches. Raw responses remain local.
No business tools ran, and this is not a real MailOps integration test.

Both full test suites pass: 1,449 Callprobe tests and 584 Didyoureally tests,
including 16 new recovery and fail-closed controls. Ruff and formatting checks
pass, as do all 102 labeled matcher cases. One hundred archived agent episodes
and 94 saved extractor outputs replay unchanged. Both final wheels install in a
clean temporary environment; CLI initialization, bundled benchmark loading, and
timestamp controls pass. The installed extractor matches reviewed source byte
for byte.
The installed offline demo also creates its recorded runs, returns the expected
regression gate exit code 1, and explains a selected failure successfully.

Mixed-action false alarms, the staged future-plan error, and case 35 label review
remain open. Publication remains deferred.

## Reproduction

```bash
.venv/bin/python packages/didyoureally/scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 llama3.1:8b \
  --json-mode --repeats 3 \
  --cases packages/didyoureally/examples/repeat-validation \
  --out /tmp/new-source-recovery-repeats

.venv/bin/python packages/didyoureally/scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --json-mode --out /tmp/new-source-recovery-bundled
```
