import asyncio

import pytest

from mcp_execution_lab.agents.common.client import RunClient
from mcp_execution_lab.agents.common.gateway import WorkerGateway
from mcp_execution_lab.orchestration.models import OrchestrationError


async def open_worker(lab, gateway, handoff):
    attempt = await lab.store.put(
        handoff.run_id,
        "tool_attempt",
        {"status": "RUNNING"},
        parents=[("plan", handoff.plan_record)],
    )
    context = await gateway.open(
        "data_understanding",
        handoff.plan.steps[0],
        {"job": "Count rows", "dataset": handoff.datasets[0].ref.model_dump()},
        attempt,
        attempt,
        "Count rows",
    )
    await RunClient(context).request("claim")
    return context


async def test_parallel_workers_share_the_actual_run_model_allowance(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    lab.budget.limits = lab.limits.model_copy(update={"max_model_calls": 5})
    lab.client.overrides["worker.data_understanding.recipe"] = {}
    async with WorkerGateway(handoff, lab.store, lab.files, lab.budget, lab.model) as gateway:
        contexts = [await open_worker(lab, gateway, handoff) for _ in range(2)]
        results = await asyncio.gather(
            *(RunClient(context).model("recipe", {}) for context in contexts),
            return_exceptions=True,
        )
        assert sum(isinstance(result, OrchestrationError) for result in results) == 1
        assert lab.budget.model_calls == 5
        calls = await lab.store.list_records(handoff.run_id, "model_call")
        assert len(calls) == 5


async def test_worker_capability_rejects_unissued_tokens_and_unsupplied_files(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    other_run = await lab.store.create_run({})
    foreign = await lab.files.register_csv(other_run, lab.source)
    async with WorkerGateway(handoff, lab.store, lab.files, lab.budget, lab.model) as gateway:
        context = await open_worker(lab, gateway, handoff)
        client = RunClient(context)
        with pytest.raises(OrchestrationError, match="not an input"):
            await client.table(foreign.ref)
        with pytest.raises(OrchestrationError, match="Inactive"):
            await RunClient(context | {"token": "not-issued"}).request("stage", name="x", detail={})
        await gateway.close_call(gateway.contexts[context["token"]], "CANCELLED")
        with pytest.raises(OrchestrationError, match="Inactive"):
            await client.request("stage", name="x", detail={})


async def test_cancelling_support_cancels_and_records_a_running_worker_model_call(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    entered = asyncio.Event()

    async def blocked(request, directory):
        entered.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(lab.client, "generate", blocked)
    async with WorkerGateway(handoff, lab.store, lab.files, lab.budget, lab.model) as gateway:
        context = await open_worker(lab, gateway, handoff)
        pending = asyncio.create_task(RunClient(context).model("recipe", {}))
        await asyncio.wait_for(entered.wait(), 5)
        await gateway.close_call(gateway.contexts[context["token"]], "UNCERTAIN")
        await asyncio.gather(pending, return_exceptions=True)
    calls = await lab.store.list_records(handoff.run_id, "model_call")
    assert calls[-1]["payload"]["status"] == "INTERRUPTED"
    assert (await lab.store.list_records(handoff.run_id, "worker_call"))[-1]["payload"][
        "status"
    ] == "UNCERTAIN"
