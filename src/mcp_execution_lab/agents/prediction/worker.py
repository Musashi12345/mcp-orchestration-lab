import asyncio

from ..common.models import Fact
from ..common.operations import csv_bytes
from ..common.worker import choose, explain, run_job
from .models import Recipe, Result
from .operations import predict


async def execute(client, job, dataset, target, time_column, rules, prediction_data):
    async def work():
        table = await client.table(dataset)
        future = await client.table(prediction_data) if prediction_data else None
        recipe = await choose(
            client,
            Recipe,
            {
                "job": job,
                "target": target,
                "time_column": time_column,
                "columns": table.columns,
                "sample": table.rows[:5],
                "rules": rules.model_dump(),
            },
        )
        await client.stage("accepted_recipe", recipe.model_dump())
        details, split, rows, warnings = await asyncio.to_thread(
            predict, table, recipe, rules, target, time_column, future
        )
        await client.stage("prediction_checked", details.model_dump())
        facts = [
            Fact(
                id="test_rows",
                label="Held-back records",
                value=details.test_rows,
                sources=[dataset.id],
            )
        ]
        facts.extend(
            Fact(id=f"model_{key}", label=key, value=value, sources=[dataset.id])
            for key, value in details.metrics.items()
        )
        facts.extend(
            Fact(id=f"baseline_{key}", label="Baseline " + key, value=value, sources=[dataset.id])
            for key, value in details.baseline_metrics.items()
        )
        summary, notes = await explain(client, job, facts, warnings)
        artifacts = [
            await client.publish(split),
            await client.publish(
                {
                    "details": details.model_dump(),
                    "facts": [fact.model_dump() for fact in facts],
                    "warnings": warnings,
                }
            ),
            await client.publish(
                csv_bytes(["source_row", "split", "actual", "predicted"], rows), "csv"
            ),
        ]
        return Result(
            summary=summary,
            details=details,
            facts=facts,
            artifacts=artifacts,
            warnings=warnings + notes,
        )

    return await run_job(client, Result, work)
