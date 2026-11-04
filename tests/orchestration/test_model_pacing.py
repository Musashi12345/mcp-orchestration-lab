import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mcp_execution_lab.orchestration import model_pacing
from mcp_execution_lab.orchestration.config import ModelConfig, Settings
from mcp_execution_lab.orchestration.model import ModelCalls
from mcp_execution_lab.orchestration.model_pacing import ModelPacer
from mcp_execution_lab.orchestration.models import OrchestrationError, Record
from mcp_execution_lab.orchestration.service import Application


class Answer(Record):
    value: int


def virtual_time(monkeypatch, lab):
    lab.budget.limits = lab.budget.limits.model_copy(update={"run_seconds": 600})
    tick = [0.0]
    pauses = []

    async def sleep(delay):
        pauses.append(delay)
        tick[0] += delay
        await asyncio.sleep(0)

    monkeypatch.setattr(model_pacing, "time", SimpleNamespace(perf_counter=lambda: tick[0]))
    monkeypatch.setattr(
        model_pacing,
        "asyncio",
        SimpleNamespace(
            Lock=asyncio.Lock,
            wait_for=asyncio.wait_for,
            sleep=sleep,
            CancelledError=asyncio.CancelledError,
        ),
    )
    return tick, pauses


def replies(lab, tick=None, *, fail_first=False):
    starts = []

    async def generate(request, directory):
        starts.append(tick[0] if tick is not None else request["stage"])
        if fail_first and len(starts) == 1:
            raise OrchestrationError("MODEL_SERVICE", "Confirmed provider rejection")
        return {"content": {"value": 1}, "usage": {"input_tokens": 1, "output_tokens": 1}}

    lab.client.generate = generate
    return starts


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_gap_must_be_finite_and_nonnegative(value):
    with pytest.raises(ValidationError):
        ModelConfig(request_gap_seconds=value)
    assert ModelConfig().request_gap_seconds == 0


async def test_ninety_second_gap_covers_planning_workers_and_reviews(lab, monkeypatch):
    tick, pauses = virtual_time(monkeypatch, lab)
    starts = replies(lab, tick)
    lab.model.pacer = ModelPacer(90)
    run_id = await lab.store.create_run({})
    for stage, role in (
        ("main_task", "initial_planner"),
        ("worker.analysis.recipe", "worker"),
        ("review", "replanner"),
    ):
        await lab.model.ask(run_id, stage, Answer, {}, role=role)
    assert starts == [0, 90, 180] and pauses == [90, 90]
    waits = await lab.store.list_records(run_id, "model_wait")
    assert len(waits) == 2
    assert all(
        row["payload"]["status"] == "SUCCEEDED" and row["payload"]["waited_seconds"] == 90
        for row in waits
    )
    assert lab.budget.model_calls == 3


async def test_concurrent_model_calls_are_spaced_when_enabled(lab, monkeypatch):
    tick, _ = virtual_time(monkeypatch, lab)
    starts = replies(lab, tick)
    lab.model.pacer = ModelPacer(90)
    run_id = await lab.store.create_run({})
    await asyncio.gather(*(lab.model.ask(run_id, "review", Answer, {}) for _ in range(3)))
    assert starts == [0, 90, 180]


async def test_failed_call_also_requires_a_gap_before_a_new_call(lab, monkeypatch):
    tick, pauses = virtual_time(monkeypatch, lab)
    starts = replies(lab, tick, fail_first=True)
    lab.model.pacer = ModelPacer(90)
    run_id = await lab.store.create_run({})
    with pytest.raises(OrchestrationError, match="Confirmed provider"):
        await lab.model.ask(run_id, "main_task", Answer, {})
    await lab.model.ask(run_id, "main_task", Answer, {})
    assert starts == [0, 90] and pauses == [90]
    assert not lab.budget.usage_complete


async def test_wait_is_outside_the_provider_response_timeout(lab):
    replies(lab)
    lab.model.pacer = ModelPacer(0.05)
    lab.model.config.timeout_seconds = 0.02
    run_id = await lab.store.create_run({})
    await lab.model.ask(run_id, "main_task", Answer, {})
    await lab.model.ask(run_id, "review", Answer, {})
    waits = await lab.store.list_records(run_id, "model_wait")
    # Work between calls also contributes to spacing; the sleep alone can be shorter.
    calls = await lab.store.list_records(run_id, "model_call")
    elapsed = datetime.fromisoformat(calls[1]["created_at"]) - datetime.fromisoformat(
        calls[0]["payload"]["finished_at"]
    )
    assert elapsed.total_seconds() >= 0.05
    assert waits[0]["payload"]["waited_seconds"] > lab.model.config.timeout_seconds
    assert lab.budget.model_calls == 2


async def test_new_components_use_saved_finish_time_and_share_the_application_gate(lab):
    starts = replies(lab)
    settings = Settings(servers=lab.servers, model=ModelConfig(request_gap_seconds=0.05))
    app = Application(lab.store, lab.files.root, settings, client=lab.client)
    _, _, first = app.components()
    _, _, second = app.components()
    assert first.pacer is second.pacer
    run_id = await lab.store.create_run({})
    await first.ask(run_id, "main_task", Answer, {})
    # A newly composed application has no in-memory completion timestamp.
    restored = ModelCalls(lab.client, settings.model, lab.store, lab.files, lab.budget)
    await restored.ask(run_id, "review", Answer, {})
    assert starts == ["main_task", "review"]
    waits = await lab.store.list_records(run_id, "model_wait")
    assert len(waits) == 1 and waits[0]["payload"]["status"] == "SUCCEEDED"


async def test_cancelled_wait_sends_no_call_or_usage_and_releases_the_gate(lab):
    replies(lab)
    lab.model.pacer = ModelPacer(1)
    run_id = await lab.store.create_run({})
    await lab.model.ask(run_id, "main_task", Answer, {})
    waiting = asyncio.create_task(lab.model.ask(run_id, "review", Answer, {}))
    while not await lab.store.list_records(run_id, "model_wait"):
        await asyncio.sleep(0.001)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    waits = await lab.store.list_records(run_id, "model_wait")
    assert waits[0]["payload"]["status"] == "INTERRUPTED"
    assert lab.budget.model_calls == 1 and lab.budget.usage_complete
    assert len(await lab.store.list_records(run_id, "model_call")) == 1
    assert not lab.model.pacer.lock.locked()


async def test_insufficient_run_time_does_not_send_or_count_a_call(lab):
    replies(lab)
    lab.model.pacer = ModelPacer(90)
    run_id = await lab.store.create_run({})
    await lab.model.ask(run_id, "main_task", Answer, {})
    with pytest.raises(OrchestrationError, match="remaining run time"):
        await lab.model.ask(run_id, "review", Answer, {})
    assert lab.budget.model_calls == 1
    assert len(await lab.store.list_records(run_id, "model_call")) == 1


async def test_default_zero_gap_keeps_independent_model_calls_parallel(lab):
    started = []
    both = asyncio.Event()

    async def generate(request, directory):
        started.append(request["stage"])
        if len(started) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), 1)
        return {"content": {"value": 1}, "usage": {"input_tokens": 1, "output_tokens": 1}}

    lab.client.generate = generate
    run_id = await lab.store.create_run({})
    await asyncio.gather(
        *(lab.model.ask(run_id, stage, Answer, {}) for stage in ("main_task", "review"))
    )
    assert len(started) == 2
    assert not await lab.store.list_records(run_id, "model_wait")
