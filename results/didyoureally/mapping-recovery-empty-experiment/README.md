# Superseded empty-repair recovery

This version attempted recovery even when source repair returned no claims. Live context checks showed this could undo a correct reclassification of "Let me handle that" as an acknowledgment, causing a Qwen false claim. The final guard requires that normal repair still asserts a completed action with no tool. Empty repairs do not trigger recovery. The fresh 24-case validation was not run with this version.
