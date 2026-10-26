"""Scripted P2 decisions with real Docker and official-SDK MCP fixture processes."""

import asyncio
import os

import pytest

from mcp_execution_lab.orchestration.mcp import Connections
from mcp_execution_lab.orchestration.models import FileRef, OrchestrationError
from mcp_execution_lab.orchestration.program_container import ProgramRevised

from .test_executor import engine as dag_engine
from .test_executor import literal, node, output, reviews
from .test_executor import pipeline as dag_pipeline
from .test_program_executor import engine, pipeline
from .test_program_planner import count_program

pytestmark = pytest.mark.skipif(
    os.environ.get("MCP_LAB_DOCKER_TEST") != "1", reason="Real Docker opt-in required."
)


@pytest.fixture(autouse=True)
def execution_deadline(lab):
    lab.budget.limits = lab.budget.limits.model_copy(update={"run_seconds": 180})


def revision(jobs, source, *, preserve=(), recoveries=None):
    keys = list(dict.fromkeys("fixture/" + tool for _, tool in jobs))
    return {
        "decision": "REVISE",
        "reason": "Continue only remaining work using checked results",
        "breakdown": {
            "selection": {"tool_keys": keys, "reasons": ["Remaining work" for _ in keys]},
            "subtasks": [
                {
                    "id": name,
                    "tool_key": "fixture/" + tool,
                    "job": "Complete " + name,
                    "expected_outputs": ["result"],
                }
                for name, tool in jobs
            ],
        },
        "replacement": {"source": source, "outputs": ["answer"]},
        "preserve": list(preserve),
        "recoveries": recoveries or {},
    }


async def answer(lab, handoff, result):
    return await lab.files.read_json(
        handoff.run_id, FileRef.model_validate(result["outputs"]["answer"])
    )


@pytest.mark.parametrize("mode", ["P1", "P2"])
async def test_keep_preserves_runner_locals_and_counts_only_p2_reviews(lab, mode):
    pipeline(
        lab,
        [("one", "echo"), ("two", "echo")],
        """async def run(sdk, inputs):
    local = {"preserved": True}
    one = await sdk.call("one", {"value": local})
    two = await sdk.call("two", {"value": one["value"]})
    return {"answer": {"local": local, "result": two["value"]}}
""",
    )
    handoff = await lab.planner.plan("Continue", [lab.source], mode=mode, rules=reviews())
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    assert (await answer(lab, handoff, result))["local"] == {"preserved": True}
    assert len(await lab.store.list_records(handoff.run_id, "program_container")) == 1
    assert len([r for r in lab.client.requests if r["stage"] == "review"]) == (
        2 if mode == "P2" else 0
    )
    assert result["metrics"]["model_calls"] == (6 if mode == "P2" else 4)


async def test_revision_reuses_saved_count_in_fresh_runner_without_replay(lab):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])

    def decide(request):
        context = request["context"]
        if context["review_rule"]["id"] == "second":
            return {"decision": "KEEP", "reason": "Revised result is ready"}
        saved = next(iter(context["valid_outputs"]))
        return revision(
            [("new_answer", "present")],
            f"""async def run(sdk, inputs):
    previous = inputs["snapshot"][{saved!r}]
    result = await sdk.call("new_answer", {{"summary": previous["value"]}})
    return {{"answer": result["value"]}}
""",
            preserve=[saved],
        )

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    runner = engine(lab)
    result = await runner.run(handoff)
    assert result["status"] == "COMPLETED" and result["plan_version"] == 2
    assert (await answer(lab, handoff, result))["answer"]["row_count"] == 2
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [r["payload"]["step_id"] for r in attempts] == ["count", "new_answer"]
    containers = await lab.store.list_records(handoff.run_id, "program_container")
    assert len({r["payload"]["container_id"] for r in containers}) == 2
    assert len({r["payload"]["image_id"] for r in containers}) == 1
    assert len(await lab.store.list_records(handoff.run_id, "program")) == 2
    assert all(
        r["payload"]["cleanup"] == "REMOVED"
        for r in await lab.store.list_records(handoff.run_id, "program_diagnostics")
    )
    with pytest.raises(ProgramRevised):
        await runner._call({"subtask_id": "count", "arguments": {}, "handles": []}, epoch=1)
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 2


