"""Acceptance checks for the five retained October 19 audit findings."""

import pytest

from mcp_execution_lab.orchestration.graph import validate_plan
from mcp_execution_lab.orchestration.models import OrchestrationError, Plan

from .test_executor import engine, literal, node, output, pipeline, reviews


async def test_explicit_d1_backup_handles_a_known_failed_tool(lab):
    backup = node(
        "backup", dependencies=["primary"], arguments={"value": literal({"answer": "backup"})}
    )
    backup["dependency_policy"] = "settled"
    backup["condition"] = {
        "left": {"kind": "status", "key": "primary", "path": ["state"]},
        "op": "eq",
        "right": literal("FAILED"),
    }
    pipeline(
        lab,
        [node("primary", tool="fail", arguments={"message": literal("Known failure")}), backup],
        {
            "answer": {
                "kind": "choice",
                "condition": backup["condition"],
                "when_true": output("backup"),
                "when_false": output("primary"),
            }
        },
    )
    handoff = await lab.planner.plan("Use the written backup on failure", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    assert result["states"] == {"primary": "FAILED", "backup": "SUCCEEDED"}
    assert not [request for request in lab.client.requests if request["stage"] == "review"]


async def test_skipping_a_later_listed_parent_starts_child_before_unrelated_slow_work(lab):
    condition = {"left": literal(False), "op": "eq", "right": literal(True)}
    pipeline(
        lab,
        [
            node("slow", arguments={"value": literal({}), "delay": literal(0.6)}),
            node("child", dependencies=["optional"]),
            node("optional", condition=condition),
        ],
        {"answer": output("child")},
    )
    handoff = await lab.planner.plan("Independent work with an optional input", [lab.source])
    await engine(lab).run(handoff)
    events = await lab.store.history(handoff.run_id)

    def sequence(step, state):
        return next(
            event["sequence"]
            for event in events
            if event["kind"] == "step_state"
            and event["payload"]["step_id"] == step
            and event["payload"]["state"] == state
        )

    assert (
        sequence("optional", "SKIPPED")
        < sequence("child", "RUNNING")
        < sequence("slow", "SUCCEEDED")
    )


async def test_review_includes_public_error_and_stop_retains_summary_and_unreached_rule(lab):
    pipeline(
        lab,
        [node("bad", tool="fail", arguments={"message": literal("Known failure")})],
        {"answer": output("bad")},
    )
    lab.client.overrides["review"] = {"decision": "STOP", "reason": "Need corrected inputs"}
    handoff = await lab.planner.plan("Inspect a failure", [lab.source], mode="D2", rules=reviews())
    with pytest.raises(OrchestrationError, match="corrected"):
        await engine(lab, model=lab.model).run(handoff)
    context = next(item["context"] for item in lab.client.requests if item["stage"] == "review")
    assert "Error executing tool fail" in context["public_failures"][0]["response_excerpt"]
    final = (await lab.store.list_records(handoff.run_id, "execution_result"))[0]["payload"]
    assert final["status"] == "FAILED" and final["metrics"]["model_calls"] == 5
    assert any(
        event["kind"] == "review_unreached" for event in await lab.store.history(handoff.run_id)
    )


async def test_published_integer_cannot_feed_an_object_argument_before_execution(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    tools = [
        tool.model_copy(
            update={
                "output_schema": {
                    "type": "object",
                    "properties": {"row_count": {"type": "integer"}},
                    "required": ["row_count"],
                }
            }
        )
        if tool.name == "profile"
        else tool
        for tool in handoff.cache.tools
    ]
    plan = handoff.plan.model_dump()
    plan["steps"][1]["arguments"]["summary"]["path"] = ["row_count"]
    with pytest.raises(OrchestrationError, match="incompatible"):
        validate_plan(
            Plan.model_validate(plan),
            handoff.breakdown,
            handoff.cache.model_copy(update={"tools": tools}),
            handoff.datasets,
            lab.limits,
        )
