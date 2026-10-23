"""Public planning records; no domain-specific tools or workflow order."""

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrchestrationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ServerConfig(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    command: str = ""
    transport: Literal["stdio", "streamable-http"] = "stdio"
    url: str | None = None
    args: list[str] = Field(default_factory=list)
    env_names: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def connection(self):
        if self.transport == "stdio" and (not self.command or self.url):
            raise ValueError("A stdio server needs a command and no URL.")
        if self.transport == "streamable-http":
            parsed = urlparse(self.url or "")
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("MCP HTTP servers must use a plain loopback HTTP URL.")
        return self


class Limits(Record):
    concurrency: int = Field(default=2, ge=1, le=16)
    max_steps: int = Field(default=32, ge=1, le=128)
    max_model_calls: int = Field(default=16, ge=1)
    max_observed_tokens: int = Field(default=60000, ge=1)
    max_tool_attempts: int = Field(default=64, ge=1)
    correction_attempts: int = Field(default=1, ge=0, le=3)
    transport_retries: int = Field(default=1, ge=0, le=3)
    run_seconds: float = Field(default=600, gt=0)
    tool_seconds: float = Field(default=120, gt=0)
    max_file_bytes: int = Field(default=104857600, ge=1)
    max_result_bytes: int = Field(default=2097152, ge=1)
    sample_rows: int = Field(default=5, ge=0, le=20)
    max_prompt_chars: int = Field(default=100000, ge=1000)
    worker_model_calls: int = Field(default=3, ge=1, le=8)
    worker_max_rows: int = Field(default=100000, ge=1, le=1000000)


class ReviewRule(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    after_completed_steps: int = Field(ge=1)


class TaskRules(Record):
    reviews: list[ReviewRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def review_order(self):
        if self.reviews and (
            len(self.reviews) != 2
            or len({point.id for point in self.reviews}) != 2
            or self.reviews[0].after_completed_steps >= self.reviews[1].after_completed_steps
        ):
            raise ValueError("A task must declare two distinct, increasing review points.")
        return self


class ToolDefinition(Record):
    server: str
    name: str
    key: str = ""
    description: str
    plain_description: str
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)
    raw_definition: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def identify(cls, value):
        if isinstance(value, dict) and "server" in value and "name" in value:
            expected = value["server"] + "/" + value["name"]
            if value.get("key", expected) != expected:
                raise ValueError("Tool key must match its server and name.")
            return value | {"key": expected}
        return value


class ToolCache(Record):
    tools: list[ToolDefinition]
    servers: dict[str, Any] = Field(default_factory=dict)

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))

    def lookup(self, server: str, name: str) -> ToolDefinition:
        for tool in self.tools:
            if (tool.server, tool.name) == (server, name):
                return tool
        raise OrchestrationError("UNKNOWN_TOOL", f"Unknown discovered tool: {server}/{name}")


class FileRef(Record):
    id: str
    run_id: str
    kind: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Dataset(Record):
    ref: FileRef
    filename: str
    row_count: int
    columns: list[str]
    missing_counts: dict[str, int]
    observed_types: dict[str, list[str]] = Field(default_factory=dict)
    sample: list[dict[str, str]]
    encoding: str
    delimiter: str


class MainTask(Record):
    goal: str = Field(min_length=1)
    dataset_ids: list[str]
    required_outputs: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class Selection(Record):
    tool_keys: list[str] = Field(
        description="Exact key values copied from discovered tool entries."
    )
    reasons: list[str]
    missing_capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def one_reason_per_tool(self):
        if len(self.tool_keys) != len(self.reasons):
            raise ValueError("Each selected tool needs its own short reason.")
        return self


class Subtask(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    tool_key: str = Field(description="The selected tool entry's exact key, including its server.")
    job: str = Field(min_length=1)
    expected_outputs: list[str] = Field(min_length=1)


class Breakdown(Record):
    selection: Selection
    subtasks: list[Subtask]


class Binding(Record):
    kind: Literal[
        "literal", "dataset", "step", "snapshot", "task", "choice", "list", "object", "status"
    ]
    key: str = ""
    path: list[str | int] = Field(default_factory=list)
    value: Any = None
    condition: "Condition | None" = None
    when_true: "Binding | None" = None
    when_false: "Binding | None" = None
    items: list["Binding"] = Field(default_factory=list)
    fields: dict[str, "Binding"] = Field(default_factory=dict)

    @model_validator(mode="after")
    def well_formed(self):
        if self.kind == "choice":
            if self.condition is None or self.when_true is None or self.when_false is None:
                raise ValueError("A choice requires a condition and both alternatives.")
        elif any(part is not None for part in (self.condition, self.when_true, self.when_false)):
            raise ValueError("Only a choice can contain conditional alternatives.")
        if self.items and self.kind != "list" or self.fields and self.kind != "object":
            raise ValueError("Only list/object bindings accept items/fields.")
        if self.kind in {"dataset", "step", "snapshot", "status"} and not self.key:
            raise ValueError("Reference bindings require a key.")
        if self.kind != "literal" and self.value is not None:
            raise ValueError("Only literal bindings contain inline values.")
        return self


class Condition(Record):
    left: Binding
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte"]
    right: Binding


Binding.model_rebuild()
Condition.model_rebuild()


class Step(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    subtask_id: str
    server: str
    tool: str
    depends_on: list[str] = Field(default_factory=list)
    arguments: dict[str, Binding]
    condition: Condition | None = None
    dependency_policy: Literal["success", "settled"] = "success"


class Plan(Record):
    steps: list[Step] = Field(default_factory=list)
    outputs: dict[str, Binding] = Field(min_length=1)


class ReviewDecision(Record):
    decision: Literal["KEEP", "REVISE", "STOP"]
    reason: str
    breakdown: Breakdown | None = None
    replacement: Plan | None = None

    @model_validator(mode="after")
    def replacement_rules(self):
        revised = self.decision == "REVISE"
        if revised != (self.replacement is not None and self.breakdown is not None):
            raise ValueError("REVISE requires a replacement and its breakdown.")
        if not revised and (self.replacement is not None or self.breakdown is not None):
            raise ValueError("KEEP and STOP cannot contain replacement work.")
        return self


class Handoff(Record):
    run_id: str
    mode: Literal["D1", "D2"]
    task: MainTask
    datasets: list[Dataset]
    cache: ToolCache
    cache_record: str
    task_record: str
    breakdown: Breakdown
    plan: Plan
    plan_record: str
    version: int = 1
    rules: TaskRules


class StructuredPayload(Record):
    """Fixed outer schema for providers that disallow arbitrary JSON properties."""

    content_json: str
