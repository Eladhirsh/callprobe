"""Bootstrap confidence intervals for a success rate.

At temperature 0 the repeats of a task mostly vary tool order, not the
model's reasoning, so results from the same task id are correlated with
each other rather than independent trials. Resampling individual results
would understate the true uncertainty. Resampling task ids instead, and
pulling every result for each sampled id along with it, keeps that
correlation intact.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

SEED = 1234
ITERATIONS = 2000


def bootstrap_ci(
    results: list[Any],
    field: str = "success",
    *,
    confidence: float = 0.95,
    iterations: int = ITERATIONS,
    seed: int = SEED,
) -> tuple[float, float]:
    # Only each cluster's numerator and denominator are needed. Keep the
    # original task order and RNG draws so intervals match row-level pooling.
    by_task: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        counts = by_task[r.task_id]
        counts[0] += int(bool(getattr(r, field)))
        counts[1] += 1
    task_ids = list(by_task)
    if not task_ids:
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(task_ids)
    rates = []
    for _ in range(iterations):
        successes = observations = 0
        for _ in range(n):
            numerator, denominator = by_task[task_ids[rng.randrange(n)]]
            successes += numerator
            observations += denominator
        rates.append(successes / observations)
    rates.sort()

    tail = (1 - confidence) / 2
    lo = rates[int(tail * iterations)]
    hi = rates[min(int((1 - tail) * iterations), iterations - 1)]
    return (lo, hi)
