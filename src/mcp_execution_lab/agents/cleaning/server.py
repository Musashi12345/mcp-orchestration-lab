from mcp.server.mcpserver import Context

from ...orchestration.models import FileRef
from ..common.server import run_client, serve
from .models import Result, Rules
from .worker import execute


async def clean_data(
    job: str,
    dataset: FileRef,
    ctx: Context,
    rules: Rules,
    profile: FileRef | None = None,
) -> Result:
    """Create a cleaned CSV copy and a complete change log while preserving originals.

    Supply explicit rules grounded in the assigned job. trim_columns authorizes trimming;
    number_columns authorizes numeric parsing without filling blanks. Three-digit comma
    groups mean thousands, with a period decimal point; malformed grouping is rejected.
    label_values lists
    permitted labels for case-insensitive normalization and rejects unexpected labels.
    drop_missing_columns authorizes missing-value removal and remove_exact_duplicates
    authorizes keeping the first identical row. replacements, fill_values and date_formats
    authorize only their declared operations. Preserve identifier text. The chosen recipe
    must follow the job's requested operation order. Omitted or empty rules do not
    authorize requested cleaning; prose alone does not replace the rules argument.
    """
    return await execute(run_client(ctx), job, dataset, rules, profile)


if __name__ == "__main__":
    serve("data_cleaning", clean_data)
