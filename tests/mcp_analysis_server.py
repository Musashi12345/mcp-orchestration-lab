"""Deterministic integration-test service, never presented as an LLM agent."""

import asyncio
import csv
import hashlib
import os
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import MCPServer

from mcp_execution_lab.orchestration.models import FileRef

server = MCPServer("analysis-test-fixture", version="1.0")
safe = types.ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def rows(reference):
    ref = FileRef.model_validate(reference)
    root = Path(os.environ["MCP_LAB_DATA_ROOT"]).resolve()
    path = (root / ref.run_id / (ref.id + ".csv")).resolve()
    if not path.is_relative_to(root) or ref.kind != "csv":
        raise ValueError("Invalid registered CSV reference")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref.sha256:
        raise ValueError("Dataset changed")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@server.tool(annotations=safe)
def profile(dataset: dict[str, Any]) -> dict[str, Any]:
    """Count the records in the supplied registered CSV without changing it."""
    values = rows(dataset)
    return {"row_count": len(values), "columns": list(values[0]) if values else []}


@server.tool(annotations=safe)
def sum_column(dataset: dict[str, Any], column: str) -> dict[str, Any]:
    """Calculate a numeric column's sum from the supplied registered CSV."""
    values = rows(dataset)
    return {"row_count": len(values), "total": sum(float(row[column]) for row in values)}


@server.tool(annotations=safe)
def present(summary: dict[str, Any]) -> dict[str, Any]:
    """Return supplied computed findings as an answer record without changing numbers."""
    return {"answer": summary}


@server.tool(annotations=safe)
async def echo(value: dict[str, Any], delay: float = 0) -> dict[str, Any]:
    """Return the supplied value after a bounded test delay."""
    await asyncio.sleep(min(2, max(0, delay)))
    return value


@server.tool(annotations=safe)
def fail(message: str) -> dict[str, Any]:
    """Return a deliberate test failure."""
    raise ValueError(message)


@server.tool(annotations=safe)
def unrelated() -> dict[str, Any]:
    """Return a marker for a tool that many tasks do not need."""
    return {"unused": True}


if __name__ == "__main__":
    server.run(transport="stdio")
