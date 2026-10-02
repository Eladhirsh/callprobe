"""Load offline JSON v1 recording documents into typed inputs for scoring.

The document carries exactly what the caller observed from their own model
run — model label, pad/repeat coordinates, and completion evidence. This
module validates the shape with strict private Pydantic models and returns
a RunConfig plus a list of RecordedCompletion. It never calls a model, never
rescans the suite, and never infers generation settings that the caller did
not record. Diagnostics are generic ValueErrors that never echo the caller's
field names, keys, or values; filesystem errors propagate; invalid encodings use a generic diagnostic.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .client import Completion
from .models import Call, RunConfig
from .recordings import RecordedCompletion

_ENDPOINT = "recorded://local"


class _DuplicateKey(Exception):
    """Raised from the JSON pairs hook on any depth of duplicate keys."""


class _InvalidNumber(Exception):
    """Raised for NaN/Infinity tokens and for float literals that overflow."""


def _object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey()
        seen.add(key)
        out[key] = value
    return out


def _parse_constant(_name: str) -> Any:
    raise _InvalidNumber()


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise _InvalidNumber()
    return value


def _finite_nonneg_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError("must be finite") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError("must be finite and nonnegative")
    return number


class _Call(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    raw_arguments: str = ""
    parse_error: str | None = None


class _Completion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    calls: list[_Call] = Field(default_factory=list)
    content: str = ""
    reasoning: str = ""
    error: str | None = None
    finish_reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0

    @field_validator("prompt_tokens", "completion_tokens")
    @classmethod
    def _nonneg_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be nonnegative")
        return value

    @field_validator("latency_ms", mode="before")
    @classmethod
    def _latency(cls, value: Any) -> float:
        return _finite_nonneg_number(value)


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: str
    pad: int = 0
    repeat: int = 0
    completion: _Completion

    @field_validator("task_id")
    @classmethod
    def _nonempty_task_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("pad", "repeat")
    @classmethod
    def _nonneg(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be nonnegative")
        return value


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model: str
    pads: list[int]
    repeats: int
    temperature: float
    max_tokens: int
    quantization: str | None = None
    selected_task_ids: list[str] | None = None

    @field_validator("model")
    @classmethod
    def _nonempty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("pads")
    @classmethod
    def _pads(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("must not be empty")
        if any(item < 0 for item in value):
            raise ValueError("must be nonnegative")
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return list(value)

    @field_validator("repeats", "max_tokens")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be positive")
        return value

    @field_validator("temperature", mode="before")
    @classmethod
    def _temperature(cls, value: Any) -> float:
        return _finite_nonneg_number(value)

    @field_validator("selected_task_ids")
    @classmethod
    def _selected(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("must not be empty")
        if any(not item for item in value):
            raise ValueError("must contain only nonempty strings")
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return list(value)


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int
    config: _ConfigModel
    records: list[_Record]

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported schema version")
        return value

    @field_validator("records")
    @classmethod
    def _nonempty_records(cls, value: list[_Record]) -> list[_Record]:
        if not value:
            raise ValueError("must not be empty")
        return value


def read_recordings(
    path: str | Path, *, suite_label: str,
) -> tuple[RunConfig, list[RecordedCompletion]]:
    """Parse an offline v1 recording file into a RunConfig and recordings.

    The file is read once as UTF-8 and parsed with hooks that reject
    duplicate keys at any depth and nonfinite or overflowing numbers
    anywhere in the document (including nested tool arguments). Scoring
    is deliberately out of scope: the caller feeds the returned
    recordings into the existing scorer when they want results.
    """
    try:
        source = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("recording document must be UTF-8") from None
    try:
        document = json.loads(
            source,
            object_pairs_hook=_object_pairs_hook,
            parse_constant=_parse_constant,
            parse_float=_parse_float,
        )
    except _DuplicateKey:
        raise ValueError("recording document contains duplicate keys") from None
    except _InvalidNumber:
        raise ValueError(
            "recording document must not contain nonfinite or overflowing numbers"
        ) from None
    except (ValueError, RecursionError):
        raise ValueError("recording document is not valid JSON") from None

    if not isinstance(document, dict):
        raise ValueError("recording document must be a JSON object")

    try:
        parsed = _Document.model_validate(document)
    except ValidationError:
        raise ValueError("recording document failed schema validation") from None

    config = RunConfig(
        model=parsed.config.model,
        endpoint=_ENDPOINT,
        suite=suite_label,
        pads=list(parsed.config.pads),
        repeats=parsed.config.repeats,
        temperature=parsed.config.temperature,
        max_tokens=parsed.config.max_tokens,
        quantization=parsed.config.quantization,
        selected_task_ids=(
            list(parsed.config.selected_task_ids)
            if parsed.config.selected_task_ids is not None
            else None
        ),
    )

    records: list[RecordedCompletion] = []
    for record in parsed.records:
        calls = [
            Call(
                id=call.id,
                name=call.name,
                arguments=dict(call.arguments),
                raw_arguments=call.raw_arguments,
                parse_error=call.parse_error,
            )
            for call in record.completion.calls
        ]
        completion = Completion(
            calls=calls,
            content=record.completion.content,
            prompt_tokens=record.completion.prompt_tokens,
            completion_tokens=record.completion.completion_tokens,
            latency_ms=record.completion.latency_ms,
            error=record.completion.error,
            finish_reason=record.completion.finish_reason,
            reasoning=record.completion.reasoning,
        )
        records.append(RecordedCompletion(
            task_id=record.task_id,
            completion=completion,
            pad=record.pad,
            repeat=record.repeat,
        ))

    return config, records
