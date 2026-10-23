import asyncio

from ..common.worker import choose, explain, run_job
from .models import Recipe, Result
from .operations import inspect_tables


async def execute(client, job, datasets, questions):
    async def work():
        tables = [await client.table(ref) for ref in datasets]
        context = {
            "job": job,
            "questions": questions,
            "files": [
                {
                    "id": table.ref.id,
                    "columns": table.columns,
                    "rows": len(table.rows),
                    "sample": table.rows[:5],
                }
                for table in tables
            ],
        }
        recipe = await choose(client, Recipe, context)
        await client.stage("accepted_recipe", recipe.model_dump())
        details, facts = await asyncio.to_thread(inspect_tables, tables, recipe)
        await client.stage("profile_calculated", details.model_dump())
        summary, warnings = await explain(client, job, facts, [])
        profile = await client.publish(
            {"details": details.model_dump(), "facts": [fact.model_dump() for fact in facts]}
        )
        return Result(
            summary=summary, facts=facts, details=details, artifacts=[profile], warnings=warnings
        )

    return await run_job(client, Result, work)
