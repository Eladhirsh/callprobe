# CI pilot reliability results

Real local model extraction on synthetic cases, plus a real disposable-file application pilot.
These are single runs, not production accuracy or a stability guarantee.

## Seven-model screen

| Model | Previous exact | Current exact | Honest false alarms | Extraction errors |
|---|---|---|---|---|
| mistral-nemo:latest | 24/24 | 24/24 | 0/12 | 0 |
| qwen2.5:7b | 22/24 | 24/24 | 0/12 | 0 |
| llama3.2:3b | 21/24 | 20/24 | 0/12 | 4 |
| hermes3:8b | 18/24 | 20/24 | 0/12 | 4 |
| llama3.1:8b | 18/24 | 20/24 | 0/12 | 4 |
| phi4-mini:latest | 18/24 | 22/24 | 0/12 | 0 |
| granite3.3:8b | 16/24 | 24/24 | 0/12 | 0 |

Same 24 screening transcripts, labels, model names, and JSON mode as the previous comparison.
The current profile adds source spans, grouped-call matching, and explicit incomplete extraction.

## Previously selected finalists

| Model | Previous 60 | Current same 60 | Expanded 72 | Fresh 24 | Fresh errors |
|---|---|---|---|---|---|
| mistral-nemo:latest | 48/60 | 50/60 | 62/72 | 24/24 | 0 |
| qwen2.5:7b | 47/60 | 42/60 | 53/72 | 24/24 | 0 |

| Model | Development precision | Development recall | Development honest false alarms | Development errors | Fresh precision | Fresh recall |
|---|---|---|---|---|---|---|
| mistral-nemo:latest | 81.6% | 81.6% | 2/32 | 3 | 100.0% | 100.0% |
| qwen2.5:7b | 86.7% | 68.4% | 1/32 | 12 | 100.0% | 100.0% |

### Fresh results by domain

| Model | Email | Refunds | Files | Scheduling |
|---|---|---|---|---|
| mistral-nemo:latest | 6/6 | 6/6 | 6/6 | 6/6 |
| qwen2.5:7b | 6/6 | 6/6 | 6/6 | 6/6 |

## Assessment

The new profile is better at explicit identifiers and some grouped actions, but the full suite still
exposes vague-claim errors, unwanted argument inference, and malformed groups. Qwen regressed from
47/60 to 42/60 on the unchanged development cases. Mistral improved from 48/60 to 50/60, but its
honest false alarms increased from one to two on those cases. Do not infer general reliability from
the perfect fresh scores: that set uses simpler single-action sessions.

## Completed changes

- Copy exact argument values from source spans. Quoted identifiers retain their exact punctuation and Unicode. Literal identifiers must be present in a source span.
- Preserve one source message for grouped claims and prohibit reusing a call within the group. Separate claim items from the same message and tool are normalized into the same group.
- Report incomplete extraction with exit code 3 and JSON status incomplete, distinct from findings and invalid input. Continue checking the rest of a batch.
- Provide a manifest runner for sanitized original application captures with separate reviewed labels.

## Real file application pilot

Six model-driven sessions executed real deletes in temporary directories. All six audit outputs agreed
with explicitly labeled expectations from transcript review. Both models disclosed missing-file failures. Mistral invented disallowed absolute
paths in the two-file task, so it failed the task but truthfully disclosed the tool failures. Qwen
completed the available delete and disclosed the missing file. No false completion claims occurred
in this small live pilot, so it tests honest controls, not sensitivity to live agent lies.

The final value-based profile was also used to re-audit all six captured sessions with both models.
Both scored 6/6 with no false alarms or extraction errors. [Final capture re-audit](../local-file-pilot-final/evaluation/report.md).
These twelve checks reuse the six captured sessions; they are not twelve new live-agent sessions.

**The original MailOps pilot is pending its sanitized export.** Synthetic email fixtures and this
file pilot do not establish compatibility with the original MailOps trace format.

## Interpretation and evidence

Exact scoring compares verdict and tool counts. It does not prove extracted arguments or call identity
are semantically correct. Precision and recall count problem verdict and tool pairs and exclude
unmentioned findings. Misclassifying a phantom as contradicted can count as both a false positive and
a miss. Extraction errors fail exact scoring and expected problems in those cases count as missed.
Honest false-alarm counts exclude extraction errors; read both columns together. Errors include provider failures as well as rejected model output.

The original development labels were retained for comparability. Some partial-action labels expect
contradicted where distinct-call grouping now yields phantom after consuming the one available call.
Those are exact-score failures even though both outputs flag an unsupported action. Newly added
grouped-action cases explicitly test distinct-call semantics.

The 24 new validation cases were written before this suite ran. No prompt or matcher tuning used their
results. They are synthetic and author-created, and should be treated as regressions in future work.
The same previously selected two finalists were qualified; current screen scores did not select them.

- [Seven-model screen](screen/report.md)
- [Expanded development qualification](development/report.md)
- [Fresh validation](validation/report.md)
- [Recorded local model digests and version](environment.json)
- [Real file-agent transcripts and review](../local-file-pilot/README.md)
- [Final source-value targeted run](../source-values-smoke/report.md)
- [Provisional numeric-ID diagnostic](../ci-pilot-span-id-diagnostic/README.md)
- [Identifier targeted run](../source-spans-smoke/report.md)
- [Initial grouped-action diagnostic run](../grouped-actions-smoke/report.md)
- [Corrected grouped-action targeted run](../grouped-actions-final/report.md)
- [Integration instructions](../../docs/integration-pilot.md)

Raw replies, parsed claims, findings, source hashes, prompt hashes, and case hashes are saved per run.
Targeted checks were used during development and must not be represented as fresh validation.
All src file hashes are identical across the final screen, development, and fresh validation phases. The provisional numeric-ID run is retained separately; its one partial validation row was not inspected or used for tuning.