async def test_two_revisions_keep_global_counts_and_version_history(lab):
    pipeline(
        lab,
        [("one", "echo")],
        """async def run(sdk, inputs):
    result = await sdk.call("one", {"value": {"n": 1}})
    return {"answer": result["value"]}
""",
    )

    def decide(request):
        context = request["context"]
        name = "two" if context["review_rule"]["id"] == "first" else "three"
        saved = next(reversed(context["valid_outputs"]))
        return revision(
            [(name, "echo")],
            f"""async def run(sdk, inputs):
    previous = inputs["snapshot"][{saved!r}]
    result = await sdk.call({name!r}, {{"value": {{"previous": previous["value"]}}}})
    return {{"answer": result["value"]}}
""",
            preserve=[saved],
        )

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Continue", [lab.source], mode="P2", rules=reviews())
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED" and result["plan_version"] == 3
    assert (await answer(lab, handoff, result)) == {"previous": {"previous": {"n": 1}}}
    assert result["metrics"]["model_calls"] == 6
    assert result["metrics"]["tool_attempts"] == 3
    assert len(await lab.store.list_records(handoff.run_id, "handoff")) == 3
    assert len(await lab.store.list_records(handoff.run_id, "program_container")) == 3
    assert [
        r["payload"]["completed_steps"]
        for r in await lab.store.list_records(handoff.run_id, "review")
    ] == [1, 2]


@pytest.mark.parametrize("revise_again", [False, True])
async def test_parallel_barrier_drains_two_and_replaces_queued_third(lab, revise_again):
    pipeline(
        lab,
        [("one", "echo"), ("two", "echo"), ("three", "echo")],
        """async def run(sdk, inputs):
    results = await sdk.parallel(
        sdk.call("one", {"value": {"n": 1}, "delay": 0.3}),
        sdk.call("two", {"value": {"n": 2}, "delay": 0.5}),
        sdk.call("three", {"value": {"n": 3}}))
    return {"answer": results}
""",
    )

    def decide(request):
        context = request["context"]
        if context["review_rule"]["id"] == "second" and not revise_again:
            return {"decision": "KEEP", "reason": "Both completed results suffice"}
        saved = list(context["valid_outputs"])
        assert len(saved) == 2
        return revision(
            [],
            f"""async def run(sdk, inputs):
    first = inputs["snapshot"][{saved[0]!r}]["value"]
    second = inputs["snapshot"][{saved[1]!r}]["value"]
    return {{"answer": [first, second]}}
""",
            preserve=saved,
        )

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Parallel work", [lab.source], mode="P2", rules=reviews())
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED" and result["metrics"]["tool_attempts"] == 2
    assert result["plan_version"] == (3 if revise_again else 2)
    assert len(await lab.store.list_records(handoff.run_id, "program_container")) == 2
    assert sorted(v["n"] for v in await answer(lab, handoff, result)) == [1, 2]
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert {r["payload"]["step_id"] for r in attempts} == {"one", "two"}
    assert [
        r["payload"]["completed_steps"]
        for r in await lab.store.list_records(handoff.run_id, "review")
    ] == [2, 2]


async def test_stop_retains_reason_and_cleans_original_runner(lab):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    lab.client.overrides["review"] = {"decision": "STOP", "reason": "Need revised inputs"}
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError, match="revised inputs") as error:
        await engine(lab).run(handoff)
    assert error.value.code == "PLANNER_STOPPED"
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1
    assert (await lab.store.run(handoff.run_id))["status"] == "FAILED"
    assert (await lab.store.list_records(handoff.run_id, "program_diagnostics"))[0]["payload"][
        "cleanup"
    ] == "REMOVED"


