# Interrupted general regeneration experiment

The screen was stopped after Qwen regressed on scheduling: regeneration repeated null placeholders that replay-based repair had removed. No development or fresh validation phase ran. The final implementation keeps replay-based repair for format errors and regenerates only source mismatches.
