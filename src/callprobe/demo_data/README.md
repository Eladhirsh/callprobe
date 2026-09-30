# GitHub issue/comment evaluation

This compares two local model configurations on the same 18 authored cases
from [the GitHub API example](../../examples/github-issues/README.md).
The three request contracts come from GitHub's official OpenAPI description;
the repository names, issue numbers, conversation text, and expected outcomes
are synthetic. No GitHub API operations are executed.

## Results

| Category | Qwen2.5 7B | Qwen3 8B |
| --- | ---: | ---: |
| Overall | 5/18 (27.8%) | 11/18 (61.1%) |
| Select | 0/5 | 3/5 |
| Arguments | 2/5 | 1/5 |
| Abstain | 2/5 | 5/5 |
| Conversation depth | 1/3 | 2/3 |

Both runs completed all 18 cases with zero request errors and zero truncated
responses. Qwen3 improved eight cases and regressed on two. The strict
regression gate **fails**, despite the higher overall score:

- `pagination-upper-values`: Qwen2.5 supplied the required call; Qwen3
  produced no structured tool call.
- `comment-body-punctuation`: Qwen2.5 supplied the nested request body;
  Qwen3 supplied a string where the `body` object was required.

Qwen3 passed all five explicit abstention cases. Both models still failed
some nested-argument contracts. These observations support investigating
argument-shape reliability before treating either configuration as a replacement.

See [the exact comparison](comparison.txt) and the raw
[Qwen2.5](qwen2.5-7b.json) / [Qwen3](qwen3-8b.json) call evidence.

## Conditions

- Callprobe 0.6.0, scoring version 2; Ollama 0.34.2.
- Suite hash: `877e1bb5a8652258`.
- One observation per case, temperature 0, zero added distractors,
  4096 maximum output tokens, three available tools, sequential requests.
- Both models use the same generated suite and task file.
- Model tags: `qwen2.5:7b` and `qwen3:8b` (local Ollama defaults).
- Both installed models were Q4_K_M with a 4096-token runtime context.
  Observed model digests: Qwen2.5
  `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`,
  Qwen3 `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
- The importer preserves nested `path`, `query`, and `body` arguments;
  flattening these arguments is a schema failure.

## Reproduce

Follow the example's import/copy/validate commands first. From the repository
root, the exact model commands used here are:

```bash
callprobe run --suite github-issues-suite --model qwen2.5:7b \
  --pad 0 --repeats 1 --max-tokens 4096 --out results/github-issues/qwen2.5-7b.json
callprobe run --suite github-issues-suite --model qwen3:8b \
  --pad 0 --repeats 1 --max-tokens 4096 --out results/github-issues/qwen3-8b.json
callprobe compare results/github-issues/qwen2.5-7b.json results/github-issues/qwen3-8b.json \
  --fail-on-regression
```

## Interpretation limits

These results describe this small suite and these local model/serving
configurations, not general model rankings. A single observation cannot
measure repeatability. The six-case support demo is a different suite and
must not be pooled into this comparison. The regression gate evaluates
changes against the baseline, not whether either model is good enough for
an application. No API response correctness or multi-step execution is tested.

The offline tests construct each expected call and require it to pass the
scorer, reject representative malformed shapes, and check that YAML loading
preserves the issue number in the prompt containing `#42`.
