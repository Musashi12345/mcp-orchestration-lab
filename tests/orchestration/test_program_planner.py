import hashlib

import pytest
from pydantic import ValidationError

from mcp_execution_lab.orchestration.models import Handoff, OrchestrationError, PythonProgram
from mcp_execution_lab.program_sdk.policy import validate_source


def count_program(context):
    dataset = context["datasets"][0]["ref"]["id"]
    return {
        "source": f'''async def run(sdk, inputs):
    count = await sdk.call("count", {{"dataset": inputs["datasets"]["{dataset}"]}})
    answer = await sdk.call("answer", {{"summary": count["value"]}})
    return {{"answer": answer["value"]}}
''',
        "outputs": ["answer"],
    }


async def test_p1_planning_is_direct_python_with_saved_source_and_no_tool_execution(lab):
    lab.client.overrides["program"] = lambda request: count_program(request["context"])
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P1")
    assert handoff.plan is None and handoff.program
    assert not await lab.store.list_records(handoff.run_id, "plan")
    assert not await lab.store.list_records(handoff.run_id, "tool_attempt")
    assert [item["stage"] for item in lab.client.requests] == [
        "main_task",
        "tool_selection",
        "subtasks",
        "program",
    ]
    record = await lab.store.get(handoff.run_id, handoff.plan_record)
    assert record["kind"] == "program"
    assert (
        record["payload"]["source"]["sha256"]
        == hashlib.sha256(handoff.program.source.encode()).hexdigest()
    )
    assert Handoff.model_validate(handoff.model_dump()) == handoff
    with pytest.raises(ValidationError):
        Handoff.model_validate(handoff.model_dump() | {"mode": "D1"})
    assert "fixture/profile" not in lab.client.requests[-1]["instructions"]
    assert "Docker" not in lab.client.requests[0]["instructions"]


async def test_pre_execution_correction_retains_candidates_and_errors(lab):
    attempts = []

    def reply(request):
        program = count_program(request["context"])
        if not attempts:
            program["source"] = "import os\n" + program["source"]
        attempts.append(request)
        return program

    lab.client.overrides["program"] = reply
    handoff = await lab.planner.plan("Count rows", [lab.source], mode="P1")
    assert len(attempts) == 2
    assert attempts[-1]["context"]["validation_errors"]
    assert len(await lab.store.list_records(handoff.run_id, "validation")) == 1
    assert (
        len(
            [
                item
                for item in await lab.store.list_records(handoff.run_id, "candidate")
                if item["payload"]["stage"] == "program"
            ]
        )
        == 2
    )


@pytest.mark.parametrize(
    "body",
    [
        "import os",
        "while True: pass",
        "for x in []: pass",
        "x = [x for x in []]",
        "x = inputs.__class__",
        "x = len(inputs)",
        "inputs['x'] = 2",
        "sdk = inputs",
        "return sdk",
        "return {'answer': 1e999}",
        "return {'answer': b'x'}",
        "return {'answer': 1 + 2}",
        "def helper(): pass",
        "raise ValueError()",
    ],
)
def test_unsupported_language_is_rejected_without_execution(body):
    with pytest.raises(ValueError):
        validate_source("async def run(sdk, inputs):\n    " + body + "\n", set())


def test_calls_must_match_jobs_once_and_parallel_calls_must_be_awaited():
    for body, jobs in [
        ("await sdk.call('other', {})", {"one"}),
        ("sdk.call('one', {})", {"one"}),
        ("sdk.parallel(sdk.call('one', {}))", {"one"}),
        ("await sdk.call('one', {})\n    await sdk.call('one', {})", {"one"}),
        ("return {}", {"missing"}),
    ]:
        with pytest.raises(ValueError):
            validate_source(f"async def run(sdk, inputs):\n    {body}\n    return {{}}\n", jobs)
    with pytest.raises(ValidationError):
        PythonProgram(source="x", outputs=["answer", "answer"])


async def test_unsupported_p2_stays_unavailable(lab):
    with pytest.raises(OrchestrationError, match="Supported modes"):
        await lab.planner.plan("Count rows", [lab.source], mode="P2")
