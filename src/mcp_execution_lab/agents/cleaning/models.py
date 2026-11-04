from typing import Literal

from pydantic import Field, field_validator

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Choose only cleaning operations explicitly allowed by the supplied rules. Preserve "
    "identifiers and original data. Follow the order requested in the assigned job. "
    "For label_values use normalize_label; it matches supplied labels without regard to "
    "case and rejects other labels. Do not replace missing rules with inferred permission."
)


class Rules(Record):
    trim_columns: list[str] = Field(default_factory=list)
    fill_values: dict[str, str] = Field(default_factory=dict)
    replacements: dict[str, dict[str, str]] = Field(default_factory=dict)
    label_values: dict[str, list[str]] = Field(default_factory=dict)
    date_formats: dict[str, str] = Field(default_factory=dict)
    number_columns: list[str] = Field(
        default_factory=list,
        description="Columns allowed numeric parsing. Three-digit comma groups mean thousands; "
        "the decimal point is a period. Malformed grouping is rejected; blanks stay blank.",
    )
    remove_exact_duplicates: bool = False
    drop_missing_columns: list[str] = Field(default_factory=list)

    @field_validator("label_values")
    @classmethod
    def unambiguous_labels(cls, value):
        for labels in value.values():
            if not labels or any(not label or label != label.strip() for label in labels):
                raise ValueError("Permitted labels must be non-empty, trimmed strings.")
            if len({label.casefold() for label in labels}) != len(labels):
                raise ValueError("Permitted labels must be distinct without regard to case.")
        return value


class Operation(Record):
    action: Literal[
        "trim",
        "fill",
        "replace",
        "normalize_label",
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
