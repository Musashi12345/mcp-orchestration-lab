from ..common.models import NeedsInput
from ..common.worker import choose, run_job
from .models import Recipe, Result
from .operations import evidence_facts, render


async def execute(client, job, evidence, charts, style):
    async def work():
        values = [await client.json(ref) for ref in evidence]
        for ref in charts:
            await client.json(ref)  # Verify the chart through its scoped registered reference.
        facts, warnings, sources = evidence_facts(values, evidence)
        errors = []
        for attempt in range(2):
            recipe = await choose(
                client,
                Recipe,
                {
                    "job": job,
                    "style": style.model_dump(),
                    "facts": [fact.model_dump() for fact in facts],
                    "warnings": warnings,
                    "validation_errors": errors,
                },
            )
            await client.stage("report_draft", recipe.model_dump())
            try:
                text, details = render(recipe, facts, sources, warnings, charts, style)
                break
            except NeedsInput as exc:
                if attempt:
                    raise
                errors = [str(exc)]
        await client.stage("claims_checked", details.model_dump())
        report = await client.publish(text.encode("utf-8"), "md")
        source_map = await client.publish(
            {
                "details": details.model_dump(),
                "facts": [fact.model_dump() for fact in facts],
                "warnings": warnings,
            }
        )
        return Result(
            summary="Report created from checked saved findings.",
            artifacts=[report, source_map],
            details=details,
            facts=facts,
            warnings=warnings,
        )

    return await run_job(client, Result, work)
