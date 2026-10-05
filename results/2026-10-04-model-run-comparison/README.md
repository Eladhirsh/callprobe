# Offline comparison gate validation

The new development comparison command reproduces the decision from the
[mixed-action experiment](../2026-10-04-mixed-action-scope/README.md) using its
saved model records. This check makes no inference requests and adds no new
model-accuracy evidence.

| Comparison | Paired attempts | Baseline exact | Candidate exact | Regressions | Exit code |
|---|---|---|---|---|---|
| Focused, three models | 48 | 43 | 48 | 0 | 0 |
| Bundled, Mistral | 102 | 102 | 100 | 2 | 1 |

The broad report identifies cases 73 and 74 as individual regressions. The
focused gain does not justify accepting the broader loss. A release evaluation
must cover both; the comparison command cannot infer which other suites should
have been run.

The JSON reports contain input hashes, coverage, and changed case identities.
They omit raw replies and claim arguments. `validation.json` identifies the
comparison script by source hash. The earlier experiment records source, suite,
and model provenance for the input runs. Raw records remain local.

The command compares complete runs with compatible configuration and recomputes
saved exactness from verdict and tool multisets. Its gate is about regressions;
unchanged verdict mismatches can pass, but extraction errors cannot. Model
names are not cryptographic identities. Neither a passing gate nor matching
verdict counts verifies all claim arguments or real business outcomes.
