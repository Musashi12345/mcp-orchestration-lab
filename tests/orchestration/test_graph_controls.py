import pytest

from mcp_execution_lab.orchestration.graph import validate_plan
from mcp_execution_lab.orchestration.models import Breakdown, OrchestrationError, Plan

from .test_executor import literal, node, output, pipeline


async def test_literal_argument_type_is_checked_before_execution(lab):
    pipeline(
        lab,
        [node("job", arguments={"value": literal({}), "delay": literal("wrong type")})],
        {"answer": output("job")},
    )
    with pytest.raises(OrchestrationError, match="Invalid literal"):
        await lab.planner.plan("Complete the job", [lab.source])
    assert not any(request["stage"] == "review" for request in lab.client.requests)


async def test_unguarded_reference_to_skipped_output_is_rejected(lab):
    condition = {"left": literal(False), "op": "eq", "right": literal(True)}
    pipeline(
        lab,
        [
            node("optional", condition=condition),
            node("answer", dependencies=["optional"], arguments={"value": output("optional")}),
        ],
        {"answer": output("answer")},
    )
    with pytest.raises(OrchestrationError, match="explicit alternative"):
        await lab.planner.plan("Use optional work", [lab.source])


async def test_duplicate_steps_and_tool_subtask_mismatch_are_rejected(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    duplicate = handoff.plan.model_copy(update={"steps": [handoff.plan.steps[0]] * 2})
    with pytest.raises(OrchestrationError, match="Duplicate step"):
        validate_plan(duplicate, handoff.breakdown, handoff.cache, handoff.datasets, lab.limits)
    wrong = handoff.plan.model_dump()
    wrong["steps"][0]["tool"] = "unrelated"
    with pytest.raises(OrchestrationError, match="different tool"):
        validate_plan(
            Plan.model_validate(wrong),
            handoff.breakdown,
            handoff.cache,
            handoff.datasets,
            lab.limits,
        )


async def test_tool_list_and_node_listing_order_do_not_prescribe_execution_order(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    reversed_cache = handoff.cache.model_copy(update={"tools": list(reversed(handoff.cache.tools))})
    reversed_plan = handoff.plan.model_copy(update={"steps": list(reversed(handoff.plan.steps))})
    order = validate_plan(
        reversed_plan, handoff.breakdown, reversed_cache, handoff.datasets, lab.limits
    )
    assert order == ["count", "answer"]


async def test_nonexistent_published_output_path_is_rejected(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    tools = [
        tool.model_copy(
            update={
                "output_schema": {
                    "type": "object",
                    "properties": {"row_count": {"type": "integer"}},
                    "required": ["row_count"],
                    "additionalProperties": False,
                }
            }
        )
        if tool.name == "profile"
        else tool
        for tool in handoff.cache.tools
    ]
    cache = handoff.cache.model_copy(update={"tools": tools})
    plan = handoff.plan.model_dump()
    plan["steps"][1]["arguments"]["summary"]["path"] = ["nonexistent"]
    with pytest.raises(OrchestrationError, match="no published output"):
        validate_plan(
            Plan.model_validate(plan), handoff.breakdown, cache, handoff.datasets, lab.limits
        )


async def test_dataset_tampering_is_rejected_before_worker_dispatch(lab):
    from mcp_execution_lab.orchestration.executor import Executor

    handoff = await lab.planner.plan("Count rows", [lab.source])
    registered = lab.files.directory(handoff.run_id) / (handoff.datasets[0].ref.id + ".csv")
    registered.write_text("product,amount\na,999\n", encoding="utf-8")
    result = await Executor(lab.store, lab.files, lab.budget, lab.servers).run(handoff)
    assert result["status"] == "FAILED"
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")


async def test_missing_required_capability_is_reported_without_inventing_a_tool(lab):
    lab.client.overrides["tool_selection"] = {
        "tool_keys": [],
        "reasons": [],
        "missing_capabilities": ["No forecasting tool is available"],
    }
    with pytest.raises(OrchestrationError, match="No forecasting tool"):
        await lab.planner.plan("Forecast sales", [lab.source])
    assert lab.client.requests[-1]["stage"] == "tool_selection"


def test_selection_requires_a_reason_for_each_agent():
    from pydantic import ValidationError

    from mcp_execution_lab.orchestration.models import Selection

    with pytest.raises(ValidationError, match="own short reason"):
        Selection(tool_keys=["a/one", "a/two"], reasons=["Only explains one tool"])


def test_a_revised_plan_cannot_replay_completed_steps():
    from mcp_execution_lab.orchestration.models import Limits, ToolCache, ToolDefinition

    tool = ToolDefinition(
        server="x",
        name="act",
        description="Return an object",
        plain_description="Return an object",
        input_schema={"type": "object"},
    )
    plan = Plan.model_validate(
        {
            "steps": [
                {"id": "done", "subtask_id": "job", "server": "x", "tool": "act", "arguments": {}}
            ],
            "outputs": {"answer": output("done")},
        }
    )
    breakdown = Breakdown.model_validate(
        {
            "selection": {"tool_keys": ["x/act"], "reasons": ["Job"]},
            "subtasks": [
                {
                    "id": "job",
                    "tool_key": "x/act",
                    "job": "Return result",
                    "expected_outputs": ["answer"],
                }
            ],
        }
    )
    with pytest.raises(OrchestrationError, match="completed steps"):
        validate_plan(plan, breakdown, ToolCache(tools=[tool]), [], Limits(), completed={"done"})
