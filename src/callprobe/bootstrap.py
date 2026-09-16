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
    by_task: dict[str, list[Any]] = defaultdict(list)
    for r in results:
        by_task[r.task_id].append(r)
    task_ids = list(by_task)
    if not task_ids:
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(task_ids)
    rates = []
    for _ in range(iterations):
        pooled = []
        for _ in range(n):
            pooled.extend(by_task[task_ids[rng.randrange(n)]])
        rates.append(sum(1 for r in pooled if getattr(r, field)) / len(pooled))
    rates.sort()

    tail = (1 - confidence) / 2
    lo = rates[int(tail * iterations)]
    hi = rates[min(int((1 - tail) * iterations), iterations - 1)]
    return (lo, hi)
