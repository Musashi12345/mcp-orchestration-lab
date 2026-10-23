import asyncio

import pytest

from mcp_execution_lab.orchestration.executor import Executor
from mcp_execution_lab.orchestration.mcp import Connections
from mcp_execution_lab.orchestration.models import Limits, OrchestrationError, ReviewRule, TaskRules


def literal(value):
    return {"kind": "literal", "value": value}


def output(step):
    return {"kind": "step", "key": step}


def node(name, *, dependencies=(), arguments=None, tool="echo", condition=None):
    return {
        "id": name,
        "subtask_id": name,
        "server": "fixture",
        "tool": tool,
        "depends_on": list(dependencies),
        "arguments": arguments or {"value": literal({"ok": True})},
        "condition": condition,
    }


def pipeline(lab, nodes, outputs):
    selected = list(dict.fromkeys("fixture/" + step["tool"] for step in nodes))
    selection = {
        "tool_keys": selected,
        "reasons": ["Required by the test question" for _ in selected],
    }
    lab.client.overrides.update(
        {
            "tool_selection": selection,
            "subtasks": {
                "selection": selection,
                "subtasks": [
                    {
                        "id": step["subtask_id"],
                        "tool_key": "fixture/" + step["tool"],
                        "job": "Complete " + step["id"],
                        "expected_outputs": ["result"],
                    }
                    for step in nodes
                ],
            },
            "dag": {"steps": nodes, "outputs": outputs},
        }
    )


def engine(lab, *, model=None):
    return Executor(lab.store, lab.files, lab.budget, lab.servers, model)


def reviews():
    return TaskRules(
        reviews=[
            ReviewRule(id="first", after_completed_steps=1),
            ReviewRule(id="second", after_completed_steps=2),
        ]
    )


async def test_real_mcp_execution_and_live_start_records(lab, monkeypatch):
    handoff = await lab.planner.plan("Count the rows", [lab.source])
    original = Connections.call

    async def observe(self, server, name, arguments, operation_id):
        attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
        assert attempts[-1]["payload"]["status"] == "RUNNING"
        assert attempts[-1]["payload"]["operation_id"] == operation_id
        return await original(self, server, name, arguments, operation_id)

    monkeypatch.setattr(Connections, "call", observe)
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    assert result["task_success"] is None
    ref = result["outputs"]["answer"]
    from mcp_execution_lab.orchestration.models import FileRef

    answer = await lab.files.read_json(handoff.run_id, FileRef.model_validate(ref))
    assert answer["answer"]["row_count"] == 2
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [row["payload"]["tool"] for row in attempts] == ["profile", "present"]
    assert all(row["payload"]["status"] == "SUCCEEDED" for row in attempts)


