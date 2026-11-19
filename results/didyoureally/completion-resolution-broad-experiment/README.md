# Superseded broad contextual instruction experiment

Implementation `271099a` improved the known vague cases but regressed broader extraction. Mistral scored 75/80 and Qwen 67/80 on development, versus 76/80 and 68/80 previously. Qwen also fell from 14/16 to 10/16 on context cases, including a false completion for "Let me handle that."

The new 24 completion-validation cases were not run with this implementation. The final change restores the previous initial and normal repair instructions. It adds bounded recovery only when repair still asserts a completion with no tool and no grounded argument details. Valid empty repairs are accepted. See [final qualification](../completion-resolution-suite/README.md). All experimental outputs remain here for comparison.