@pytest.mark.parametrize("invalid", ["syntax", "completed_job", "snapshot"])
async def test_invalid_revisions_are_retained_and_bounded_before_restart(lab, invalid):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])

    def decide(request):
        if invalid == "completed_job":
            return revision(
                [("count", "echo")],
                "async def run(sdk, inputs):\n"
                '    x = await sdk.call("count", {"value": {}})\n'
                '    return {"answer": x}\n',
            )
        return revision(
            [],
            "import os\n"
            if invalid == "syntax"
            else 'async def run(sdk, inputs):\n    return {"answer": {}}\n',
            preserve=["guessed_private_artifact"] if invalid == "snapshot" else [],
        )

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "PLAN_INVALID"
    assert len(await lab.store.list_records(handoff.run_id, "review_candidate")) == 2
    assert len(await lab.store.list_records(handoff.run_id, "validation")) == 2
    assert len(await lab.store.list_records(handoff.run_id, "program_container")) == 1
    assert lab.budget.model_calls == 6


@pytest.mark.parametrize("mode", ["D2", "P2"])
@pytest.mark.parametrize("recover", [False, True])
async def test_revisions_must_explicitly_recover_prior_failures(lab, mode, recover):
    if mode == "P2":
        pipeline(
            lab,
            [("bad", "fail")],
            """async def run(sdk, inputs):
    result = await sdk.call("bad", {"message": "Known failure"})
    return {"answer": result}
""",
        )
    else:
        dag_pipeline(
            lab,
            [node("bad", tool="fail", arguments={"message": literal("Known failure")})],
            {"answer": output("bad")},
        )

    def decide(request):
        context = request["context"]
        if context["review_rule"]["id"] == "second":
            return {"decision": "KEEP", "reason": "No more revisions"}
        failed = list(context["unresolved_failures"])
        assert len(failed) == 1
        decision = revision(
            [("fixed", "echo")],
            "async def run(sdk, inputs):\n"
            '    x = await sdk.call("fixed", {"value": {"recovered": True}})\n'
            '    return {"answer": x["value"]}\n',
            recoveries={"fixed": failed} if recover else {},
        )
        if mode == "D2":
            decision.pop("preserve")
            decision["replacement"] = {
                "steps": [node("fixed")],
                "outputs": {"answer": output("fixed")},
            }
        return decision

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Recover", [lab.source], mode=mode, rules=reviews())
    runner = engine(lab) if mode == "P2" else dag_engine(lab, model=lab.model)
    result = await runner.run(handoff)
    assert result["status"] == ("COMPLETED" if recover else "FAILED")
    assert bool(result["unresolved_failures"]) != recover
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [r["payload"]["status"] for r in attempts] == ["FAILED", "SUCCEEDED"]


async def test_model_allowance_is_not_reset_at_reviews(lab):
    lab.budget.limits = lab.budget.limits.model_copy(update={"max_model_calls": 5})
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert lab.budget.model_calls == 5
    assert (await lab.store.run(handoff.run_id))["status"] == "FAILED"


async def test_cleanup_failure_prevents_replacement_runner(lab, monkeypatch):
    from mcp_execution_lab.orchestration import program_container

    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    lab.client.overrides["review"] = revision(
        [], 'async def run(sdk, inputs):\n    return {"answer": {}}\n'
    )
    original = program_container.docker

    async def unconfirmed_cleanup(*args, **kwargs):
        result = await original(*args, **kwargs)
        if args[0] == "rm":
            raise OrchestrationError("DOCKER", "Simulated missing cleanup confirmation")
        return result

    monkeypatch.setattr(program_container, "docker", unconfirmed_cleanup)
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "OUTCOME_UNKNOWN"
    assert len(await lab.store.list_records(handoff.run_id, "program_container")) == 1
    assert (await lab.store.run(handoff.run_id))["status"] == "UNCERTAIN"


