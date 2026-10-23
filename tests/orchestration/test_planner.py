import json

import pytest
from sqlalchemy.exc import IntegrityError

from mcp_execution_lab.orchestration.graph import validate_plan
from mcp_execution_lab.orchestration.mcp import Connections
from mcp_execution_lab.orchestration.model import SYSTEM_PROMPT
from mcp_execution_lab.orchestration.models import OrchestrationError, Plan

from .conftest import example_records


async def test_real_mcp_discovery_and_planning_never_execute_workers(lab):
    handoff = await lab.planner.plan("Count the rows", [lab.source])
    assert (await lab.store.run(handoff.run_id))["status"] == "READY_FOR_EXECUTION"
    assert len(handoff.cache.tools) == 6
    assert all(
        tool.model_dump()["key"] == tool.server + "/" + tool.name for tool in handoff.cache.tools
    )
    assert handoff.breakdown.selection.tool_keys == ["fixture/profile", "fixture/present"]
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [request["stage"] for request in lab.client.requests] == [
        "main_task",
        "tool_selection",
        "subtasks",
        "dag",
    ]
    assert handoff.datasets[0].row_count == 2
    assert lab.client.requests[0]["remaining"]["tool_attempts"] == lab.limits.max_tool_attempts
    assert lab.client.requests[0]["remaining"]["model_calls"] == lab.limits.max_model_calls - 1
    assert lab.source.read_text() == "product,amount\na,10\nb,20\n"
    events = await lab.store.history(handoff.run_id)
    assert [entry["sequence"] for entry in events] == list(range(1, len(events) + 1))
    stages = await lab.store.list_records(handoff.run_id, "stage")
    assert all(row["payload"]["status"] == "SUCCEEDED" for row in stages)


async def test_multiple_tools_share_one_server_and_cache_is_stable(lab):
    async with Connections(lab.servers) as connections:
        first = await connections.discover()
        second = await connections.discover()
        assert first.digest == second.digest
        assert len(connections.sessions) == 1
        await connections.verify(first)


async def test_subtasks_can_refine_the_draft_selection(lab):
    lab.client.overrides["tool_selection"] = {
        "tool_keys": ["fixture/profile"],
        "reasons": ["Count rows"],
    }
    handoff = await lab.planner.plan("Count the rows", [lab.source])
    assert len(handoff.breakdown.selection.tool_keys) == 2
    assert (
        len(
            (await lab.store.list_records(handoff.run_id, "tool_selection"))[0]["payload"][
                "tool_keys"
            ]
        )
        == 1
    )


async def test_bad_plan_is_recorded_and_corrected_by_model(lab):
    attempts = []

    def draft(request):
        result = example_records(request["context"])["dag"]
        if not attempts:
            result["steps"][0]["depends_on"] = ["answer"]
        attempts.append(request)
        return result

    lab.client.overrides["dag"] = draft
    handoff = await lab.planner.plan("Count rows", [lab.source])
    assert len(attempts) == 2
    assert attempts[1]["context"]["validation_errors"]
    assert len(await lab.store.list_records(handoff.run_id, "validation")) == 1
    candidates = await lab.store.list_records(handoff.run_id, "candidate")
    assert len([row for row in candidates if row["payload"]["stage"] == "dag"]) == 2


async def test_correction_exhaustion_retains_failed_run(lab):
    def bad(request):
        result = example_records(request["context"])["dag"]
        result["steps"][0]["depends_on"] = ["answer"]
        return result

    lab.client.overrides["dag"] = bad
    with pytest.raises(OrchestrationError, match="circle"):
        await lab.planner.plan("Count rows", [lab.source])
    run_id = lab.client.requests[0]["context"]["datasets"][0]["ref"]["run_id"]
    assert (await lab.store.run(run_id))["status"] == "PLANNING_FAILED"


@pytest.mark.parametrize("text", ["a,a\n1,2\n", "a,b\n1\n", "\n", 'a,b\n"unterminated,2\n'])
async def test_invalid_csv_is_rejected_before_model_work(lab, text):
    lab.source.write_text(text, encoding="utf-8")
    with pytest.raises(OrchestrationError):
        await lab.planner.plan("Count rows", [lab.source])
    assert not lab.client.requests


async def test_main_task_clarification_is_saved_without_selecting_tools(lab):
    def clarify(request):
        result = example_records(request["context"])["main_task"]
        result["clarification_questions"] = ["Which date range?"]
        return result

    lab.client.overrides["main_task"] = clarify
    with pytest.raises(OrchestrationError, match="Which date range"):
        await lab.planner.plan("Analyse this", [lab.source])
    assert len(lab.client.requests) == 1


async def test_database_enforces_cross_run_parent_ownership(lab):
    first = await lab.store.create_run({})
    second = await lab.store.create_run({})
    parent = await lab.store.put(first, "main_task", {})
    with pytest.raises(IntegrityError):
        await lab.store.put(second, "plan", {}, parents=[("task", parent)])
    assert await lab.store.list_records(second) == []


async def test_output_content_changes_are_detected(lab):
    run_id = await lab.store.create_run({})
    ref = await lab.files.put_json(run_id, {"answer": 2})
    (lab.files.directory(run_id) / (ref.id + ".json")).write_text('{"answer":99}')
    with pytest.raises(OrchestrationError, match="changed"):
        await lab.files.read_json(run_id, ref)


async def test_missing_dependency_and_unknown_tool_are_rejected(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    data = json.loads(handoff.plan.model_dump_json())
    data["steps"][1]["depends_on"] = []
    with pytest.raises(OrchestrationError, match="dependency path"):
        validate_plan(
            Plan.model_validate(data),
            handoff.breakdown,
            handoff.cache,
            handoff.datasets,
            lab.limits,
        )


def test_neutral_system_prompt_contains_no_agent_names_or_domain_sequence():
    for term in ("clean", "combine", "profile", "forecast", "predict", "pricing", "fixture/"):
        assert term not in SYSTEM_PROMPT.lower()


def test_production_store_never_silently_falls_back_to_sqlite():
    from mcp_execution_lab.orchestration.storage import Store

    with pytest.raises(OrchestrationError, match="PostgreSQL"):
        Store("sqlite://")
