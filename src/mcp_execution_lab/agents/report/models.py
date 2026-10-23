from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Write from supplied evidence only. Every numeric claim must use {{fact:ID}} and each "
    "section must cite its fact IDs. Preserve warnings and contradictions."
)


class Style(Record):
    audience: str = "General reader"
    language: str = "Simple English"
    max_characters: int = Field(default=20000, ge=100, le=100000)


class Section(Record):
    title: str
    paragraphs: list[str] = Field(min_length=1, max_length=12)
    fact_ids: list[str]


class Recipe(Record):
    title: str
    sections: list[Section] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=32)
    question: str = ""


class Details(Record):
    title: str = ""
    claim_sources: list[dict[str, str | list[str]]] = Field(default_factory=list)
    input_evidence_ids: list[str] = Field(default_factory=list)
    character_count: int = 0


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
