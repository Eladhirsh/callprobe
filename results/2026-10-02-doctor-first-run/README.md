# Installed first-run validation — October 2, 2026

A clean wheel built from the exact source in [provenance.json](provenance.json)
was installed into a new temporary environment. Commands ran outside the checkout
with no `PYTHONPATH` or API-key environment variables. No global installation was
changed and no model was downloaded.

The bundled support suite was created and validated (six active tasks). Doctor
found the already-installed `qwen2.5:7b` on Ollama 0.34.2, identified the backend,
and reported `generation_tested: false`. A deliberately absent model returned an
inconclusive warning; a URL containing placeholder credentials was rejected
before endpoint access without echoing those credentials in its error message.

The six-case model run then completed: **2/6 passed, zero request errors, zero
truncations**. The four model failures remain in the raw results. A successful
setup check does not promise correct tool calls. This is a first-run smoke test,
not an independent estimate of model quality. No proposed support API operation
was executed. Explain, JUnit export, and a self-comparison gate all completed.

[Commands and exit codes](evidence/commands.json), [raw results](evidence/baseline.json),
and every command's stdout/stderr are retained under `evidence/`.
The URL/auth strings in the invalid-input test are deliberate placeholders.

To repeat, install the recorded source in an isolated environment with Qwen2.5
already served locally by Ollama, then use a new output directory:

```bash
/path/to/installed/python verify_installed.py /path/to/new-evidence
```

This script makes six completion requests after its read-only doctor checks.
The source test suite separately checks HTTP request methods, authentication
scope, status/transport failures, malformed catalogs, and local validation.
