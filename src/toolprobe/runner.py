"""Execute a suite against one endpoint.

Two sweeps matter and both are cheap to run here:

    pad      extra irrelevant tools added to the bundle. Most small models
             hold up at 5 tools and fall apart somewhere between 8 and 20.
    repeats  the same task run more than once. Tool calling is not
             deterministic even at temperature 0, so a single pass reports
             a number with no error bar.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from .client import ChatClient
from .models import Bundle, Run, RunConfig, Suite, Task, TaskResult
from .scoring import score


def build_toolset(
    suite: Suite, task: Task, pad: int, seed: int
) -> tuple[Bundle, list[dict]]:
    bundle = suite.bundles[task.bundle]
    tools = list(bundle.tools)
    if pad and suite.distractors:
        rng = random.Random(f"{task.id}:{pad}:{seed}")
        blocked = {t.name for t in tools} | set(task.exclude_distractors)
        pool = [d for d in suite.distractors if d.name not in blocked]
        rng.shuffle(pool)
        tools.extend(pool[:pad])
    rng = random.Random(f"order:{task.id}:{pad}:{seed}")
    rng.shuffle(tools)  # position bias is real, do not let it hide
    padded = Bundle(name=bundle.name, tools=tools)
    return padded, [t.as_openai() for t in tools]


def run_suite(
    suite: Suite,
    client: ChatClient,
    config: RunConfig,
    *,
    on_result=None,
) -> Run:
    run = Run(
        config=config,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    for pad in config.pads:
        for repeat in range(config.repeats):
            for task in suite.tasks:
                bundle, tools = build_toolset(suite, task, pad, seed=repeat)
                completion = client.complete(
                    model=config.model,
                    messages=task.messages,
                    tools=tools,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                result: TaskResult = score(
                    task,
                    bundle,
                    completion,
                    model=config.model,
                    pad=pad,
                    repeat=repeat,
                )
                run.results.append(result)
                if on_result:
                    on_result(result)
    run.finished_at = datetime.now(timezone.utc).isoformat()
    return run


def interrupted_run(config: RunConfig, results: list[TaskResult]) -> Run:
    """Build a Run from partial results so Ctrl-C still reports something."""
    now = datetime.now(timezone.utc).isoformat()
    return Run(config=config, started_at=now, finished_at=now, results=list(results))
