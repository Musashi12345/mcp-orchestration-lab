import asyncio

from ..common.models import Fact, NeedsInput
from ..common.operations import csv_bytes
from ..common.worker import choose, explain, run_job
from .models import Recipe, Result
from .operations import clean


async def execute(client, job, dataset, rules, profile=None):
    async def work():
        table = await client.table(dataset)
        if profile:
            prior = await client.json(profile)
            profiles = prior.get("details", {}).get("profiles", [])
            if not any(item["dataset_id"] == dataset.id for item in profiles):
                raise NeedsInput("The supplied profile belongs to another data version.")
        recipe = await choose(
            client,
            Recipe,
            {
                "job": job,
                "columns": table.columns,
                "sample": table.rows[:5],
                "rules": rules.model_dump(),
            },
        )
        await client.stage("accepted_recipe", recipe.model_dump())
        rows, changes, mapping, details = await asyncio.to_thread(clean, table, recipe, rules)
        await client.stage("cleaning_checked", details.model_dump())
        facts = [
            Fact(
                id="rows_before",
                label="Input rows",
                value=details.before_rows,
                sources=[dataset.id],
            ),
            Fact(
                id="rows_after", label="Output rows", value=details.after_rows, sources=[dataset.id]
            ),
            Fact(
                id="changed_cells",
                label="Changed cells",
                value=details.changed_cells,
                sources=[dataset.id],
            ),
        ]
        summary, warnings = await explain(client, job, facts, [])
        ref = await client.publish(csv_bytes(table.columns, rows), "csv") if changes else dataset
        checks = await client.publish(
            {
                "details": details.model_dump(),
                "facts": [fact.model_dump() for fact in facts],
                "source_rows": mapping,
                "input": dataset.model_dump(),
                "rules": rules.model_dump(),
            }
        )
        artifacts = [checks]
        if changes:
            artifacts.append(
                await client.publish(
                    csv_bytes(
                        ["source_row", "column", "old", "new", "operation", "reason", "removed"],
                        changes,
                    ),
                    "csv",
                )
            )
        return Result(
            summary=summary,
            datasets=[ref],
            artifacts=artifacts,
            facts=facts,
            details=details,
            warnings=warnings,
        )

    return await run_job(client, Result, work)
