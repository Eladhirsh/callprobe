"""Explicit YAML defaults for `callprobe run --config FILE.yaml`.

A config file only supplies *defaults* for experiment settings. It is never
discovered automatically, never stores credentials, targeting, resume, or
gating, and any CLI flag the caller passes explicitly always wins over it.
`suite`/`out` values that come from the file resolve relative to the config
file's own directory, not the process's working directory, so a config
behaves the same no matter where `callprobe` is invoked from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

# Keys accepted in this version. Anything else (api keys, targeting, resume,
# gating, format/quiet, ...) is rejected rather than silently ignored.
ALLOWED_KEYS = {
    "model", "endpoint", "suite", "pads", "repeats", "temperature",
    "max_tokens", "quant", "notes", "retries", "concurrency", "out",
}

_STR_FIELDS = ("model", "endpoint", "suite", "quant", "notes", "out")
_POSITIVE_INT_FIELDS = ("repeats", "max_tokens", "concurrency")


class RunFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    endpoint: str | None = None
    suite: str | None = None
    pads: list[int] | None = None
    repeats: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    quant: str | None = None
    notes: str | None = None
    retries: int | None = None
    concurrency: int | None = None
    out: str | None = None

    @field_validator(*_STR_FIELDS, mode="before")
    @classmethod
    def _check_str(cls, value: Any, info) -> Any:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string")
        if info.field_name in ("model", "endpoint", "suite", "out") and not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("repeats", "max_tokens", "retries", "concurrency", mode="before")
    @classmethod
    def _check_int(cls, value: Any, info) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{info.field_name} must be an integer")
        return value

    @field_validator(*_POSITIVE_INT_FIELDS)
    @classmethod
    def _check_positive(cls, value: int | None, info) -> int | None:
        if value is not None and value < 1:
            raise ValueError(f"{info.field_name} must be positive")
        return value

    @field_validator("retries")
    @classmethod
    def _check_nonnegative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("retries must be nonnegative")
        return value

    @field_validator("temperature", mode="before")
    @classmethod
    def _check_temperature(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("temperature must be a number")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError("temperature must be finite") from None
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("temperature must be finite")
        return value

    @field_validator("pads", mode="before")
    @classmethod
    def _check_pads(cls, value: Any) -> Any:
        if not isinstance(value, list) or not value:
            raise ValueError("pads must be a nonempty list of integers")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError("pads must contain only integers")
            if item < 0:
                raise ValueError("pads must be nonnegative")
        if len(set(value)) != len(value):
            raise ValueError("pads must not contain duplicate values")
        return list(value)


class _StrictLoader(yaml.SafeLoader):
    """Rejects duplicate mapping keys instead of silently keeping the last one."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
            raise ValueError("--config: mapping keys must be strings")
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"--config: duplicate key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _summarize_errors(exc: ValidationError) -> str:
    """Field names and messages only; never the offending value itself."""
    parts = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "config"
        parts.append(f"{field}: {error['msg']}")
    return "; ".join(parts)


def load_run_config(path: str) -> tuple[RunFileConfig, Path]:
    """Parse and fully validate a `--config` file.

    Returns the validated config and the directory it lives in, so callers
    can resolve `suite`/`out` relative to the config file rather than cwd.
    Raises ValueError on any problem; never echoes configured values.
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"--config file not found: {path}") from None
    except IsADirectoryError:
        raise ValueError(f"--config must be a file, not a directory: {path}") from None
    try:
        data = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ValueError(f"--config: invalid YAML syntax{where}") from None
    if data is None or not isinstance(data, dict):
        raise ValueError("--config: file must contain a YAML mapping")
    unknown = sorted(set(data) - ALLOWED_KEYS)
    if unknown:
        raise ValueError("--config: unknown field(s): " + ", ".join(unknown))
    try:
        parsed = RunFileConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError("--config: " + _summarize_errors(exc)) from None
    return parsed, config_path.resolve().parent
