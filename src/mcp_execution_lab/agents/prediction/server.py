from mcp.server.mcpserver import Context

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result, Rules
from .worker import execute


async def predict_data(
    job: str,
    dataset: FileRef,
    ctx: Context,
    target: str | None = None,
    time_column: str | None = None,
    rules: Rules | None = None,
    prediction_data: FileRef | None = None,
) -> Result:
    """Check linear numeric prediction, nearest-centroid labels, or a last-value forecast
    against a held-back reference score."""
    return await execute(
        run_client(ctx), job, dataset, target, time_column, rules or Rules(), prediction_data
    )


if __name__ == "__main__":
    serve("prediction", predict_data)
