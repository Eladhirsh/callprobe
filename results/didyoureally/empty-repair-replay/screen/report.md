# Offline recorded-response regression

These results reuse saved model replies. They are not fresh end-to-end accuracy.

| Model | Unchanged | Changed | Needs live recovery | Missing saved reply |
|---|---|---|---|---|
| mistral-nemo:latest | 24 | 0 | 0 | 0 |
| qwen2.5:7b | 24 | 0 | 0 | 0 |
| llama3.2:3b | 24 | 0 | 0 | 0 |
| hermes3:8b | 24 | 0 | 0 | 0 |
| llama3.1:8b | 23 | 0 | 1 | 0 |
| phi4-mini:latest | 24 | 0 | 0 | 0 |
| granite3.3:8b | 24 | 0 | 0 | 0 |

Baseline records: `results/vague-claims-suite/screen/records.jsonl`. Cases: `examples/reliability-challenge`.
No network calls are made. A new recovery request stops replay and requires a live evaluation.
