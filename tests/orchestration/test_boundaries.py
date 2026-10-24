import asyncio
from types import SimpleNamespace

import pytest
from mcp import types

from mcp_execution_lab.orchestration.broker import ToolBroker
from mcp_execution_lab.orchestration.budget import Budget
from mcp_execution_lab.orchestration.config import Settings, local_environment
from mcp_execution_lab.orchestration.executor import Executor
from mcp_execution_lab.orchestration.mcp import Connections, check_schema
from mcp_execution_lab.orchestration.models import Limits, OrchestrationError, ServerConfig
from mcp_execution_lab.orchestration.service import Application

from .test_executor import engine, literal, node, output, pipeline, reviews


async def test_no_tools_are_forced_when_the_goal_needs_only_available_metadata(lab):
    pipeline(lab, [], {"answer": literal({"message": "No worker action needed"})})
    handoff = await lab.planner.plan("Return already available information", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    assert result["states"] == {}
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")


async def test_known_failure_can_reach_d2_review_without_a_successful_step(lab):
    pipeline(
        lab,
        [node("bad", tool="fail", arguments={"message": literal("test failure")})],
        {"answer": output("bad")},
    )
    lab.client.overrides["review"] = {"decision": "STOP", "reason": "Observed the failed job"}
    handoff = await lab.planner.plan("Handle a failure", [lab.source], mode="D2", rules=reviews())
    with pytest.raises(OrchestrationError, match="Observed the failed job"):
        await engine(lab, model=lab.model).run(handoff)
    calls = [value for value in lab.client.requests if value["stage"] == "review"]
    assert len(calls) == 1 and calls[0]["context"]["states"]["bad"] == "FAILED"


async def test_short_d2_plan_records_unreached_review_without_extra_agent_call(lab):
    pipeline(lab, [node("one")], {"answer": output("one")})
    handoff = await lab.planner.plan("One bounded job", [lab.source], mode="D2", rules=reviews())
    result = await engine(lab, model=lab.model).run(handoff)
    assert result["status"] == "COMPLETED"
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1
    history = await lab.store.history(handoff.run_id)
    assert any(event["kind"] == "review_unreached" for event in history)


async def test_restart_preserves_planning_usage_and_rejects_changed_settings(lab):
    settings = Settings(servers=lab.servers, limits=lab.limits, task_rules=reviews())
    app = Application(lab.store, lab.files.root, settings, client=lab.client)
    handoff = await app.plan("Count rows", [lab.source], mode="D2")
    changed = settings.model_copy(update={"limits": Limits(max_model_calls=20)})
    with pytest.raises(OrchestrationError, match="settings differ"):
        await Application(lab.store, lab.files.root, changed, client=lab.client).execute(
            handoff.run_id
        )
    restarted = Application(lab.store, lab.files.root, settings, client=lab.client)
    result = await restarted.execute(handoff.run_id)
    assert result["metrics"]["model_calls"] == 6
    assert result["metrics"]["observed_tokens"] == 60


async def test_model_limit_cannot_be_reset_between_plan_and_execution(lab):
    settings = Settings(servers=lab.servers, limits=Limits(max_model_calls=4), task_rules=reviews())
    app = Application(lab.store, lab.files.root, settings, client=lab.client)
    handoff = await app.plan("Count rows", [lab.source], mode="D2")
    with pytest.raises(OrchestrationError, match="Model-call"):
        await app.execute(handoff.run_id)
    assert len(lab.client.requests) == 4


async def test_changed_tool_cache_is_rejected_before_dispatch(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    original = Connections.discover

    async def changed(self):
        cache = await original(self)
        changed_tool = cache.tools[0].model_copy(update={"description": "Changed capability"})
        return cache.model_copy(update={"tools": [changed_tool, *cache.tools[1:]]})

    monkeypatch.setattr(Connections, "discover", changed)
    with pytest.raises(OrchestrationError, match="changed after planning"):
        await engine(lab).run(handoff)
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")


async def test_known_completion_reuse_does_not_make_another_mcp_call(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    async with Connections(lab.servers) as connections:
        broker = ToolBroker(handoff, connections, lab.store, lab.files, lab.budget)
        step = handoff.plan.steps[0]
        arguments = {"dataset": handoff.datasets[0].ref.model_dump()}
        job = handoff.breakdown.subtasks[0].job
        first = await broker.call(step, arguments, plan_id=handoff.plan_record, job=job)
        second = await broker.call(step, arguments, plan_id=handoff.plan_record, job=job)
    assert first == second and broker.reuses == 1
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1


async def test_foreign_dataset_reference_is_rejected_before_transport(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    foreign = handoff.datasets[0].ref.model_copy(update={"run_id": "another_run"})
    transport = SimpleNamespace(call=None)
    broker = ToolBroker(handoff, transport, lab.store, lab.files, lab.budget)
    with pytest.raises(OrchestrationError, match="another run"):
        await broker.call(
            handoff.plan.steps[0],
            {"dataset": foreign.model_dump()},
            plan_id=handoff.plan_record,
            job="Count rows",
        )
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")


async def test_database_save_failure_stops_dependent_work(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    original = lab.store.finish

    async def unavailable(run_id, record_id, payload):
        row = await lab.store.get(run_id, record_id)
        if row["kind"] == "tool_attempt" and payload["status"] == "SUCCEEDED":
            raise RuntimeError("simulated database write outage")
        await original(run_id, record_id, payload)

    monkeypatch.setattr(lab.store, "finish", unavailable)
    with pytest.raises(RuntimeError, match="write outage"):
        await engine(lab).run(handoff)
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1
    assert attempts[0]["payload"]["status"] == "RUNNING"
    final = (await lab.store.list_records(handoff.run_id, "execution_result"))[-1]["payload"]
    assert final["states"]["count"] == "FAILED"


async def test_cancellation_is_recorded_and_no_dependent_step_starts(lab):
    pipeline(
        lab,
        [
            node("slow", arguments={"value": literal({"ok": True}), "delay": literal(2)}),
            node("next", dependencies=["slow"], arguments={"value": output("slow")}),
        ],
        {"answer": output("next")},
    )
    handoff = await lab.planner.plan("Run a cancellable job", [lab.source])
    task = asyncio.create_task(engine(lab).run(handoff))
    for _ in range(300):
        if await lab.store.list_records(handoff.run_id, "tool_attempt"):
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await lab.store.run(handoff.run_id))["status"] == "INTERRUPTED"
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1 and attempts[0]["payload"]["status"] == "UNCERTAIN"


async def test_only_one_executor_can_claim_a_ready_run(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    runners = [Executor(lab.store, lab.files, lab.budget, lab.servers) for _ in range(2)]
    values = await asyncio.gather(
        *(runner.run(handoff) for runner in runners), return_exceptions=True
    )
    assert sum(isinstance(value, dict) for value in values) == 1
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 2
    assert (await lab.store.run(handoff.run_id))["status"] == "COMPLETED"


async def test_connections_open_only_requested_servers_and_can_add_one(lab):
    second = ServerConfig(
        id="other",
        command=lab.servers[0].command,
        args=lab.servers[0].args,
        env_names=lab.servers[0].env_names,
    )
    async with Connections([*lab.servers, second], initial_ids={"fixture"}) as connections:
        assert set(connections.sessions) == {"fixture"}
        await connections.ensure({"other"})
        assert set(connections.sessions) == {"fixture", "other"}
        cache = await connections.discover()
        assert len(cache.tools) == 12
        assert cache.lookup("fixture", "profile").name == cache.lookup("other", "profile").name


async def test_discovery_reads_all_pages_and_preserves_raw_schema():
    first = types.Tool(
        name="one", description="First available action", input_schema={"type": "object"}
    )
    second = types.Tool(
        name="two", description="Second available action", input_schema={"type": "object"}
    )

    class Paged:
        async def list_tools(self, *, params):
            return (
                types.ListToolsResult(tools=[first], next_cursor="next")
                if params.cursor is None
                else (types.ListToolsResult(tools=[second]))
            )

    connections = Connections([])
    connections.sessions = {"fixture": Paged()}
    cache = await connections.discover()
    assert [tool.name for tool in cache.tools] == ["one", "two"]
    assert cache.tools[0].raw_definition["input_schema"] == {"type": "object"}


async def test_missing_model_usage_stays_unknown(lab, monkeypatch):
    original = lab.client.generate

    async def missing_usage(request, directory):
        result = await original(request, directory)
        result.pop("usage")
        return result

    monkeypatch.setattr(lab.client, "generate", missing_usage)
    handoff = await lab.planner.plan("Count rows", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["metrics"]["observed_tokens"] is None


async def test_plan_records_are_immutable(lab):
    run_id = await lab.store.create_run({})
    record = await lab.store.put(run_id, "plan", {"version": 1})
    with pytest.raises(OrchestrationError, match="may change"):
        await lab.store.finish(run_id, record, {"version": 99})


def test_observed_token_limit_prevents_the_next_model_call():
    budget = Budget(Limits(max_observed_tokens=10))
    budget.observe({"input_tokens": 5, "output_tokens": 5})
    with pytest.raises(OrchestrationError, match="token allowance"):
        budget.model()


def test_external_schema_references_are_rejected():
    with pytest.raises(OrchestrationError, match="External schema"):
        check_schema({"$ref": "https://unconfigured.example/schema.json"})


def test_missing_database_credentials_have_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_LAB_DATABASE_URL", raising=False)
    with pytest.raises(OrchestrationError, match=".env.example"):
        local_environment(tmp_path)


async def test_changed_code_cannot_silently_execute_a_saved_plan(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    from mcp_execution_lab.orchestration import executor

    actual = executor.source_identity()
    monkeypatch.setattr(executor, "source_identity", lambda: actual | {"source_sha256": "0" * 64})
    with pytest.raises(OrchestrationError, match="changed after planning"):
        await engine(lab).run(handoff)
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")
