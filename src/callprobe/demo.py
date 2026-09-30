"""The offline demo: `callprobe demo`.

Builds a self-contained directory that teaches the CI-gate/regression and
`explain` workflow using two historical recorded model runs, bundled inside
the package at build time. No model endpoint, no network access, and no
subprocess or model calls: `baseline.json` and `candidate.json` are the
exact, unmodified results from a real Qwen2.5 7B / Qwen3 8B comparison
recorded under ``results/github-issues/``, not a fresh execution and not a
current model ranking.
"""

from __future__ import annotations

import importlib.resources
import shlex

from .examples import generate_example_suite

SUITE_DIRNAME = "github-issues-suite"

REGRESSED_TASKS = ("pagination-upper-values", "comment-body-punctuation")

INSPECT_TASK = "comment-body-punctuation"


def _demo_resource(filename: str) -> str:
    return (importlib.resources.files("callprobe") / "demo_data" / filename).read_bytes().decode("utf-8")


def _demo_readme(suite_dirname: str) -> str:
    return f"""# callprobe offline demo

**OFFLINE DEMO: recorded results, not a fresh run.** Nothing in this
directory was produced by a model request just now, and running the
commands below makes none either. `baseline.json` and `candidate.json` are
byte-identical copies of a real, historical Qwen2.5 7B / Qwen3 8B comparison
recorded under `results/github-issues/` in the callprobe repository (see
`CONDITIONS.md` for the full conditions, including the exact commands that
originally produced them). They are here so you can see what a CI gate
failure and a diagnostic explanation look like without an endpoint, a
downloaded model, or any network access.

## What these numbers are

| model | success |
| --- | --- |
| Qwen2.5 7B (`baseline.json`) | 5/18 |
| Qwen3 8B (`candidate.json`) | 11/18 |

Qwen3 has the higher aggregate score, but it **regressed two previously
passing cases**:

- `pagination-upper-values`: Qwen2.5 supplied the required call; Qwen3
  produced no structured tool call at all.
- `comment-body-punctuation`: Qwen2.5 supplied the nested `body` object;
  Qwen3 supplied a plain string where the schema required `{{"body": ...}}`.

`callprobe compare --fail-on-regression` rejects any previously passing case
that now fails, regardless of the aggregate score. That is the point of a
regression gate: a higher overall number can still hide a previously passing
case that now fails. Run it yourself:

```bash
callprobe compare {shlex.quote('baseline.json')} {shlex.quote('candidate.json')} --fail-on-regression
```

This is expected to **exit 1** here: it is the gate correctly catching the
two regressions above, not a bug in callprobe or in this demo.

## Look at exactly what went wrong

`callprobe explain` reads a saved results file back into a debugging
session, offline, no model calls:

```bash
callprobe explain {shlex.quote('candidate.json')} --suite {shlex.quote(suite_dirname)}
```

To see just the nested-argument regression above, in detail (the model's
call, the schema failure, and the expected shape):

```bash
callprobe explain {shlex.quote('candidate.json')} --suite {shlex.quote(suite_dirname)} --task {shlex.quote(INSPECT_TASK)}
```

`{suite_dirname}/` contains every suite file `explain` and `compare` need
(`tools.yaml`, `tasks.yaml`, `distractors.yaml`, `suite.yaml`); it was
generated the same way as `callprobe init --example github-issues`, and its
content hashes to the exact `suite_hash` recorded inside `baseline.json` and
`candidate.json`.

## Full conditions and raw evidence

`CONDITIONS.md` preserves the conditions that accompanied these two runs when
they were first recorded, with links adjusted for this directory: per-category breakdown, exact model
tags/quantization/digests, and the original reproduce commands. Those
commands require a running Ollama endpoint and the named models; this demo
does not run them for you and needs neither to work.

## This is not a current model ranking

Two model configurations, one suite, one observation per case: this
illustrates the *mechanism* (a regression gate, a diagnostic explanation),
not a ranking of Qwen2.5 against Qwen3, and not a claim about either model
in general. To evaluate your own tools, see `callprobe init --example` or
`callprobe init --from-openapi` and run against a live endpoint.
"""


def generate_demo_files() -> tuple[dict[str, str], dict[str, str]]:
    """Build the demo's top-level files and its suite files separately.

    Returns ``(top_level_files, suite_files)``; the caller writes the suite
    files into a `github-issues-suite/` subdirectory of the demo output.
    Pure and offline: no model, network, or subprocess calls, and nothing
    here mutates the bundled resources or re-scores the recorded runs.
    """
    suite_files, _ = generate_example_suite("github-issues", SUITE_DIRNAME)
    top_files = {
        "baseline.json": _demo_resource("baseline.json"),
        "candidate.json": _demo_resource("candidate.json"),
        "CONDITIONS.md": (_demo_resource("README.md")
            .replace("../../examples/github-issues/README.md", f"{SUITE_DIRNAME}/README.md")
            .replace("(qwen2.5-7b.json)", "(baseline.json)")
            .replace("(qwen3-8b.json)", "(candidate.json)")),
        "comparison.txt": _demo_resource("comparison.txt"),
        "DEMO.md": _demo_readme(SUITE_DIRNAME),
    }
    return top_files, suite_files
