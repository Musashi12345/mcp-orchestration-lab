"""Bounded model choice, trusted calculation, and checked explanation for one job."""

import asyncio
import re

from ...orchestration.models import OrchestrationError
from .models import Explanation, NeedsInput, Unsupported
from .operations import render_text


async def choose(client, recipe_type, context):
    errors = []
    for attempt in range(2):
        try:
            value = await client.model("recipe", context | {"validation_errors": errors})
            return recipe_type.model_validate(value)
        except (OrchestrationError, ValueError) as exc:
            if isinstance(exc, OrchestrationError) and exc.code != "MODEL_FORMAT":
                raise
            errors = [str(exc)[:2000]]
            if attempt:
                raise


async def explain(client, job, facts, warnings):
    response = Explanation.model_validate(
        await client.model(
            "explanation",
            {
                "job": job,
                "facts": [fact.model_dump() for fact in facts],
                "warnings": warnings,
            },
        )
    )
    known = {fact.id for fact in facts}
    if not set(response.fact_ids) <= known:
        raise NeedsInput("The model cited a fact that was not calculated.")
    used = set(re.findall(r"\{\{fact:([a-zA-Z0-9_]+)\}\}", response.text))
    if not used <= set(response.fact_ids):
        raise NeedsInput("A numeric claim is missing its declared fact reference.")
    return render_text(response.text, facts), [
        render_text(note, facts) for note in response.warnings
    ]


async def run_job(client, result_type, operation):
    claim = await client.request("claim")
    if claim.get("result"):
        return result_type.model_validate(claim["result"])
    try:
        result = await operation()
    except (NeedsInput, Unsupported) as exc:
        result = result_type(
            outcome="NEEDS_INPUT" if isinstance(exc, NeedsInput) else "UNSUPPORTED",
            summary=str(exc),
            questions=[str(exc)] if isinstance(exc, NeedsInput) else [],
        )
    except OrchestrationError as exc:
        result = result_type(
            outcome="UNSUPPORTED" if exc.code in {"WORKER_ROWS", "WORKER_SIZE"} else "FAILED",
            summary=str(exc),
            error={"code": exc.code, "message": str(exc)},
        )
    except asyncio.CancelledError:
        raise
    result = result.model_copy(update={"usage_record_ids": client.usage_ids})
    saved = await client.request("finish", result=result.model_dump(mode="json"))
    return result_type.model_validate(saved["result"])
