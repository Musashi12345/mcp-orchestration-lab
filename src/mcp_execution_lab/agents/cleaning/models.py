from typing import Literal

from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Choose only cleaning operations explicitly allowed by the supplied rules. Preserve "
    "identifiers and original data."
)


class Rules(Record):
    trim_columns: list[str] = Field(default_factory=list)
    fill_values: dict[str, str] = Field(default_factory=dict)
    replacements: dict[str, dict[str, str]] = Field(default_factory=dict)
    date_formats: dict[str, str] = Field(default_factory=dict)
    number_columns: list[str] = Field(default_factory=list)
    remove_exact_duplicates: bool = False
    drop_missing_columns: list[str] = Field(default_factory=list)


class Operation(Record):
    action: Literal[
        "trim",
        "fill",
        "replace",
        "parse_date",
        "convert_number",
        "remove_exact_duplicates",
        "drop_missing",
    ]
    column: str = ""
    reason: str = Field(min_length=1)


class Recipe(Record):
    operations: list[Operation] = Field(default_factory=list, max_length=64)
    question: str = ""


class Details(Record):
    before_rows: int = 0
    after_rows: int = 0
    changed_cells: int = 0
    removed_rows: int = 0
    recipe: list[Operation] = Field(default_factory=list)


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
