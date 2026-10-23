from typing import Annotated

from mcp.server.mcpserver import Context
from pydantic import Field

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Definitions, Result
from .worker import execute


async def analyze_data(
    job: str,
    datasets: Annotated[list[FileRef], Field(min_length=1, max_length=1)],
    ctx: Context,
    definitions: Definitions | None = None,
) -> Result:
    """Calculate checked filters, grouped totals, averages, changes, correlations and charts
    from one registered CSV."""
    return await execute(run_client(ctx), job, datasets, definitions or Definitions())


if __name__ == "__main__":
    serve("data_analysis", analyze_data)
