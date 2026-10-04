"""Score externally recorded completions offline.

Lets applications such as MailOps feed their already-produced final tool
decisions back through CallProbe's existing rubric without standing up an
HTTP proxy in between. The caller's model label and the generation
metadata carried on each Completion (tokens, latency, finish reason,
calls, errors) are preserved as recorded; this module treats them as
caller assertions and does not re-execute the model, re-tokenize the
prompt, or re-time the request. Partial input stays partial: no
planned-but-missing coordinate is invented, and a configured sweep with
a million repeats stays bounded by whatever the caller actually hands in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from . import __version__
from .client import Completion
from .models import Call, Run, RunConfig, Suite
from .runner import build_toolset, prepare_config
from .scoring import score


@dataclass(frozen=True)
class RecordedCompletion:
    """One externally recorded final tool decision at a (task, pad, repeat).

    ``completion`` carries the model's calls, parse errors, request error,
    truncation flag, token counts and latency as the caller observed them.
    Those values are consumed by the existing scorer unchanged; this type
    does not re-verify or re-time them.
    """

    task_id: str
    completion: Completion
    pad: int = 0
    repeat: int = 0


def _require_int(value, label: str) -> None:
    # bool is a subclass of int in Python, so an identity check is needed
    # to reject True/False masquerading as a coordinate.
    if type(value) is not int:
        raise ValueError(f"recording {label} must be a plain integer")


def _validate_completion(completion: Completion, index: int) -> None:
    """Reject adapter shape errors without echoing recorded response values.

    Completion is a mutable dataclass, and Call fields can be reassigned after
    construction. Validate consumed fields before the scorer can coerce values
    or mistake an empty container for a successful no-call response. Raw provider
    metadata is not consumed by scoring and remains opaque.
    """
    def require(condition: bool, field: str) -> None:
        if not condition:
            raise ValueError(f"recording {index} has invalid completion {field}")

    for field in ("content", "reasoning", "finish_reason"):
        require(isinstance(getattr(completion, field), str), field)
    require(completion.error is None or isinstance(completion.error, str), "error")
    for field in ("prompt_tokens", "completion_tokens"):
        value = getattr(completion, field)
        require(type(value) is int and value >= 0, field)
    latency = completion.latency_ms
    finite_latency = False
    if type(latency) in (int, float):
        try:
            finite_latency = math.isfinite(latency) and latency >= 0
        except OverflowError:
            pass
    require(finite_latency, "latency_ms")
    require(isinstance(completion.calls, list), "calls")
    for call in completion.calls:
        require(isinstance(call, Call), "calls entry")
        require(isinstance(call.name, str), "call name")
        require(isinstance(call.arguments, dict), "call arguments")
        require(call.id is None or isinstance(call.id, str), "call id")
        require(isinstance(call.raw_arguments, str), "call raw_arguments")
        require(call.parse_error is None or isinstance(call.parse_error, str), "call parse_error")


def score_recordings(
    suite: Suite,
    config: RunConfig,
    recordings: Iterable[RecordedCompletion],
) -> Run:
    """Score externally recorded completions. No network, no model call.

    Every completion shape and supplied identity is validated against the
    prepared config and suite before any scoring runs; a single bad record aborts the
    batch rather than scoring half of it. Results are returned in the
    canonical pad-config / repeat / suite-task order, bounded by the
    input: a config.repeats of a million is harmless as long as only a
    few repeats are actually recorded. Partial input stays partial — the
    returned Run has exactly one result per supplied recording and no
    inferred coordinates beyond that.
    """
    config = prepare_config(suite, config).model_copy(
        update={"callprobe_version": __version__}, deep=True,
    )
    started_at = datetime.now(timezone.utc).isoformat()

    records = list(recordings)
    if not records:
        raise ValueError("no recordings supplied")

    pad_order = {pad: index for index, pad in enumerate(config.pads)}
    task_order = {task.id: index for index, task in enumerate(suite.tasks)}
    task_by_id = {task.id: task for task in suite.tasks}
    in_scope = (
        set(config.selected_task_ids)
        if config.selected_task_ids is not None
        else set(task_by_id)
    )

    seen: set[tuple[str, int, int]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, RecordedCompletion):
            raise ValueError(f"recording {index} is not a RecordedCompletion")
        if not isinstance(record.completion, Completion):
            raise ValueError(f"recording {index} payload is not a Completion")
        _validate_completion(record.completion, index)
        _require_int(record.pad, f"{index} pad")
        _require_int(record.repeat, f"{index} repeat")
        if not isinstance(record.task_id, str):
            raise ValueError(f"recording {index} task id must be a string")
        if record.task_id not in task_by_id:
            raise ValueError(f"recording {index} refers to an unknown task")
        if record.task_id not in in_scope:
            raise ValueError(
                f"recording {index} refers to a task outside the current selection"
            )
        if record.pad not in pad_order:
            raise ValueError(f"recording {index} pad is not in the configured sweep")
        if not 0 <= record.repeat < config.repeats:
            raise ValueError(f"recording {index} repeat is outside the configured range")
        key = (record.task_id, record.pad, record.repeat)
        if key in seen:
            raise ValueError(f"recording {index} duplicates an earlier identity")
        seen.add(key)

    ordered = sorted(
        records,
        key=lambda record: (
            pad_order[record.pad], record.repeat, task_order[record.task_id],
        ),
    )

    results = []
    for record in ordered:
        task = task_by_id[record.task_id]
        bundle, _ = build_toolset(suite, task, record.pad, seed=record.repeat)
        results.append(score(
            task, bundle, record.completion,
            model=config.model, pad=record.pad, repeat=record.repeat,
        ))

    finished_at = datetime.now(timezone.utc).isoformat()
    return Run(
        config=config,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
    )
