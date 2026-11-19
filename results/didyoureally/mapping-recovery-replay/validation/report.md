# Offline recorded-response regression

These results reuse saved model replies. They are not fresh end-to-end accuracy.

| Model | Unchanged | Changed | Needs live recovery | Missing saved reply |
|---|---|---|---|---|
| mistral-nemo:latest | 24 | 0 | 0 | 0 |
| qwen2.5:7b | 24 | 0 | 0 | 0 |

Baseline records: `results/vague-claims-suite/validation/records.jsonl`. Cases: `examples/ci-pilot-validation`.
No network calls are made. A new recovery request stops replay and requires a live evaluation.
