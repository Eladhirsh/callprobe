# Offline contract comparison

These are byte-identical historical Hermes3 results from
[the nine-model schema experiment](https://github.com/Eladhirsh/callprobe/tree/main/results/schema-shape-nine-models),
including the frozen nested and flat suite snapshots. No model calls are made.
The recorded configuration and raw responses remain in each JSON file.

From this directory:

```bash
callprobe compare-contracts baseline.json candidate.json --suite-a nested --suite-b flat
callprobe compare-contracts baseline.json candidate.json --suite-a nested --suite-b flat --format markdown
callprobe explain candidate.json --suite flat
```

The same Hermes3 model passed 13/54 nested observations and 38/54 flat
observations: 27 improvements **and two regressions**. Each contract used
18 synthetic mail cases, pads 0/2/4, one repeat, temperature 0 and 4096 maximum
tokens. This is one historical experiment, not a general model ranking or a
MailOps integration test. Two historical reply prompts were later clarified
in the active example; these snapshots intentionally preserve the original
prompts and hashes. These scores are not rescored or upgraded.

The comparison requires matching prompts, model settings and complete planned
coverage. Request errors are reported separately and excluded from paired
scores. Changed argument assertions are disclosed: a human still needs to
check that they express equivalent requirements. Different contracts can make
cases easier; matching prompts alone cannot establish a fair comparison.

This report is informational, **not a CI gate**. Ordinary
`callprobe compare baseline.json candidate.json --fail-on-regression` rejects
this pair because the suite hashes differ. After choosing a contract, create
a new baseline for that suite and use the ordinary gate for future runs.
