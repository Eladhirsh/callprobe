# Initial two-stage extraction experiment

This diagnostic used the first uncommitted staged extractor draft. Its action prompt lacked the later contrastive examples, and its input included the target in a conversation list identified by index. It was evaluated only on known completion-validation cases. Mistral improved some mappings but introduced an acknowledgment false alarm; Qwen still had scope and mapping errors.

The next candidate supplies the target explicitly and adds examples contrasting accepting work, completing a change, and completing a lookup. Fresh staged-validation cases were not evaluated or used for these changes. Raw replies and source hashes are retained here; final committed implementation results are reported separately.
