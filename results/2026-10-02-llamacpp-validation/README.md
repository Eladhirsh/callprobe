# Second serving backend validation — October 2, 2026

Qwen2.5 7B was tested through **llama.cpp b11339-81e39ad34** using the existing
Ollama GGUF, read-only. All **154 planned observations** completed, with
**zero request errors and zero token-limit truncations**. No proposed tools
or mail operations were executed, and no model weights were downloaded.

| Suite | Conditions | llama.cpp passes | Earlier Ollama passes | Matched regressions |
| --- | --- | ---: | ---: | ---: |
| Core | 50 tasks, pad 0, two repeats | 82/100 | 79/100 | 6 |
| Fictional mail | 18 tasks, pads 0/2/4, one repeat | 42/54 | 18/54 | 1 |

Mail passed 15/18 at pad 0, 14/18 at pad 2, and 13/18 at pad 4. Four core
tasks changed verdict between repeats. Repeats change deterministic tool
order, so those differences do not isolate sampling randomness. Padding
also changes distractor selection and tool order. These are 68 distinct tasks
with repeated conditions, not 154 independent tasks.

Both [core](verified-reports/core-compare.md) and
[mail](verified-reports/mail-compare.md) comparisons correctly fail the strict
regression gate despite higher aggregate success. No recorded result was
rescored, discarded, or repaired to improve the totals.

## What this validates

This adds a second real OpenAI-compatible serving backend to the existing
[nine-model Ollama experiment](../2026-10-01-rc3-model-validation/README.md).
It exercises installed-wheel sweeps, server identification, tool-call parsing,
scoring, JUnit export, offline explanations, and comparison gates.

It does **not** validate a live MailOps adapter or establish a model/backend
ranking. Although weights, suite snapshots, request temperature (0), output
limit (4096), padding, and repeats match, templates and server defaults differ.
llama.cpp explicitly used an 8192-token context and `--jinja`; the earlier
Ollama experiment used server context defaults. CallProbe sends no explicit
`parallel_tool_calls` field. These are integration observations with multiple
configuration differences, not a controlled causal experiment.

## Provenance

- [provenance.json](provenance.json) records the exact live-run source commit,
  wheel hash, official backend release/archive hash, GGUF hash, and flags.
- [Server before](evidence/server-before.json) and
  [after](evidence/server-after.json) metadata match. Recorded generation
  settings there are **server defaults**; request temperature and output
  limits override them as recorded in each results file.
- The live requests used source `fd122735604bfb38a18da941ecad2bc2c624bcad`.
  The later offline verification used a separate clean wheel identified in
  [report-build.json](report-build.json), including repeat diagnostics and
  backend identity in comparisons.
- The runtime was downloaded from the official
  [llama.cpp b11339 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11339)
  into a temporary directory. The loopback-only server was stopped afterward.
- Raw files, suites, manifests, and logs remain in `evidence/`.
  [Checksums](checksums.json) cover every archived file except this checksum
  manifest itself.

## Reproduce and verify

Install the exact live-run source in an isolated environment. Serve the
recorded GGUF with llama.cpp b11339 and the flags in `provenance.json`, adding
`--model /path/to/the.gguf`. The runner expects `127.0.0.1:18080` and alias
`qwen2.5:7b`. Use a **new** output directory:

```bash
/path/to/live-run/python run_validation.py /path/to/new-evidence
```

To verify the committed evidence offline through the installed report wheel:

```bash
/path/to/report-wheel/python verify_reports.py /path/to/new-report-directory
```

The verifier checks complete unique coverage, byte-identical suite snapshots,
JUnit counts, observed repeat variations, independently calculated paired
regressions/deltas, and unchanged raw hashes. It calls only offline CLI
commands. The saved [verification report](verified-reports/verification.json)
contains the independently calculated counts and raw hashes. Expected gate
failures remain failures; they are not harness errors. Timing on a shared local
machine is not a throughput benchmark.
