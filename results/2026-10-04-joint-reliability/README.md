# Unified repository reliability checks

Verified revision `31067454d678b51a1d2868b111b469baa062e52c` after importing
Didyoureally into Callprobe. All checks here are offline. Live agent behavior is
reported separately.

| Check | Result |
|---|---|
| Callprobe tests | 1,441 passed |
| Didyoureally tests | 267 passed |
| Labeled matcher benchmark | 88 of 88 exact; 45 problems caught, zero false alarms or misses |
| Ruff | Package and shared workflow lint and formatting passed |
| Group allocation oracle | 4,096 configurations, zero failures |
| Malformed report field shapes | 456 mutations, zero uncaught exceptions |
| GitHub CI | All jobs passed on Python 3.10 through 3.13 |

[Machine-readable checks](checks.json) and [GitHub CI](https://github.com/Eladhirsh/callprobe/actions/runs/37227137221)
record the tested revision. Local tests used Python 3.14.2. Isolated wheels were
installed together and exercised outside the checkout: packaged task validation,
shared agent initialization, a masked-failure audit, and all 88 matcher cases.
Both historical 12-case agent reports replayed without changed decisions or findings.
Package versions were unchanged and nothing was published.

## What the stress checks establish

The [allocation oracle](group_allocation_oracle_results.json) enumerates every
three-claim, three-call compatibility graph and every success and error arrangement:
512 graphs times eight status patterns. It compares the matcher with independent
brute-force partial assignments, maximizing successful assignments first and all
compatible assignments second. It also checks call uniqueness and compatible edges.
This is exhaustive for that graph size, not for arbitrary sessions.

The [report shape sweep](report-shape-sweep/results.json) replaces 76 saved fields
with six JSON shapes each. There were 428 setup-error exits and 28 valid comparisons;
some replacements are unchanged or remain valid. Zero uncaught exceptions is an
exception-containment result, not 456 successful detections or evidence authenticity.

The regular suite also includes 36 planted failures and controls across billing,
email, files, and scheduling. It covers wrong details, phantom actions, masked
failures, unmentioned actions, premature completion, retries, and honest outcomes.
These use scripted model responses and labeled claims. They do not measure LLM
extraction accuracy.

## Reproduce the stress checks

From the repository root after the shared development install:

```sh
.venv/bin/python results/2026-10-04-joint-reliability/group_allocation_oracle.py \
  --out /tmp/group-allocation-oracle.json
.venv/bin/python results/2026-10-04-joint-reliability/report-shape-sweep/agent_compare_shape_sweep.py \
  --repo . --out /tmp/new-report-shape-sweep
```

Use a new output directory for the shape sweep. It needs the development test
helpers at the recorded revision. Each report includes source and script hashes.
For the full suite and benchmark commands, see [contributing](../../CONTRIBUTING.md).