async def test_review_correction_is_charged_and_snapshot_only_finalization_works(lab):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    count = 0

    def decide(request):
        nonlocal count
        count += 1
        saved = next(iter(request["context"]["valid_outputs"]))
        return revision(
            [],
            "import os\n"
            if count == 1
            else "async def run(sdk, inputs):\n"
            f'    return {{"answer": inputs["snapshot"][{saved!r}]["value"]}}\n',
            preserve=[saved],
        )

    lab.client.overrides["review"] = decide
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED" and result["plan_version"] == 2
    assert result["metrics"]["model_calls"] == 6 and result["metrics"]["tool_attempts"] == 1
    assert len(await lab.store.list_records(handoff.run_id, "validation")) == 1
    assert len(await lab.store.list_records(handoff.run_id, "review_candidate")) == 2


async def test_empty_p2_program_leaves_both_reviews_unreached(lab):
    pipeline(lab, [], 'async def run(sdk, inputs):\n    return {"answer": {"metadata": True}}\n')
    handoff = await lab.planner.plan("Metadata", [lab.source], mode="P2", rules=reviews())
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED" and result["metrics"]["tool_attempts"] == 0
    assert not await lab.store.list_records(handoff.run_id, "review")
    assert (
        len([r for r in await lab.store.history(handoff.run_id) if r["kind"] == "review_unreached"])
        == 2
    )


async def test_unknown_outcome_never_enters_p2_review(lab, monkeypatch):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    lab.budget.limits = lab.budget.limits.model_copy(
        update={"tool_seconds": 0.01, "transport_retries": 0}
    )

    async def missing_reply(*args, **kwargs):
        await asyncio.sleep(2)

    monkeypatch.setattr(Connections, "call", missing_reply)
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "OUTCOME_UNKNOWN"
    assert not await lab.store.list_records(handoff.run_id, "review")
    assert (await lab.store.run(handoff.run_id))["status"] == "UNCERTAIN"
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1


async def test_cancelling_review_retains_model_attempt_and_cleans_runner(lab):
    entered = asyncio.Event()
    original = lab.client.generate
    lab.client.overrides["program"] = lambda request: count_program(request["context"])

    async def generate(request, directory):
        if request["stage"] == "review":
            entered.set()
            await asyncio.Future()
        return await original(request, directory)

    lab.client.generate = generate
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    pending = asyncio.create_task(engine(lab).run(handoff))
    try:
        await asyncio.wait_for(entered.wait(), 60)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    calls = await lab.store.list_records(handoff.run_id, "model_call")
    assert calls[-1]["payload"]["stage"] == "review"
    assert calls[-1]["payload"]["status"] == "INTERRUPTED"
    assert (await lab.store.run(handoff.run_id))["status"] == "INTERRUPTED"
    assert (await lab.store.list_records(handoff.run_id, "program_diagnostics"))[0]["payload"][
        "cleanup"
    ] == "REMOVED"


async def test_protocol_failure_during_active_tool_retains_uncertainty(lab, monkeypatch):
    from mcp_execution_lab.orchestration import program_container

    pipeline(
        lab,
        [("slow", "echo")],
        """async def run(sdk, inputs):
    result = await sdk.call("slow", {"value": {}, "delay": 2})
    return {"answer": result}
""",
    )
    entered = asyncio.Event()
    original_call, original_read = Connections.call, program_container.read_async
    count = 0

    async def observe(self, *args, **kwargs):
        entered.set()
        return await original_call(self, *args, **kwargs)

    async def invalid_frame(stream, limit):
        nonlocal count
        count += 1
        if count == 3:
            await entered.wait()
            return {"type": "unrecognized"}
        return await original_read(stream, limit)

    monkeypatch.setattr(Connections, "call", observe)
    monkeypatch.setattr(program_container, "read_async", invalid_frame)
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P2", rules=reviews())
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "PROGRAM_PROTOCOL"
    assert (await lab.store.run(handoff.run_id))["status"] == "UNCERTAIN"
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1 and attempts[0]["payload"]["status"] == "UNCERTAIN"
