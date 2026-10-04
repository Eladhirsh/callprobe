# Partial-action annotation audit

Cases 11 through 16 describe two distinct objects in one message. Their labels now share a group ID, matching the grouped-action policy. In failure cases 11, 13, and 15, the second action is phantom because no unused call supports it. Previously those labels reused the first call and called the second action contradicted. Honest controls still require two successful calls. No matcher or extraction code changed.

The table below rescored archived predictions under the corrected labels. It makes no model calls and is not a new end-to-end benchmark. Original result files and their original scores remain unchanged.

| Source | Model | Original exact | Audited exact |
|---|---|---|---|
| development-staged (staged) | mistral-nemo:latest | 61/82 | 63/82 |
| development (default) | mistral-nemo:latest | 76/80 | 78/80 |
| development (default) | qwen2.5:7b | 68/80 | 70/80 |

Changed expectations apply only to the three failure cases. This audit does not correct missing actions, misplaced arguments, or incomplete extractions. The staged grouped-refund failures remain failures when the extractor puts the second order ID in the amount field.
