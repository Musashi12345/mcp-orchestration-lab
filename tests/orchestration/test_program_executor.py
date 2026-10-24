import asyncio
import json
import os

import pytest

from mcp_execution_lab.orchestration.mcp import Connections
from mcp_execution_lab.orchestration.models import FileRef, OrchestrationError
from mcp_execution_lab.orchestration.program_container import docker
from mcp_execution_lab.orchestration.program_executor import ProgramExecutor

from .test_executor import reviews
from .test_program_planner import count_program

pytestmark = pytest.mark.skipif(
    os.environ.get("MCP_LAB_DOCKER_TEST") != "1", reason="Real Docker opt-in required."
)


def engine(lab):
    return ProgramExecutor(lab.store, lab.files, lab.budget, lab.servers, lab.model)


def pipeline(lab, jobs, source):
    keys = list(dict.fromkeys("fixture/" + tool for _, tool in jobs))
    selection = {"tool_keys": keys, "reasons": ["Required for the test" for _ in keys]}
    lab.client.overrides.update(
        {
            "tool_selection": selection,
            "subtasks": {
                "selection": selection,
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
            "program": {"source": source, "outputs": ["answer"]},
        }
    )


async def execute(lab, *, rules=None):
    handoff = await lab.planner.plan("Complete the CSV task", [lab.source], mode="P1", rules=rules)
    runner = engine(lab)
    return handoff, runner, await runner.run(handoff)


async def test_real_docker_mcp_sequence_and_live_records(lab, monkeypatch):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    original = Connections.call

    async def observe(self, *args, **kwargs):
        records = await lab.store.list_records(handoff.run_id, "tool_attempt")
        assert records[-1]["payload"]["status"] == "RUNNING"
        return await original(self, *args, **kwargs)

    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P1")
    monkeypatch.setattr(Connections, "call", observe)
    result = await engine(lab).run(handoff)
    assert result["status"] == "COMPLETED"
    value = await lab.files.read_json(
        handoff.run_id, FileRef.model_validate(result["outputs"]["answer"])
    )
    assert value["answer"]["row_count"] == 2
    assert len(lab.client.requests) == 4
    containers = await lab.store.list_records(handoff.run_id, "program_container")
    config = containers[0]["payload"]
    host = config["host_config"]
    assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
    assert config["user"] == "65532:65532" and config["mounts"] == []
    assert host["Memory"] == 512 * 1024**2 and host["PidsLimit"] == 64
    assert host["NanoCpus"] == 1000000000
    assert "size=16m" in host["Tmpfs"]["/tmp"]
    assert host["CapDrop"] == ["ALL"]
    assert any("no-new-privileges" in item for item in host["SecurityOpt"])
    diagnostics = await lab.store.list_records(handoff.run_id, "program_diagnostics")
    assert diagnostics[0]["payload"]["cleanup"] == "REMOVED"
    assert await docker("ps", "-aq", "--filter", "name=" + config["name"]) == b""


async def test_container_actually_blocks_host_files_network_and_root_writes(lab, monkeypatch):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P1")
    runner = engine(lab)
    original = Connections.call
    observed = []
    # Handwritten probe, executed only in the already confined container.
    probe = """import errno, json, os, socket
from pathlib import Path
result = {"uid": os.getuid(), "project_present": Path("/workspace").exists(),
          "database_env": "MCP_LAB_DATABASE_URL" in os.environ,
          "agent_package": Path("/opt/runner/mcp_execution_lab").exists(),
          "memory": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
          "pids": Path("/sys/fs/cgroup/pids.max").read_text().strip()}
try:
    Path("/opt/runner/forbidden.txt").write_text("probe")
    result["root_write"] = True
except OSError as exc:
    result["root_write"] = exc.errno
try:
    with socket.create_connection(("1.1.1.1", 53), timeout=0.5):
        result["network"] = True
except OSError:
    result["network"] = False
try:
    Path("/tmp/space-probe").write_bytes(b"x" * (17 * 1024**2))
    result["tmp_full"] = False
except OSError as exc:
    result["tmp_full"] = exc.errno == errno.ENOSPC
finally:
    Path("/tmp/space-probe").unlink(missing_ok=True)
print(json.dumps(result))
"""

    async def observe(self, *args, **kwargs):
        if not observed:
            observed.append(
                json.loads(await docker("exec", runner.container.name, "python", "-I", "-c", probe))
            )
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(Connections, "call", observe)
    assert (await runner.run(handoff))["status"] == "COMPLETED"
    result = observed[0]
    assert result["uid"] == 65532
    assert not result["project_present"] and not result["database_env"]
    assert not result["agent_package"] and not result["network"]
    assert result["root_write"] in {13, 30} and result["tmp_full"]
    assert result["memory"] == str(512 * 1024**2) and result["pids"] == "64"


@pytest.mark.parametrize("concurrency", [1, 2])
async def test_parallel_uses_shared_capacity_and_records_reviews_without_model(lab, concurrency):
    lab.budget.limits = lab.budget.limits.model_copy(update={"concurrency": concurrency})
    pipeline(
        lab,
        [("one", "echo"), ("two", "echo"), ("three", "echo")],
        """async def run(sdk, inputs):
    results = await sdk.parallel(
        sdk.call("one", {"value": {"n": 1}, "delay": 0.5}),
        sdk.call("two", {"value": {"n": 2}, "delay": 0.5}),
        sdk.call("three", {"value": {"n": 3}}))
    return {"answer": results}
""",
    )
    handoff, _, result = await execute(lab, rules=reviews())
    assert result["status"] == "COMPLETED"
    events = await lab.store.history(handoff.run_id)
    active, peak = 0, 0
    for event in events:
        if event["kind"] == "step_state":
            if event["payload"]["state"] == "RUNNING":
                active += 1
                peak = max(peak, active)
            elif event["payload"]["state"] == "SUCCEEDED":
                active -= 1
    assert peak == concurrency
    passed = await lab.store.list_records(handoff.run_id, "review")
    assert len(passed) == 2 and all(
        item["payload"]["status"] == "PASSED_WITHOUT_MODEL" for item in passed
    )
    assert len(lab.client.requests) == 4
    value = await lab.files.read_json(
        handoff.run_id, FileRef.model_validate(result["outputs"]["answer"])
    )
    assert [item["value"]["n"] for item in value] == [1, 2, 3]


async def test_condition_skips_unneeded_agent_and_makes_no_attempt(lab):
    pipeline(
        lab,
        [("optional", "unrelated"), ("answer", "echo")],
        """async def run(sdk, inputs):
    if inputs["task"]["goal"] == "optional request":
        unused = await sdk.call("optional", {})
    result = await sdk.call("answer", {"value": {"used": True}})
    return {"answer": result["value"]}
""",
    )
    handoff, _, result = await execute(lab)
    assert result["states"] == {"optional": "SKIPPED", "answer": "SUCCEEDED"}
    assert len(await lab.store.list_records(handoff.run_id, "tool_attempt")) == 1


@pytest.mark.parametrize("handled", [True, False])
async def test_confirmed_failure_can_use_prewritten_fallback_only(lab, handled):
    recovery = ', handles=["fail"]' if handled else ""
    pipeline(
        lab,
        [("fail", "fail"), ("fallback", "echo")],
        f"""async def run(sdk, inputs):
    first = await sdk.call("fail", {{"message": "test failure"}})
    if first["state"] == "FAILED":
        result = await sdk.call("fallback",
            {{"value": {{"code": first["error"]["code"]}}}}{recovery})
        return {{"answer": result["value"]}}
    return {{"answer": first["value"]}}
""",
    )
    _, _, result = await execute(lab)
    assert result["status"] == ("COMPLETED" if handled else "FAILED")
    assert result["states"] == {"fail": "FAILED", "fallback": "SUCCEEDED"}
    assert len(lab.client.requests) == 4


async def test_unknown_outcome_stops_instead_of_using_fallback(lab, monkeypatch):
    pipeline(
        lab,
        [("first", "echo"), ("fallback", "echo")],
        """async def run(sdk, inputs):
    first = await sdk.call("first", {"value": {}})
    fallback = await sdk.call("fallback", {"value": {"should_not_run": True}}, handles=["first"])
    return {"answer": fallback["value"]}
""",
    )
    original = Connections.call

    async def unknown(self, server, name, arguments, operation_id, **kwargs):
        await original(self, server, name, arguments, operation_id, **kwargs)
        raise ConnectionError("lost reply")

    monkeypatch.setattr(Connections, "call", unknown)
    lab.budget.limits = lab.budget.limits.model_copy(update={"transport_retries": 0})
    handoff = await lab.planner.plan("Complete task", [lab.source], mode="P1")
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == "OUTCOME_UNKNOWN"
    assert (await lab.store.run(handoff.run_id))["status"] == "UNCERTAIN"
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1 and attempts[0]["payload"]["status"] == "UNCERTAIN"


@pytest.mark.parametrize(
    "source,code",
    [
        (
            "async def run(sdk, inputs):\n"
            '    result = await sdk.call("one", {"value": {}})\n'
            '    return {"wrong": result["value"]}\n',
            "PROGRAM_OUTPUT",
        ),
        (
            "async def run(sdk, inputs):\n"
            '    result = await sdk.call("one", {"value": {}})\n'
            '    return {"answer": result["missing"]}\n',
            "PROGRAM_FAILED",
        ),
        (
            "async def run(sdk, inputs):\n"
            '    result = await sdk.call("one", {"value": {"id": "private", '
            '"run_id": "other", "kind": "json", "sha256": '
            '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}})\n'
            '    return {"answer": result["value"]}\n',
            "FILE_SCOPE",
        ),
    ],
)
async def test_bad_output_or_unreceived_reference_fails_and_cleans_container(lab, source, code):
    pipeline(lab, [("one", "echo")], source)
    handoff = await lab.planner.plan("Complete task", [lab.source], mode="P1")
    with pytest.raises(OrchestrationError) as error:
        await engine(lab).run(handoff)
    assert error.value.code == code
    assert (await lab.store.run(handoff.run_id))["status"] == "FAILED"
    diagnostics = await lab.store.list_records(handoff.run_id, "program_diagnostics")
    assert diagnostics[0]["payload"]["cleanup"] == "REMOVED"


async def test_cancellation_kills_owned_container_and_preserves_attempt(lab):
    pipeline(
        lab,
        [("slow", "echo")],
        """async def run(sdk, inputs):
    result = await sdk.call("slow", {"value": {}, "delay": 2})
    return {"answer": result["value"]}
""",
    )
    handoff = await lab.planner.plan("Complete task", [lab.source], mode="P1")
    task = asyncio.create_task(engine(lab).run(handoff))
    for _ in range(300):
        attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
        if attempts:
            break
        await asyncio.sleep(0.05)
    assert attempts and attempts[0]["payload"]["status"] == "RUNNING"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await lab.store.run(handoff.run_id))["status"] == "INTERRUPTED"
    diagnostics = await lab.store.list_records(handoff.run_id, "program_diagnostics")
    assert diagnostics[0]["payload"]["cleanup"] == "REMOVED"
    assert (await lab.store.list_records(handoff.run_id, "tool_attempt"))[0]["payload"][
        "status"
    ] == "UNCERTAIN"


