# Native Ollama recording adapter validation

A clean wheel built from commit `426d669` was installed into a fresh Python
3.14.2 environment. It captured 36 new non-streaming native `/api/chat` responses
from Ollama 0.34.2 and normalized them with `parse_ollama_completion`.

The generated `support` example supplied six fictional tasks, each repeated twice
with pad 0, temperature 0, and `num_predict: 4096`. Requests were sequential, with
a 90-second timeout and no retries. Tool order came from
`build_toolset(suite, task, pad=0, seed=repeat)`. Thinking used the server default.
No application tools were executed.

| Model | Successful decisions | Request errors | Truncated | Thinking responses | Exact replay |
| --- | ---: | ---: | ---: | ---: | --- |
| llama3.2:3b | 5/12 | 0 | 0 | 0 | Yes |
| granite3.3:8b | 9/12 | 0 | 0 | 0 | Yes |
| qwen3:8b | 7/12 | 0 | 0 | 12 | Yes |

Every response preserved native tool-call count, prompt/generated token counts,
and thinking text. Client-measured latency was supplied explicitly. Each model's
normalized recordings were scored, exported with `recordings_to_json`, and
replayed with the installed `python -m callprobe replay`. Every TaskResult field
and the full summary matched the direct offline scoring result exactly. All model
digests were unchanged at the end; timestamps, digests, and suite hash are in
[summary.json](summary.json).

This is an integration compatibility check on six tasks, not a model ranking or
a real MailOps validation. The 21/36 successes describe model decisions; all 36
passed adapter/export/replay consistency checks. Live responses had no truncation;
synthetic tests cover truncation, malformed inputs, multiple calls, partial
responses, and lifecycle acknowledgements. Raw responses and individual results
remain local and are not included in this report. Publication remains deferred.
