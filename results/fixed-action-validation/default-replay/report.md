# Offline recorded-response regression

These results reuse saved model replies. They are not fresh end-to-end accuracy.

| Model | Unchanged | Changed | Needs live recovery | Missing saved reply |
|---|---|---|---|---|
| mistral-nemo:latest | 78 | 1 | 0 | 1 |
| qwen2.5:7b | 78 | 1 | 0 | 1 |

Baseline records: `results/vague-claims-suite/development/records.jsonl`. Cases: `src/didyoureally/benchmark`.
No network calls are made. A new recovery request stops replay and requires a live evaluation.
