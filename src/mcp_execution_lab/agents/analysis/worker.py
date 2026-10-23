import asyncio

from ..common.models import NeedsInput
from ..common.operations import csv_bytes
from ..common.worker import choose, explain, run_job
from .models import Recipe, Result
from .operations import analyze, chart


async def execute(client, job, datasets, definitions):
    async def work():
        if len(datasets) != 1:
            raise NeedsInput(
                "Supply one analysis dataset; combining files must be an explicit planned task."
            )
        table = await client.table(datasets[0])
        recipe = await choose(
            client,
            Recipe,
            {
                "job": job,
                "columns": table.columns,
                "sample": table.rows[:5],
                "definitions": definitions.model_dump(),
            },
        )
        await client.stage("accepted_recipe", recipe.model_dump())
        details, facts, warnings = await asyncio.to_thread(analyze, table, recipe, definitions)
        await client.stage("calculations_checked", details.model_dump())
        image = await asyncio.to_thread(chart, details, definitions)
        summary, notes = await explain(client, job, facts, warnings)
        findings = await client.publish(
            {
                "facts": [f.model_dump() for f in facts],
                "details": details.model_dump(),
                "warnings": warnings,
                "inputs": [ref.model_dump() for ref in datasets],
            }
        )
        rows = [group.group | group.metrics for group in details.groups]
        columns = recipe.group_by + [m.name for m in recipe.measures]
        artifacts = [findings, await client.publish(csv_bytes(columns, rows), "csv")]
        if image:
            artifacts.append(await client.publish(image, "png"))
        return Result(
            summary=summary,
            facts=facts,
            artifacts=artifacts,
            details=details,
            warnings=warnings + notes,
        )

    return await run_job(client, Result, work)
