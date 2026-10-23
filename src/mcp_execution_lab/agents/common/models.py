"""Public worker results and bounded choices, shared by all transports."""

from typing import Any, Literal

from pydantic import Field

from ...orchestration.models import FileRef, Record


class Fact(Record):
    id: str
    label: str
    value: Any
    unit: str = ""
    sources: list[str] = Field(default_factory=list)


class AgentResult(Record):
    contract_version: str = "1"
    outcome: Literal["COMPLETED", "NEEDS_INPUT", "UNSUPPORTED", "FAILED"] = "COMPLETED"
    summary: str
    datasets: list[FileRef] = Field(default_factory=list)
    artifacts: list[FileRef] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    error: dict[str, str] | None = None
    usage_record_ids: list[str] = Field(default_factory=list)


class Explanation(Record):
    text: str = Field(description="Explain checked facts. Insert numbers only as {{fact:ID}}.")
    fact_ids: list[str]
    warnings: list[str] = Field(default_factory=list)


class Refusal(Record):
    question: str = ""


class Table(Record):
    ref: FileRef
    columns: list[str]
    rows: list[dict[str, str]]


class NeedsInput(ValueError):
    """The request needs a public clarification, not an invented business assumption."""


class Unsupported(ValueError):
    """A bounded operation cannot perform this particular request."""
