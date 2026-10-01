# Published 0.9.0rc1 live model demo

Tested the package installed from PyPI against local Ollama Qwen 2.5 7B.
The fictional mail suite contains 18 cases, each evaluated with zero and two
extra distractor tools: 36 observations, one repeat, temperature 0.
No email API operations were executed.

| Configuration | Success |
| --- | --- |
| No distractors | 4/18 (22.2%) |
| Two distractors | 7/18 (38.9%) |
| Overall | 11/36 (30.6%) |

All 36 requests completed, with zero request errors and zero truncations.
Tool selection scored 88.9%. Twenty-one observations failed schema and
argument checks; the diagnostics identify flattened arguments that should
be nested under `path`, `query`, or `body`. Four observations called a tool
when the expected behavior was to abstain. Suggestions are advisory and do
not change scores. One repeat does not establish that distractors help.

For example, `get-by-id` at pad 0 supplied `{"message_id":"msg-1042"}`
where the tool requires `{"path":{"message_id":"msg-1042"}}`.

## Reproduce

From this directory, with the named model already served by local Ollama:

```bash
uv tool install callprobe==0.9.0rc1 --force
callprobe validate --suite suite
callprobe run --suite suite --model qwen2.5:7b --pad 0,2 --repeats 1 \
  --max-tokens 4096 --retries 0 --out rerun.json
callprobe compare qwen2.5-7b.json rerun.json --fail-on-regression
```

Inspect the original evidence without a model or network:

```bash
callprobe explain qwen2.5-7b.json --suite suite --task get-by-id
callprobe leaderboard qwen2.5-7b.json
```

The raw run preserves all responses and scores. `diagnostics.json` contains
the full diagnostic report; `provenance.json` records the model digest,
quantization, server version, and installed package source. This is a
synthetic mail contract, not a MailOps integration or general model ranking.
