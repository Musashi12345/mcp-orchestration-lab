from typing import Literal

from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Choose join or append from the job. Do not guess business relationships. Specify exact "
    "common keys, row retention and expected key multiplicity."
)


class Rules(Record):
    keys: list[str] = Field(default_factory=list)
    join_type: Literal["inner", "left", "outer"] | None = None
    relationship: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = "one_to_one"
    allow_many_to_many: bool = False
    max_output_rows: int = Field(default=100000, ge=1, le=100000)


class Recipe(Record):
    operation: Literal["join", "append"]
    keys: list[str] = Field(default_factory=list)
    join_type: Literal["inner", "left", "outer"] = "inner"
    relationship: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = "one_to_one"
    question: str = ""


class Details(Record):
    operation: str = ""
    output_rows: int = 0
    checks: list[dict[str, int | str]] = Field(default_factory=list)
    column_mapping: list[dict[str, str]] = Field(default_factory=list)


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
