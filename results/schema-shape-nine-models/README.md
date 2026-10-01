# Nine-model schema-shape experiment

Published Callprobe 0.9.0rc1; fictional email tools; no mail API operations executed. Eighteen identical prompts across flat and nested contracts, with 0, 2, and 4 distractors. Nine locally installed Ollama models. Each task/shape/pad/model condition has one observation; 972 were planned.

Each model uses temperature 0, max_tokens 4096, concurrency 1 and retries 0. Model order is fixed and variant order alternates by model. No generated responses are repaired or rescored. Models differ in size, quantization, training, templates and tool parsers; this is a local compatibility experiment, not a universal ranking.

All **972 planned observations were recorded**: 967 scored responses, 5 request errors, and 3 truncated responses (included as scored failures).

Flattening improved paired success for five models, reduced it for three, and left one unchanged. Across scored pairs, 85 observations improved and 27 regressed. Qwen 3 had the highest flat score here (48/54), but still regressed two conditions. This supports an explicit contract-comparison option, not automatic flattening as a universal default.

The experiment completed without a harness crash. Model failures, request timeouts and truncated responses remain distinct in the saved evidence. Model digests were checked again after the run and were unchanged.

## Overall results

| Model | Nested successes/scored | Flat successes/scored | Paired change (pp) | Improved cases | Regressed cases | Errors | Truncated |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen2.5:7b | 18/54 | 39/54 | +38.9 | 21 | 0 | 0 | 0 |
| llama3.2:3b | 20/54 | 17/54 | -5.6 | 3 | 6 | 0 | 0 |
| hermes3:8b | 13/54 | 38/54 | +46.3 | 27 | 2 | 0 | 0 |
| phi4-mini:latest | 17/51 | 20/54 | +3.9 | 3 | 1 | 3 | 2 |
| granite3.3:8b | 29/54 | 27/54 | -3.7 | 3 | 5 | 0 | 0 |
| command-r7b:latest | 18/54 | 18/54 | +0.0 | 0 | 0 | 0 | 0 |
| llama3.1:8b | 18/54 | 17/54 | -1.9 | 5 | 6 | 0 | 1 |
| mistral-nemo:latest | 29/54 | 32/54 | +5.6 | 8 | 5 | 0 | 0 |
| qwen3:8b | 34/52 | 48/54 | +25.0 | 15 | 2 | 2 | 0 |

Request errors are excluded from scored denominators and disclosed above; truncations remain scored failures. A complete model/variant has 54 observations. Paired changes use only task/pad observations successfully scored in both contracts; models with request errors have fewer such pairs. Different suite hashes are intentional: these are descriptive paired contract comparisons, not same-suite CI regression gates.

## By distractor count

| Model | Pad | Nested | Flat |
| --- | --- | --- | --- |
| qwen2.5:7b | 0 | 4/18 | 13/18 |
| qwen2.5:7b | 2 | 7/18 | 14/18 |
| qwen2.5:7b | 4 | 7/18 | 12/18 |
| llama3.2:3b | 0 | 5/18 | 5/18 |
| llama3.2:3b | 2 | 7/18 | 7/18 |
| llama3.2:3b | 4 | 8/18 | 5/18 |
| hermes3:8b | 0 | 5/18 | 14/18 |
| hermes3:8b | 2 | 4/18 | 14/18 |
| hermes3:8b | 4 | 4/18 | 10/18 |
| phi4-mini:latest | 0 | 6/18 | 8/18 |
| phi4-mini:latest | 2 | 5/17 | 6/18 |
| phi4-mini:latest | 4 | 6/16 | 6/18 |
| granite3.3:8b | 0 | 9/18 | 9/18 |
| granite3.3:8b | 2 | 9/18 | 10/18 |
| granite3.3:8b | 4 | 11/18 | 8/18 |
| command-r7b:latest | 0 | 6/18 | 6/18 |
| command-r7b:latest | 2 | 6/18 | 6/18 |
| command-r7b:latest | 4 | 6/18 | 6/18 |
| llama3.1:8b | 0 | 5/18 | 6/18 |
| llama3.1:8b | 2 | 5/18 | 4/18 |
| llama3.1:8b | 4 | 8/18 | 7/18 |
| mistral-nemo:latest | 0 | 12/18 | 12/18 |
| mistral-nemo:latest | 2 | 9/18 | 10/18 |
| mistral-nemo:latest | 4 | 8/18 | 10/18 |
| qwen3:8b | 0 | 9/18 | 16/18 |
| qwen3:8b | 2 | 14/18 | 16/18 |
| qwen3:8b | 4 | 11/16 | 16/18 |

## Equivalence and limits

Tool names, descriptions, leaf-field constraints, prompts and abstention expectations are identical. Only the argument grouping and matching assertion paths differ. Extra optional fields omitted from exact nested expectations are explicitly forbidden in flat expectations. `check_equivalence.py` verifies 68 paired argument outcomes and identical prompts. Suites are frozen copies of the prior experiment.

Eighteen synthetic cases are limited coverage. Two literal-text reply cases expect send mode even though the prompts say reply rather than explicitly send; that policy interpretation warrants review before using this suite as a production benchmark. These prompts and expectations were frozen for this experiment, not changed after observing results. Results can reflect provider/template/parser behavior as well as model capability. There are no independent repetitions in this wider matrix, no statistical significance claim, and no claim that additional distractors improve performance. The earlier Qwen-only experiment contains three temperature-zero consistency runs per variant.

## Inspect and reproduce

`manifest.json` preserves model digests, quantization, server/package versions, commands, order, elapsed times, return codes and coverage. Numbered JSON files are raw results; corresponding logs preserve CLI diagnostics. `summary.json` lists exact cases improved and regressed at each padding level.

```bash
callprobe explain 01-nested.json --suite nested
callprobe explain 01-flat.json --suite flat
```

To reproduce in a fresh directory with the same installed models, copy the scripts and both suites; leave numbered results and manifest out. Use Python with callprobe==0.9.0rc1 installed:

```bash
python check_equivalence.py
python run_matrix.py
python write_report.py
```

No new model is downloaded automatically. The runner configures a 1,800-second subprocess timeout and preserves partial results when a block fails. Recorded duration uses wall-clock time and may include host scheduling or sleep; it is not a controlled inference-speed measurement. Inspect coverage before drawing conclusions.
