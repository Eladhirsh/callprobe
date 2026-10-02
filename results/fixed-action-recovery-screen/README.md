# Fixed-action recovery screen

Commit `ea133d4` passed all six selected known regression cases with both Mistral and Qwen. These cases cover honest and masked-failure completions in email, files, and scheduling. This is targeted diagnostic evidence, not a fresh accuracy estimate. Offers, changed requests, and detailed argument comparisons were not in this screen.

The fixed action IDs prevented tool identity loss in the scheduling cases. The detail prompt distinguishes general completion language from identifiers, and source validation rejects unresolved pronouns. Generic words can still be assigned the wrong argument meaning; this does not establish reliable extraction on arbitrary traces.

[Results](report.md) and raw model replies are retained. The earlier interrupted diagnostic remains in [fixed-action-suite](../fixed-action-suite/README.md).
