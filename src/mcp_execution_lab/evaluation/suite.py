"""Public questions and frozen input identities; no expected answers here."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..orchestration.models import OrchestrationError, Record, fingerprint


class Task(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    title: str
    files: list[str] = Field(min_length=1)
    query: str
    kind: Literal["table", "forecast", "clarification"] = "table"
    columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    tolerance: str = "0.005"
    require_chart: bool = False
    require_report: bool = False
    require_change_log: bool = False
    human_checks: list[str] = Field(default_factory=list)


class Suite:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        raw = json.loads((self.directory / "tasks.json").read_text(encoding="utf-8"))
        self.tasks = [Task.model_validate(item) for item in raw["tasks"]]
        if len({task.id for task in self.tasks}) != len(self.tasks):
            raise ValueError("Task IDs must be unique.")
        self.version = raw["version"]
        self.digest = fingerprint({"manifest": self.manifest, "tasks": raw})
        for name in self.manifest["files"]:
            self.path(name)
        for task in self.tasks:
            if not set(task.files) <= self.manifest["files"].keys():
                raise ValueError("A task names an unknown CSV.")
            if not set(task.numeric_columns) <= set(task.columns):
                raise ValueError("Numeric output columns must be declared.")

    def path(self, name):
        path = (self.directory / name).resolve()
        if path.parent != self.directory or path.suffix != ".csv":
            raise OrchestrationError("EVAL_SCOPE", "Suite inputs must be direct CSV children.")
        expected = self.manifest["files"].get(name)
        if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            raise OrchestrationError(
                "EVAL_FIXTURE_CHANGED", "A CSV differs from the suite manifest."
            )
        return path

    def task(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise ValueError("Unknown evaluation task: " + task_id)