async def test_parallel_readiness_does_not_wait_for_unrelated_slow_step(lab):
    pipeline(
        lab,
        [
            node("slow", arguments={"value": literal({"slow": True}), "delay": literal(0.6)}),
            node("fast", arguments={"value": literal({"fast": True}), "delay": literal(0.01)}),
            node("child", dependencies=["fast"], arguments={"value": output("fast")}),
        ],
        {"child": output("child"), "slow": output("slow")},
    )
    handoff = await lab.planner.plan("Do independent work", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    history = await lab.store.history(handoff.run_id)

    def sequence(step, state):
        return next(
            entry["sequence"]
            for entry in history
            if entry["kind"] == "step_state"
            and entry["payload"]["step_id"] == step
            and entry["payload"]["state"] == state
        )

    assert sequence("fast", "SUCCEEDED") < sequence("child", "RUNNING")
    assert sequence("child", "RUNNING") < sequence("slow", "SUCCEEDED")


async def test_skip_uses_explicit_alternative_and_makes_no_call(lab):
    condition = {"left": literal(False), "op": "eq", "right": literal(True)}
    choice = {
        "kind": "choice",
        "condition": condition,
        "when_true": output("optional"),
        "when_false": literal({"original": True}),
    }
    pipeline(
        lab,
        [
            node("optional", condition=condition),
            node("answer", dependencies=["optional"], arguments={"value": choice}),
        ],
        {"answer": output("answer")},
    )
    handoff = await lab.planner.plan("Use optional work only when necessary", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["states"] == {"optional": "SKIPPED", "answer": "SUCCEEDED"}
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1


async def test_known_failure_blocks_consumers_without_retry(lab):
    pipeline(
        lab,
        [
            node("bad", tool="fail", arguments={"message": literal("deliberate")}),
            node("dependent", dependencies=["bad"], arguments={"value": output("bad")}),
        ],
        {"answer": output("dependent")},
    )
    handoff = await lab.planner.plan("Handle failure", [lab.source])
    result = await engine(lab).run(handoff)
    assert result["status"] == "FAILED"
    assert result["states"] == {"bad": "FAILED", "dependent": "BLOCKED"}
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1 and attempts[0]["payload"]["response"]["is_error"]


async def test_safe_transport_retry_is_another_attempt_of_same_operation(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    original = Connections.call
    attempts = []

    async def interrupted(self, server, name, arguments, operation_id):
        attempts.append(operation_id)
        if len(attempts) == 1:
            raise ConnectionError("lost connection before test dispatch")
        return await original(self, server, name, arguments, operation_id)

    monkeypatch.setattr(Connections, "call", interrupted)
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    assert attempts[0] == attempts[1]
    recorded = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(recorded) == 3
    assert recorded[0]["payload"]["status"] == "UNCERTAIN"


async def test_unknown_outcome_is_saved_and_not_automatically_restarted(lab, monkeypatch):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    lab.budget.limits = Limits(tool_seconds=0.01, transport_retries=0)

    async def missing_reply(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(Connections, "call", missing_reply)
    runner = engine(lab)
    with pytest.raises(OrchestrationError, match="confirmed"):
        await runner.run(handoff)
    assert (await lab.store.run(handoff.run_id))["status"] == "UNCERTAIN"
    with pytest.raises(OrchestrationError, match="unstarted"):
        await engine(lab).run(handoff)
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1


@pytest.mark.parametrize("mode", ["D1", "D2"])
async def test_same_task_review_rules_but_only_d2_calls_the_model(lab, mode):
    handoff = await lab.planner.plan("Count rows", [lab.source], mode=mode, rules=reviews())
    result = await engine(lab, model=lab.model).run(handoff)
    assert result["status"] == "COMPLETED"
    calls = [request for request in lab.client.requests if request["stage"] == "review"]
    assert len(calls) == (2 if mode == "D2" else 0)
    assert len(await lab.store.list_records(handoff.run_id, "review")) == 2


async def test_d2_replaces_only_remaining_work_and_reuses_saved_output(lab):
    def decide(request):
        context = request["context"]
        if context["review_rule"]["id"] == "second":
            return {"decision": "KEEP", "reason": "Completed revised work"}
        saved = next(iter(context["valid_outputs"]))
        return {
            "decision": "REVISE",
            "reason": "Return the existing count through a revised step",
            "breakdown": {
                "selection": {"tool_keys": ["fixture/present"], "reasons": ["Present saved count"]},
                "subtasks": [
                    {
                        "id": "new_answer",
                        "tool_key": "fixture/present",
                        "job": "Present saved count",
                        "expected_outputs": ["answer"],
                    }
                ],
            },
            "replacement": {
                "steps": [
                    node(
                        "new_answer",
                        tool="present",
                        arguments={"summary": {"kind": "snapshot", "key": saved}},
                    )
                ],
                "outputs": {"answer": output("new_answer")},
            },
        }

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="D2", rules=reviews())
    result = await engine(lab, model=lab.model).run(handoff)
    assert result["status"] == "COMPLETED" and result["plan_version"] == 2
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [row["payload"]["step_id"] for row in attempts] == ["count", "new_answer"]
    assert len(await lab.store.list_records(handoff.run_id, "plan")) == 2
    history = await lab.store.history(handoff.run_id)
    assert any(
        entry["kind"] == "step_state"
        and entry["payload"]["step_id"] == "answer"
        and entry["payload"]["state"] == "REPLACED"
        for entry in history
    )


async def test_accepted_handoff_cannot_be_changed_before_execution(lab):
    handoff = await lab.planner.plan("Count rows", [lab.source])
    changed = handoff.model_copy(update={"mode": "D2"})
    with pytest.raises(OrchestrationError, match="differs"):
        await engine(lab, model=lab.model).run(changed)
