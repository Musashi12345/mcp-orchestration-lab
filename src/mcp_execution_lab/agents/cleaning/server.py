from mcp.server.mcpserver import Context

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result, Rules
from .worker import execute


async def clean_data(
    job: str,
    dataset: FileRef,
    ctx: Context,
    rules: Rules | None = None,
    profile: FileRef | None = None,
) -> Result:
    """Create a checked cleaned CSV copy using explicit permitted rules, preserving the
    original and recording every change."""
    return await execute(run_client(ctx), job, dataset, rules or Rules(), profile)


if __name__ == "__main__":
    serve("data_cleaning", clean_data)
