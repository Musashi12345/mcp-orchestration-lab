"""Explicit server/model settings; database credentials stay in the local environment."""

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import Field

from .models import Limits, OrchestrationError, Record, ServerConfig, TaskRules


class ModelConfig(Record):
    provider: Literal["codex", "command"] = "codex"
    model_id: str | None = None
    reasoning_effort: str = "low"
    command: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=90, gt=0)


class Settings(Record):
    servers: list[ServerConfig] = Field(min_length=1)
    model: ModelConfig = Field(default_factory=ModelConfig)
    limits: Limits = Field(default_factory=Limits)
    task_rules: TaskRules = Field(default_factory=TaskRules)


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def local_environment(root: Path):
    load_dotenv(root / ".env", override=False)
    url = os.environ.get("MCP_LAB_DATABASE_URL", "")
    if not url or "YOUR_" in url:
        raise OrchestrationError(
            "DATABASE_CONFIG", "Copy .env.example to .env and set MCP_LAB_DATABASE_URL."
        )
    if not url.startswith("postgresql+psycopg://"):
        raise OrchestrationError("DATABASE_CONFIG", "Use a postgresql+psycopg:// connection URL.")
    data_root = Path(os.environ.get("MCP_LAB_DATA_ROOT", "runs/data_analysis"))
    data_root = (root / data_root).resolve()
    os.environ["MCP_LAB_DATA_ROOT"] = str(data_root)
    return url, data_root
