from typing import Annotated

from mcp.server.mcpserver import Context
from pydantic import Field

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result
from .worker import execute


async def understand_data(
    job: str,
    datasets: Annotated[list[FileRef], Field(min_length=1, max_length=8)],
    ctx: Context,
    questions: list[str] | None = None,
) -> Result:
    """Explain registered CSVs, check missing/duplicate values and key candidates, preserving
    the data."""
    return await execute(run_client(ctx), job, datasets, questions or [])


if __name__ == "__main__":
    serve("data_understanding", understand_data)
