from typing import Annotated

from mcp.server.mcpserver import Context
from pydantic import Field

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result, Style
from .worker import execute


async def create_report(
    job: str,
    evidence: Annotated[list[FileRef], Field(min_length=1, max_length=8)],
    ctx: Context,
    charts: list[FileRef] | None = None,
    style: Style | None = None,
) -> Result:
    """Write a plain-English Markdown report from registered checked facts and PNG charts,
    retaining claim sources and limits."""
    return await execute(run_client(ctx), job, evidence, charts or [], style or Style())


if __name__ == "__main__":
    serve("report", create_report)
