import asyncio

from ..common.models import Fact
from ..common.operations import csv_bytes
from ..common.worker import choose, explain, run_job
from .models import Recipe, Result
from .operations import combine


async def execute(client, job, datasets, rules):
    async def work():
        tables = [await client.table(ref) for ref in datasets]
        recipe = await choose(
            client,
            Recipe,
            {
                "job": job,
                "rules": rules.model_dump(),
                "files": [
                    {"id": t.ref.id, "columns": t.columns, "sample": t.rows[:5]} for t in tables
                ],
            },
        )
        await client.stage("accepted_recipe", recipe.model_dump())
        columns, rows, mapping, details = await asyncio.to_thread(combine, tables, recipe, rules)
        await client.stage("combination_checked", details.model_dump())
        facts = [
            Fact(
                id="output_rows",
                label="Combined rows",
                value=len(rows),
                sources=[ref.id for ref in datasets],
            )
        ]
        summary, warnings = await explain(client, job, facts, [])
        combined = await client.publish(csv_bytes(columns, rows), "csv")
        checks = await client.publish(
            {
                "recipe": recipe.model_dump(),
                "details": details.model_dump(),
                "source_rows": mapping,
                "facts": [fact.model_dump() for fact in facts],
            }
        )
        return Result(
            summary=summary,
            datasets=[combined],
            artifacts=[checks],
            facts=facts,
            details=details,
            warnings=warnings,
        )

    return await run_job(client, Result, work)
