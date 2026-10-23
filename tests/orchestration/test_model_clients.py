"""Provider bridge checks without subscription calls or pricing-pilot types."""

import json
import sys
from types import SimpleNamespace

import pytest

from mcp_execution_lab.orchestration.config import ModelConfig
from mcp_execution_lab.orchestration.model_clients import (
    CodexPlanner,
    CommandPlanner,
    bounded_process,
    make_planner,
    structured_schema,
)
from mcp_execution_lab.orchestration.models import (
    OrchestrationError,
    ReviewDecision,
    StructuredPayload,
)


def test_current_review_schema_is_strict_including_nullable_fields():
    schema = structured_schema(ReviewDecision)
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert "default" not in schema["properties"]["replacement"]
    assert {"type": "null"} in schema["properties"]["replacement"]["anyOf"]


def test_factory_supports_only_the_csv_model_routes():
    assert isinstance(make_planner(ModelConfig(provider="codex")), CodexPlanner)
    assert isinstance(make_planner(ModelConfig(provider="command")), CommandPlanner)
    with pytest.raises(OrchestrationError) as error:
        make_planner(SimpleNamespace(provider="reference"))
    assert error.value.code == "MODEL_CONFIG"


async def test_command_router_receives_current_protocol_and_retains_usage(tmp_path):
    # This is a fixed test router, not model-generated analysis code.
    script = (
        "import json,sys; request=json.load(sys.stdin); "
        "print(json.dumps({'content':request,'usage':{'input_tokens':3,'output_tokens':2},"
        "'request_id':'fixed-router'}))"
    )
    client = CommandPlanner(ModelConfig(provider="command", command=[sys.executable, "-c", script]))
    request = {"protocol": "orchestration.v1", "stage": "main_task", "role": "initial_planner"}
    result = await client.generate(request, tmp_path)
    assert result["content"] == request
    assert result["usage"] == {"input_tokens": 3, "output_tokens": 2}
    assert result["request_id"] == "fixed-router"
    assert result["provider"] == "command" and result["cost_usd"] is None
    assert (tmp_path / "router.stderr.txt").read_text() == ""


async def test_router_errors_use_the_current_orchestration_error(tmp_path):
    client = CommandPlanner(
        ModelConfig(provider="command", command=[sys.executable, "-c", "print('{}')"])
    )
    with pytest.raises(OrchestrationError) as error:
        await client.generate({"protocol": "orchestration.v1"}, tmp_path)
    assert error.value.code == "MODEL_RESULT_SCHEMA"


async def test_bounded_process_refuses_oversized_router_output(tmp_path):
    with pytest.raises(OrchestrationError) as error:
        await bounded_process(
            [sys.executable, "-c", "print('x'*2048)"],
            directory=tmp_path,
            payload="{}",
            timeout=10,
            stdout_limit=128,
        )
    assert error.value.code == "MODEL_RESPONSE_SIZE"


async def test_codex_requires_a_current_response_schema_before_starting(tmp_path, monkeypatch):
    client = CodexPlanner(ModelConfig(model_id="audit-model"))
    client.executable = "fixed-codex"

    async def forbidden(*args, **kwargs):
        raise AssertionError("A missing schema must not start a provider process.")

    monkeypatch.setattr("asyncio.create_subprocess_exec", forbidden)
    with pytest.raises(OrchestrationError) as error:
        await client.generate({"role": "worker"}, tmp_path)
    assert error.value.code == "MODEL_REQUEST_SCHEMA"


@pytest.mark.parametrize("tool_activity", [False, True])
async def test_codex_csv_response_and_tool_rejection_without_live_calls(
    tmp_path, monkeypatch, tool_activity
):
    client = CodexPlanner(ModelConfig(model_id="audit-model"))
    client.executable = "fixed-codex"
    request = {
        "protocol": "orchestration.v1",
        "role": "worker",
        "response_schema": structured_schema(StructuredPayload),
    }
    commands = []

    class LoginStatus:
        returncode = 0

        async def communicate(self):
            return b"Logged in with ChatGPT", b""

    async def login(*command, **kwargs):
        assert command == ("fixed-codex", "login", "status")
        return LoginStatus()

    async def response(command, *, directory, payload, timeout):
        commands.append(command)
        assert json.loads(payload) == request
        events = [
            {"type": "thread.started", "thread_id": "fixed-request"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": '{"content_json":"{}"}'},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 2}},
        ]
        if tool_activity:
            events.append({"type": "item.completed", "item": {"type": "command_execution"}})
        return 0, "\n".join(json.dumps(event) for event in events), "fixed diagnostic"

    monkeypatch.setattr("asyncio.create_subprocess_exec", login)
    monkeypatch.setattr("mcp_execution_lab.orchestration.model_clients.bounded_process", response)
    result = await client.generate(request, tmp_path)
    assert result["content"] == {"content_json": "{}"}
    assert result["usage"] == {"input_tokens": 7, "output_tokens": 2}
    assert result["cost_usd"] is None
    assert (result["failure"]["code"] if result["failure"] else None) == (
        "PLANNER_TOOL_VIOLATION" if tool_activity else None
    )
    command = commands[0]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command and "--ignore-user-config" in command
    assert command[command.index("--model") + 1] == "audit-model"
    assert json.loads((tmp_path / "response.schema.json").read_text()) == request["response_schema"]
    assert (tmp_path / "codex.stderr.txt").read_text() == "fixed diagnostic"
    assert (tmp_path / "codex.events.jsonl").is_file()
