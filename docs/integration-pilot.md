# Integration pilot

The local file pilot executes real model tool calls against disposable files and saves the
OpenAI-format transcript, before and after filesystem state, and didyoureally findings:

```bash
.venv/bin/python scripts/run_local_file_pilot.py \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --out results/my-file-pilot
```

These are synthetic tasks in a real local application. They are not MailOps captures or production
accuracy. Review the transcript before assigning expected claims; audit output is not ground truth.

## Bring an original application export

The MailOps pilot remains pending the original sanitized trace. The existing email fixtures are
synthetic reproductions of failure signatures, not evidence that the original MailOps export works.
An export must contain assistant messages, tool names and arguments, call IDs, ordering, and explicit
outcomes. Keep failed results and the final user-facing summary. Preserve the original structure.
If an export is unsupported, record the failure and add an adapter against that real structure;
do not quietly relabel the export as a different framework.

Create reviewed claims and expected findings separately from the export. Claim `message_index`
values refer to the canonical Trace event order, not raw export row numbers. Inspect
`load_trace(export).assistant_messages()` to obtain those indices. Use a manifest like:

```json
{
  "sanitized": true,
  "cases": [{
    "id": "failed-send",
    "application": "MailOps",
    "domain": "email",
    "trace": "failed-send.export.json",
    "claims": "failed-send.claims.json",
    "expected": [{"tool": "send_email", "verdict": "masked_failure"}]
  }]
}
```

Paths are relative to the manifest. Tool names must match the actual export. The manifest's
`sanitized` field is a declaration by its author, not an automatic redaction guarantee. Include
at least an honest successful send and an honest failure disclosure alongside a false success claim.
The runner saves prompts' model replies and trace content, so supply only reviewed sanitized data.

```bash
.venv/bin/python scripts/run_trace_pilot.py --manifest captures/manifest.json \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --out results/mailops-pilot
```

Labels are never sent to the model. Results compare extracted verdict and tool counts with the
reviewed expectations. Review claim arguments and call identity as well; exact count agreement
alone does not prove semantic correctness.

## Frozen synthetic comparison

```bash
.venv/bin/python scripts/run_ci_pilot_suite.py \
  --base-url http://localhost:11434/v1 --out results/new-ci-pilot-suite
```

This uses the same seven installed model names as the previous comparison. It runs the balanced
24-case screen, the expanded development suite with Mistral and Qwen, and a separate 24-case set
under `examples/ci-pilot-validation`. The finalists were selected in the previous milestone, not
from these fresh results. Once inspected, a validation set becomes regression evidence for future
work rather than a fresh holdout. One run per model does not measure run-to-run variance.

## Context and correction validation

The separate `examples/context-validation` set contains 16 multi-turn sessions in email, refunds,
files, and scheduling, including eight honest controls. Labels were written before real-model
validation. Regenerate them with `python scripts/build_context_validation.py`.

```bash
.venv/bin/python scripts/run_llm_bench.py --json-mode \
  --cases examples/context-validation \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --out results/my-context-validation
```

After inspecting a run, treat this set as regression evidence rather than a fresh holdout.

## Vague completion validation

`examples/vague-validation` adds 16 frozen cases across email, support, files, and scheduling:
honest completions, missing actions, offers, and honest failure disclosures. Regenerate them with
`python scripts/build_vague_validation.py`. These test whether the extractor identifies a completed
action without copying requested argument values into the claim.

```bash
.venv/bin/python scripts/run_llm_bench.py --json-mode \
  --cases examples/vague-validation \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --out results/my-vague-validation
```

Inspect both verdict exact and detail-free claim agreement. All 16 cases expect either no claims or claims with empty arguments. The final evaluation was the first inspection of these outputs; two superseded implementations ran the set without inspecting it. Subsequent runs are regression tests.


## Completion and acknowledgment validation

`examples/completion-validation` contains 24 frozen sessions across four domains. Each domain
has an honest completion, a phantom completion, an offer, a failure disclosure, an acknowledgment,
and a completed read-only lookup. The latter four must not produce side-effect claims. All expected
claims have empty arguments, so compare both verdict exact and detail-free claim agreement.

Regenerate with `.venv/bin/python scripts/build_completion_validation.py`. Evaluate with:

```bash
.venv/bin/python scripts/run_llm_bench.py --json-mode \
  --cases examples/completion-validation \
  --endpoint http://localhost:11434/v1 mistral-nemo:latest \
  --endpoint http://localhost:11434/v1 qwen2.5:7b \
  --out results/my-completion-validation
```

These cases were frozen before the first evaluation. After inspecting the outputs, treat them as
regressions and create new wording for future validation.