async def test_stale_image_is_refused_before_any_execution(lab, monkeypatch):
    from mcp_execution_lab.orchestration import program_container

    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P1")
    real = program_container.sdk_identity
    monkeypatch.setattr(program_container, "sdk_identity", lambda: "changed-" + real())
    with pytest.raises(OrchestrationError, match="SDK changed"):
        await engine(lab).run(handoff)
    assert (await lab.store.run(handoff.run_id))["status"] == "READY_FOR_EXECUTION"
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")


async def test_no_agent_is_forced_for_metadata_only_question(lab):
    pipeline(
        lab,
        [],
        """async def run(sdk, inputs):
    return {"answer": {"goal": inputs["task"]["goal"]}}
""",
    )
    handoff, _, result = await execute(lab, rules=reviews())
    assert result["status"] == "COMPLETED" and result["states"] == {}
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert (
        len(
            [
                item
                for item in await lab.store.history(handoff.run_id)
                if item["kind"] == "review_unreached"
            ]
        )
        == 2
    )


async def test_unreceived_same_run_artifact_cannot_be_used_in_final_output(lab):
    pipeline(lab, [("one", "echo")], "placeholder")
    original = lab.client.generate

    async def generate(request, directory):
        if request["stage"] == "program":
            hidden = await lab.files.put_json(directory.parent.parent.name, {"undisclosed": True})
            assert hidden.id not in json.dumps(request)
            # Simulate a guessed reference that exists but was never supplied to Python.
            lab.client.overrides["program"] = {
                "source": "async def run(sdk, inputs):\n"
                '    result = await sdk.call("one", {"value": {}})\n'
                f'    return {{"answer": {hidden.model_dump()!r}}}\n',
                "outputs": ["answer"],
            }
        return await original(request, directory)

    lab.client.generate = generate
    handoff = await lab.planner.plan("Complete task", [lab.source], mode="P1")
    runner = engine(lab)
    with pytest.raises(OrchestrationError) as error:
        await runner.run(handoff)
    assert error.value.code == "FILE_SCOPE"


