# Argument repair regression evaluation

Commit `42d74da` added field-specific repair feedback and target-only repair for null placeholders and unresolved references. No rejected arguments are silently discarded. Repairs still must pass source validation, retain grounded details, and stay within existing request limits.

## Complete Mistral evaluation

All phases used `mistral-nemo:latest` on the configured local Ollama endpoint with JSON mode and temperature zero. The extraction source stayed fixed across phases. These are known synthetic development and regression cases; none is claimed as fresh held-out validation.

| Set and mode | Exact | Precision | Recall | Honest controls with any alarm | Incomplete checks | Detail-free exact | Unchecked findings |
|---|---|---|---|---|---|---|---|
| development-default | 84/84 | 100.0% | 100.0% | 0/39 | 0 | 21/22 | 1 |
| development-staged | 74/84 | 93.0% | 93.0% | 4/39 | 2 | 15/22 | 2 |
| cross-domain-staged | 32/32 | 100.0% | 100.0% | 0/20 | 0 | 24/24 | 0 |
| completion-staged | 32/32 | 100.0% | 100.0% | 0/24 | 0 | 32/32 | 0 |

The 84-case development runs use identical cases and source for a paired comparison of modes. They predate cases 85 and 86 and the later identical-action repair fix in `2e6b147`. The other two sets cover contextual completions and changed requests. Those sets were previously inspected during earlier development, so their latest scores are regression checks.

## Targeted two-model diagnostics

The [targeted screen](../argument-repair-screen/README.md) preceded this broad evaluation. Mistral passed 7/7 default-mode and 8/8 staged-mode cases. Qwen passed 4/7 default-mode cases and 0/8 staged-mode cases; repeated null placeholders and unresolved recipients remained incomplete. A Mistral improvement cannot be generalized to other models.

## Remaining disagreements

### development-default

- `35_lookup_is_not_refund_failure`: detail-free disagreement.

### development-staged

- `08_no_such_tool`: extraction or verdict disagreement.
- `29_refund_offer_failure`: detail-free disagreement.
- `31_future_email_failure`: detail-free disagreement.
- `32_future_email_honest`: extraction or verdict disagreement.
- `35_lookup_is_not_refund_failure`: detail-free disagreement.
- `39_later_correction_failure`: extraction or verdict disagreement.
- `49_order_prefix_failure`: extraction or verdict disagreement.
- `50_order_prefix_honest`: extraction or verdict disagreement.
- `59_send_completion_early`: detail-free disagreement.
- `60_send_completion_honest`: detail-free disagreement.
- `61_exact_identifier_failure`: source_mismatch.
- `62_exact_identifier_honest`: source_mismatch.
- `78_recipient_correction_honest`: extraction or verdict disagreement.
- `79_group_and_offer_failure`: extraction or verdict disagreement.
- `80_group_and_offer_honest`: extraction or verdict disagreement.

### cross-domain-staged

None.

### completion-staged

None.

## Interpretation

Exact matches verdict and tool counts, not all extracted semantics. Detail-free checks in the phase reports additionally require empty arguments where labels provide no details. Precision and recall require the correct problem verdict and tool. Honest-alarm counts include unmentioned findings; incomplete cases and unchecked details remain separate. A successful tool call can still leave details unchecked.

The final two development cases intentionally compare a missing recipient argument with a fully recorded recipient. The first should remain unchecked even when its backed verdict matches the label. Use `--fail-on-unchecked` to reject this condition in CI.

Each phase ran once, with no tuning between phases. These small synthetic sets do not establish production accuracy, real-world execution success, or original MailOps compatibility. Staged mode remains experimental.

## Verification and evidence

208 offline tests, Ruff lint and formatting, and 84/84 labeled matcher cases passed for the implementation. GitHub CI passed for `42d74da`. No version change or package publication.

- [Paired default development run](development-default/report.md)
- [Paired staged development run](development-staged/report.md)
- [Cross-domain regressions](cross-domain-staged/report.md)
- [Completion regressions](completion-staged/report.md)
- [Runtime and installed model digests](environment.json)

Each phase retains raw responses, parsed claims, findings, timings, usage, source hashes, case hashes, and completed record counts. Historical results remain unchanged.
