"""Core data model for suites, tasks, and results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CheckOp = Literal[
    "eq", "neq", "in", "contains", "gte", "lte", "matches", "exists", "absent"
]

Category = Literal["select", "abstain", "args", "depth", "sequence"]


class ArgCheck(BaseModel):
    """A semantic assertion about one argument value.

    `path` is a dotted path into the arguments object, e.g. "filters.status".
    """

    path: str
    op: CheckOp
    value: Any = None
    note: str | None = None


class Expectation(BaseModel):
    type: Literal["call", "no_call"]
    tool: str | None = None
    # Exact match required on these keys only. Extra keys are ignored here and
    # judged by schema validity instead.
    args: dict[str, Any] = Field(default_factory=dict)
    arg_checks: list[ArgCheck] = Field(default_factory=list)
    # Tools that are also defensible choices. Counted as correct selection.
    also_acceptable: list[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    category: Category
    bundle: str
    messages: list[dict[str, Any]]
    expect: Expectation
    tags: list[str] = Field(default_factory=list)
    # Distractors that must never be padded in, because they would make the
    # expected answer wrong. An abstention task stops being one the moment
    # padding hands the model a tool that legitimately applies.
    exclude_distractors: list[str] = Field(default_factory=list)
    # Number of prior turns in `messages`. Filled in by the loader.
    depth: int = 0


class Tool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Bundle(BaseModel):
    name: str
    tools: list[Tool]

    def by_name(self, name: str) -> Tool | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


class Suite(BaseModel):
    name: str
    bundles: dict[str, Bundle]
    distractors: list[Tool] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)


class Call(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str = ""
    parse_error: str | None = None


class TaskResult(BaseModel):
    task_id: str
    category: Category
    model: str
    pad: int
    repeat: int

    selection_ok: bool
    schema_ok: bool
    args_ok: bool
    success: bool

    schema_ok_lenient: bool = False
    args_ok_lenient: bool = False
    success_lenient: bool = False
    type_coerced: bool = False

    called: str | None = None
    expected: str | None = None
    failures: list[str] = Field(default_factory=list)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    # What the model said instead of calling a tool. Kept on failures so a
    # parsing bug is distinguishable from a model that declined to act.
    response_text: str = ""
    # True when the server stopped on the token limit before finishing.
    truncated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class RunConfig(BaseModel):
    model: str
    endpoint: str
    suite: str
    pads: list[int]
    repeats: int
    temperature: float
    max_tokens: int
    quantization: str | None = None
    notes: str | None = None


class Run(BaseModel):
    config: RunConfig
    started_at: str
    finished_at: str | None = None
    results: list[TaskResult] = Field(default_factory=list)
