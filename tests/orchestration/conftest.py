import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_execution_lab.orchestration.budget import Budget
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.model import ModelCalls
from mcp_execution_lab.orchestration.models import Limits, ServerConfig
from mcp_execution_lab.orchestration.planner import Planner
from mcp_execution_lab.orchestration.storage import Store


def example_records(context):
    dataset = context["datasets"][0]["ref"]["id"]
    selection = {
        "tool_keys": ["fixture/profile", "fixture/present"],
        "reasons": ["Count rows", "Return answer"],
    }
    subtasks = [
        {
            "id": "count",
            "tool_key": "fixture/profile",
            "job": "Count the supplied rows",
            "expected_outputs": ["row_count"],
        },
        {
            "id": "answer",
            "tool_key": "fixture/present",
            "job": "Present the count",
            "expected_outputs": ["answer"],
        },
    ]
    return {
        "main_task": {
            "goal": context.get("original_request", "Count rows"),
            "dataset_ids": [dataset],
            "required_outputs": ["answer"],
        },
        "tool_selection": selection,
        "subtasks": {"selection": selection, "subtasks": subtasks},
        "dag": {
            "steps": [
                {
                    "id": "count",
                    "subtask_id": "count",
                    "server": "fixture",
                    "tool": "profile",
                    "arguments": {"dataset": {"kind": "dataset", "key": dataset}},
                },
                {
                    "id": "answer",
                    "subtask_id": "answer",
                    "server": "fixture",
                    "tool": "present",
                    "depends_on": ["count"],
                    "arguments": {"summary": {"kind": "step", "key": "count"}},
                },
            ],
            "outputs": {"answer": {"kind": "step", "key": "answer"}},
        },
        "review": {"decision": "KEEP", "reason": "The current plan remains suitable."},
    }


class ScriptedModel:
    provider = "scripted-test"
    is_model = False

    def __init__(self, store, overrides=None):
        self.store = store
        self.overrides = overrides or {}
        self.requests = []

    async def generate(self, request, directory):
        self.requests.append(request)
        run_id = directory.parent.parent.name
        records = await self.store.list_records(run_id, "model_call")
        assert records[-1]["payload"]["status"] == "RUNNING"
        assert await self.store.list_records(run_id, "configuration")
        assert len((await self.store.run(run_id))["payload"]["source_sha256"]) == 64
        stage = request["stage"]
        if stage in self.overrides:
            override = self.overrides[stage]
            result = override(request) if callable(override) else override
        else:
            result = example_records(request["context"])[stage]
        return {
            "content": {"content_json": json.dumps(result)},
            "usage": {"input_tokens": 5, "output_tokens": 5},
            "request_id": directory.name,
        }


@pytest.fixture
async def lab(tmp_path, monkeypatch):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    limits = Limits(run_seconds=60)
    files = Files(tmp_path / "files", store, limits)
    monkeypatch.setenv("MCP_LAB_DATA_ROOT", str(files.root))
    server_path = Path(__file__).resolve().parents[1] / "mcp_analysis_server.py"
    servers = [
        ServerConfig(
            id="fixture",
            command="{python}",
            args=[str(server_path)],
            env_names=["MCP_LAB_DATA_ROOT"],
        )
    ]
    budget = Budget(limits)
    client = ScriptedModel(store)
    config = SimpleNamespace(model_id="scripted", timeout_seconds=20)
    model = ModelCalls(client, config, store, files, budget)
    planner = Planner(store, files, model, budget, servers)
    source = tmp_path / "orders.csv"
    source.write_text("product,amount\na,10\nb,20\n", encoding="utf-8")
    try:
        yield SimpleNamespace(
            store=store,
            files=files,
            limits=limits,
            budget=budget,
            client=client,
            model=model,
            planner=planner,
            servers=servers,
            source=source,
        )
    finally:
        await store.close()
