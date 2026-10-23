from typing import Any, Literal

from pydantic import Field

from ...orchestration.models import Record
from ..common.models import AgentResult

INSTRUCTIONS = (
    "Select a supported method and target from the assigned job. Keep the fixed split and "
    "allowed features. Never claim future accuracy from training scores."
)


class Rules(Record):
    seed: int = Field(default=0, ge=0, le=2147483647)
    test_fraction: float = Field(default=0.2, ge=0.1, le=0.5)
    minimum_rows: int = Field(default=10, ge=6, le=100000)
    excluded_columns: list[str] = Field(default_factory=list)
    allowed_features: list[str] = Field(default_factory=list)
    missing_policy: Literal["error", "drop"] = "error"


class Recipe(Record):
    method: Literal["linear_regression", "nearest_centroid", "last_value"]
    target: str
    features: list[str] = Field(default_factory=list, max_length=16)
    time_column: str = ""
    horizon: int = Field(default=1, ge=1, le=12)
    question: str = ""


class Details(Record):
    method: str = ""
    target: str = ""
    features: list[str] = Field(default_factory=list)
    training_rows: int = 0
    test_rows: int = 0
    excluded_rows: int = 0
    seed: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    model_parameters: dict[str, Any] = Field(default_factory=dict)
    predictions_created: int = 0


class Result(AgentResult):
    details: Details = Field(default_factory=Details)
