---
name: New model run
about: Report a run against a model not yet on the leaderboard
title: "[run] "
labels: run
---

**Model**
Name and tag, e.g. `qwen2.5:7b`. Quantization if relevant.

**Endpoint**
Ollama, LM Studio, llama.cpp server, vLLM, or a hosted provider, and the
`--endpoint` value used.

**Command**
The exact `callprobe run` invocation. The recommended flags are:

```bash
callprobe run --model your-model --pad 0,8,16,24 --repeats 3 \
  --max-tokens 4096 --out results/your-model.json
```

If you used different flags, say why (context window too small for
`--max-tokens 4096`, fewer repeats to keep the run short, etc).

**Results file**
Attach or link the JSON file written by `--out`. This is what a
maintainer will run `callprobe leaderboard` on to add the row.

**Anything surprising**
Truncation, errors, a category that fell apart, anything in the failure
digest worth flagging before it becomes a leaderboard row.
