from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = "Choose relevant columns and checks. Meanings are hypotheses, not business facts."


class Recipe(Record):
    columns: list[str] = Field(default_factory=list)
    check_duplicates: bool = True
    key_columns: list[str] = Field(default_factory=list)
    column_meanings: dict[str, str] = Field(default_factory=dict)
    question: str = ""


class ColumnProfile(Record):
    name: str
    missing: int
    distinct: int
    observed_types: dict[str, int]
    minimum: str | None = None
    maximum: str | None = None


class FileProfile(Record):
    dataset_id: str
    row_count: int
    columns: list[ColumnProfile]
    duplicate_rows: int | None = None


class Details(Record):
    profiles: list[FileProfile] = Field(default_factory=list)
    key_checks: list[dict[str, str | int | bool]] = Field(default_factory=list)
    possible_meanings: dict[str, str] = Field(default_factory=dict)
    scope: str = "full_file"


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
