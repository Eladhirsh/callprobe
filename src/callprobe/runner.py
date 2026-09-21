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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .client import ChatClient
from .models import Bundle, Run, RunConfig, Suite, Task, TaskResult
from .scoring import SCORING_VERSION, score

WorkItem = tuple[int, int, Task]


def prepare_config(suite: Suite, config: RunConfig) -> RunConfig:
    """Record the suite and rubric actually used, including the planned coverage."""
    if not suite.tasks:
        raise ValueError("suite contains no tasks")
    if config.repeats < 1 or not config.pads or any(p < 0 for p in config.pads):
        raise ValueError("repeats must be positive and pads must be nonnegative")
    if len(set(config.pads)) != len(config.pads):
        raise ValueError("pads must not contain duplicates")
    return config.model_copy(update={
        "suite_name": suite.name,
        "suite_version": suite.version,
        "suite_hash": suite.hash,
        "scoring_version": SCORING_VERSION,
        "task_ids": [task.id for task in suite.tasks],
    })


def validate_resume(config: RunConfig, resume: Run) -> None:
    """Never combine cached observations from different experiments.

    Pads and repeats may expand; each cached result retains its original key.
    Legacy files remain readable but cannot safely resume without provenance.
    """
    fields = (
        "model", "endpoint", "temperature", "max_tokens", "quantization",
        "suite_hash", "suite_version", "scoring_version", "task_ids",
        "server_name", "server_version",
    )
    mismatches = [name for name in fields
                  if getattr(config, name) != getattr(resume.config, name)]
    if not resume.config.suite_hash or resume.config.scoring_version is None:
        mismatches.append("missing suite/scoring provenance")
    if mismatches:
        raise ValueError("incompatible resume: " + ", ".join(mismatches) + "; start a new run")
    seen = set()
    for result in resume.results:
        key = (result.task_id, result.pad, result.repeat)
        if (key in seen or result.model != config.model
                or result.task_id not in (config.task_ids or [])
                or result.pad not in resume.config.pads
                or not 0 <= result.repeat < resume.config.repeats):
            raise ValueError("incompatible resume: duplicate or invalid result " + str(key))
        seen.add(key)


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


def _work_items(suite: Suite, config: RunConfig) -> list[WorkItem]:
    """Canonical order: pad outer, repeat middle, task inner.

    The result list is always assembled in this order regardless of
    concurrency or resume, so the output file is deterministic.
    """
    return [
        (pad, repeat, task)
        for pad in config.pads
        for repeat in range(config.repeats)
        for task in suite.tasks
    ]


def run_suite(
    suite: Suite,
    client: ChatClient,
    config: RunConfig,
    *,
    on_result=None,
    on_progress=None,
    concurrency: int = 1,
    resume: Run | None = None,
) -> Run:
    """Run every (pad, repeat, task) combination and return a Run.

    on_result(result) fires once per landed result, in whatever order it
    lands (useful for a progress counter). on_progress(run) fires with the
    run assembled so far, always in canonical order, for incremental
    writes. Ctrl-C returns the run assembled from whatever finished, in
    canonical order, instead of raising.
    """
    config = prepare_config(suite, config)
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if resume is not None:
        validate_resume(config, resume)
    started_at = resume.started_at if resume else datetime.now(timezone.utc).isoformat()
    items = _work_items(suite, config)

    resumed: dict[tuple[str, int, int], TaskResult] = {}
    if resume is not None:
        # Request errors are not completed observations; retry them on resume.
        resumed = {(r.task_id, r.pad, r.repeat): r for r in resume.results if not r.error}

    results: list[TaskResult | None] = [None] * len(items)

    def compute(pad: int, repeat: int, task: Task) -> TaskResult:
        cached = resumed.get((task.id, pad, repeat))
        if cached is not None:
            return cached
        bundle, tools = build_toolset(suite, task, pad, seed=repeat)
        completion = client.complete(
            model=config.model,
            messages=task.messages,
            tools=tools,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        return score(task, bundle, completion, model=config.model, pad=pad, repeat=repeat)

    def snapshot(finished_at: str | None) -> Run:
        return Run(
            config=config,
            started_at=started_at,
            finished_at=finished_at,
            results=[r for r in results if r is not None],
        )

    def land(index: int, result: TaskResult) -> None:
        results[index] = result
        if on_result:
            on_result(result)
        if on_progress:
            on_progress(snapshot(None))

    try:
        if concurrency <= 1:
            for index, (pad, repeat, task) in enumerate(items):
                land(index, compute(pad, repeat, task))
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {
                    pool.submit(compute, pad, repeat, task): index
                    for index, (pad, repeat, task) in enumerate(items)
                }
                try:
                    for future in as_completed(futures):
                        land(futures[future], future.result())
                except KeyboardInterrupt:
                    # Threads already mid-request cannot be preempted and
                    # are left to finish or hit their own timeout; this
                    # only stops queued work from starting.
                    for f in futures:
                        f.cancel()
                    raise
    except KeyboardInterrupt:
        sys.stderr.write("\n\ninterrupted, reporting on what finished\n\n")
        return snapshot(datetime.now(timezone.utc).isoformat())

    return snapshot(datetime.now(timezone.utc).isoformat())