@pytest.mark.parametrize(
    "case", ["tool_budget", "invalid_handles", "unexpected", "time_limit", "save_failure"]
)
async def test_budget_gate_and_unexpected_failures_stop_cleanly(lab, monkeypatch, case):
    extra = ', handles=["one"]' if case == "invalid_handles" else ""
    pipeline(
        lab,
        [("one", "echo"), ("two", "echo")],
        f"""async def run(sdk, inputs):
    first = await sdk.call("one", {{"value": {{}}, "delay": 0.2}})
    second = await sdk.call("two", {{"value": {{}}}}{extra})
    return {{"answer": second["value"]}}
""",
    )
    if case == "tool_budget":
        lab.budget.limits = lab.budget.limits.model_copy(update={"max_tool_attempts": 1})
    handoff = await lab.planner.plan("Complete task", [lab.source], mode="P1")
    if case == "unexpected":

        async def broken(*args, **kwargs):
            raise RuntimeError("unexpected fixture failure")

        monkeypatch.setattr(Connections, "call", broken)
        # An unconfirmed transport exception correctly becomes OUTCOME_UNKNOWN.
    elif case == "time_limit":
        original = Connections.call

        async def expire(self, *args, **kwargs):
            lab.budget.started -= lab.budget.limits.run_seconds
            return await original(self, *args, **kwargs)

        monkeypatch.setattr(Connections, "call", expire)
    elif case == "save_failure":
        original = lab.store.finish

        async def unavailable(run_id, record_id, payload):
            row = await lab.store.get(run_id, record_id)
            if row["kind"] == "tool_attempt" and payload["status"] == "SUCCEEDED":
                raise RuntimeError("simulated database write outage")
            return await original(run_id, record_id, payload)

        monkeypatch.setattr(lab.store, "finish", unavailable)
    if case == "tool_budget":
        result = await engine(lab).run(handoff)
        assert result["status"] == "FAILED" and result["states"]["two"] == "FAILED"
    else:
        with pytest.raises((OrchestrationError, TimeoutError, RuntimeError)):
            await engine(lab).run(handoff)
    diagnostics = await lab.store.list_records(handoff.run_id, "program_diagnostics")
    assert diagnostics[0]["payload"]["cleanup"] == "REMOVED"
    attempts = await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert len(attempts) == 1
    assert (await lab.store.run(handoff.run_id))["status"] in {"FAILED", "UNCERTAIN"}
    if case == "save_failure":
        result = (await lab.store.list_records(handoff.run_id, "execution_result"))[-1]["payload"]
        assert result["states"]["one"] == "FAILED"
