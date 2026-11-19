# Superseded direct repair experiment

Restoring the old initial extraction instruction while replacing its source repair scored 16/16 on Mistral and 11/16 on Qwen. It lost a Qwen scheduling case that the original repair handled. The final implementation preserves normal repair and attempts focused recovery only when normal repair still asserts a completion but loses its known tool mapping. Empty repairs do not trigger recovery. See [final qualification](../completion-resolution-suite/README.md).
