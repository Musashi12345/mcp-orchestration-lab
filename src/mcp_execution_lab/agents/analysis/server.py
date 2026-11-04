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
    from one registered CSV. Numeric sums and means use Decimal internally; exported
    metrics are JSON integers or floating-point numbers, not exact Decimal JSON.
    Saves JSON calculation evidence and a CSV table with group-by columns followed by
    the recipe's named measures. With no grouping, the table has one row and only the
    named measure columns. State required filters and measure names in the assigned job.
    Returns registered artifact references and structured results; a requested chart
    adds a PNG artifact."""
    return await execute(run_client(ctx), job, datasets, definitions or Definitions())


if __name__ == "__main__":
    serve("data_analysis", analyze_data)
