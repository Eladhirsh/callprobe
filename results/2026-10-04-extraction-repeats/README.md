# Repeated extraction on fresh mixed-action cases

Eight synthetic cases were committed in `997af6f` before inference, then each was
run three times on three installed local model families. The generator supplies
four honest controls paired with phantom, masked-failure, wrong-detail, and
unmentioned-action cases across email, files, support, and scheduling. Prompts,
scoring, and labels stayed fixed throughout this first evaluation.

This measures extraction from recordings. It does not exercise an autonomous
agent or verify a real MailOps integration. No business tools ran.

## Results

All 72 planned attempts were recorded. Six Qwen attempts ended with incomplete
extraction errors; none were counted as clean results. The runner returned exit
code 1 because some attempts did not match the expected verdicts.

| Local extractor | Exact attempts | Cases exact in all three repeats | Extraction errors | Honest false alarms |
|---|---:|---:|---:|---:|
| Mistral Nemo | 24 of 24 | 8 of 8 | 0 | 0 of 12 |
| Qwen 2.5 7B | 18 of 24 | 6 of 8 | 6 | 0 of 12 |
| Llama 3.1 8B | 15 of 24 | 5 of 8 | 0 | 6 of 12 |

Qwen consistently failed the two scheduling cases with `lost_source_detail`
after extraction repair. Three of these errors were on the honest control.
The separate unmentioned-action metric records three misses from the errored
failure case, so the ordinary claim precision and recall columns alone do not
capture this limitation.

Llama consistently extracted the explicitly unsent email draft as an additional
completed send in the honest email case. It also extracted the pending account
adjustment as a completed credit in both support cases. These added phantom
findings caused false alarms on six honest attempts. The phantom email case
still matched its expected verdict, illustrating why paired cases matter.

Among completed extractions, no parsed-claim multiset changed across repeats.
Outcome signatures, including error categories, were also unchanged. Cases with
no completed extraction provide no evidence of claim stability. Consistency
therefore includes repeatable mistakes. Temperature-zero
repeats are not independent new cases, and these eight development fixtures do
not establish held-out accuracy, production reliability, or a general model
ranking. Exactness compares verdict and tool counts, not full argument accuracy.

## Evidence and checks

[Full aggregate report](report.md) separates attempt counts, honest-case alarms,
unmentioned findings, unique-case coverage, and repeat diagnostics.
[Provenance](summary.json) includes source and prompt hashes, frozen case hashes,
run timestamps, model digests observed before and after inference, coverage,
per-case repeat metrics, and mismatched verdict counts. Model digests were
unchanged. Raw responses remain local and are not included here.

The feature passed 1,449 Callprobe tests and 568 Didyoureally tests, including
20 new regression tests for missing coverage, interruptions, duplicate records,
changed claims, stable failures, and target separation. Ruff and formatting
checks pass. All 102 bundled matcher cases and the eight new labeled controls
pass. The generator reproduces the frozen cases, and all 100 archived agent
episodes plus 94 saved extractor outputs replay unchanged.

## Reproduction

From the repository root, with these models already installed in Ollama:

```bash
.venv/bin/python packages/didyoureally/scripts/run_llm_bench.py \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --endpoint http://localhost:11434/v1 llama3.1:8b \
  --cases packages/didyoureally/examples/repeat-validation \
  --json-mode --repeats 3 --out /tmp/new-extraction-repeat-run
```

Use a new output directory. The next extraction work should investigate the
scheduling repair failures and mixed completed versus pending actions, preserving
this first evaluation before tuning. The prior staged future-plan false alarm
and benchmark case 35 annotation review also remain open. Publication remains
deferred.
