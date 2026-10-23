from typing import Literal

from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Choose checked filters, grouped measures, comparisons or correlations needed for the "
    "job. Do not infer causes. Ask when metric meaning is unclear."
)


class Filter(Record):
    column: str
    operation: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "missing"]
    value: str = ""
    values: list[str] = Field(default_factory=list, max_length=1000)


class Measure(Record):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    operation: Literal["count", "sum", "mean", "min", "max"]
    column: str = ""


class Comparison(Record):
    before: str
    after: str
    measure: str


class Definitions(Record):
    date_formats: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Recipe(Record):
    filters: list[Filter] = Field(default_factory=list, max_length=32)
    group_by: list[str] = Field(default_factory=list, max_length=3)
    measures: list[Measure] = Field(
        default_factory=lambda: [Measure(name="count", operation="count")],
        min_length=1,
        max_length=16,
    )
    time_column: str = ""
    period: Literal["day", "month", "year"] = "month"
    comparison: Comparison | None = None
    correlation_columns: list[str] = Field(default_factory=list, max_length=2)
    chart_metric: str = ""
    chart_kind: Literal["bar", "line"] = "bar"
    question: str = ""


class GroupResult(Record):
    group: dict[str, str]
    metrics: dict[str, int | float | None]
    valid_counts: dict[str, int]
    missing_counts: dict[str, int]


class Details(Record):
    rows_used: int = 0
    rows_excluded: int = 0
    groups: list[GroupResult] = Field(default_factory=list)
    comparison: dict[str, int | float | str | None] = Field(default_factory=dict)
    correlation: float | None = None
    correlation_rows: int = 0
    recipe: Recipe | None = None


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
