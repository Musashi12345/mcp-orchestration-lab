from typing import Annotated

from mcp.server.mcpserver import Context
from pydantic import Field

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result, Rules
from .worker import execute


async def combine_data(
    job: str,
    datasets: Annotated[list[FileRef], Field(min_length=2, max_length=8)],
    ctx: Context,
    rules: Rules | None = None,
) -> Result:
    """Join or append registered CSVs using checked matching rules, preserving source rows
    and match counts."""
    return await execute(run_client(ctx), job, datasets, rules or Rules())


if __name__ == "__main__":
    serve("data_combining", combine_data)
