# Try your first API evaluation

This fictional support API has three operations and six human-authored tests.
It needs no API server or credentials: Callprobe evaluates the model's proposed
tool calls and never executes the imported API operations.

From the repository root, with Callprobe 0.6.0 or newer installed:

```bash
callprobe init --from-openapi examples/openapi/support-api.yaml --out my-support-suite
cp examples/openapi/tasks.yaml my-support-suite/tasks.yaml
callprobe validate --suite my-support-suite
callprobe run --suite my-support-suite --model qwen2.5:7b \
  --pad 0 --repeats 1 --max-tokens 4096 --out my-support-suite/baseline.json
```

Ollama must be running with the model installed. Other OpenAI-compatible
model servers can be selected with `--endpoint`.

After changing your model or serving configuration, repeat the same run with
`--out my-support-suite/candidate.json`, then compare:

```bash
callprobe compare my-support-suite/baseline.json my-support-suite/candidate.json \
  --fail-on-regression
```

## Use your own API

Replace `support-api.yaml` with your local OpenAPI 3.0 or 3.1 YAML/JSON document.
The generated `tasks.yaml` contains commented drafts, not runnable tests. Write
real user requests and the outcomes you expect. Include missing-information
and unsupported-capability cases, not just happy paths.

The generated tool for `POST /orders/{order_id}/refunds` takes arguments like:

```json
{
  "path": {"order_id": "ORD-991003"},
  "body": {"amount_cents": 1250, "reason": "damaged"}
}
```

Path, query, headers, cookies, and body stay in separate groups to avoid name
collisions. Make sure this mapping agrees with the adapter in your application.
Use `--tag support` to import a smaller set of operations, and inspect the
generated `import-report.json` for diagnostics. Unsupported operations cause
the import to fail by default; `--skip-unsupported` explicitly omits them and
records the reasons. Local references are resolved without fetching URLs.

An API schema defines valid inputs, not the correct behavior for a user
request. Review the examples and write your own assertions before trusting a
model score. API-schema or task changes require a fresh baseline because the
suite hash changes.

## Reading a real result

A local smoke run on September 21, 2026 with `qwen2.5:7b`, no distractors,
one repeat, and a 4096-token budget passed 2 of these 6 tests. The model chose
the correct tool in all three call cases, but flattened the arguments instead
of using `path`, `query`, and `body`. Schema validation caught each failure.
It also called `get_order` for the unsupported address-change request.

A second run produced the same outcomes and the regression gate passed.
That means no regression against this baseline; it does not mean the model
meets your application's quality requirements. These six tests demonstrate
the workflow, not a general model ranking.
