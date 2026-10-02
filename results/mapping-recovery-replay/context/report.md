# Offline recorded-response regression

These results reuse saved model replies. They are not fresh end-to-end accuracy.

| Model | Unchanged | Changed | Needs live recovery | Missing saved reply |
|---|---|---|---|---|
| mistral-nemo:latest | 16 | 0 | 0 | 0 |
| qwen2.5:7b | 16 | 0 | 0 | 0 |

Baseline records: `results/all-argument-grounding-diagnostic/records.jsonl`. Cases: `examples/context-validation`.
No network calls are made. A new recovery request stops replay and requires a live evaluation.
