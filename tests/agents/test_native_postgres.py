import asyncio
import json
import os

import pytest
from orchestration.postgres import LocalPostgres

from mcp_execution_lab.orchestration.config import ModelConfig, Settings
from mcp_execution_lab.orchestration.models import ServerConfig
from mcp_execution_lab.orchestration.service import Application
from mcp_execution_lab.orchestration.storage import Store

from .workers import AgentModel


@pytest.mark.skipif(
    os.environ.get("MCP_LAB_POSTGRES_TEST") != "1", reason="Native PostgreSQL opt-in required."
)
async def test_worker_calls_are_visible_during_execution_in_native_postgres(tmp_path):
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres").start)
    store = Store(cluster.url)
    observed = []
    try:
        await store.initialize()

        class VisibleModel(AgentModel):
            async def generate(self, request, directory):
                if request["role"] == "worker":
                    reader = Store(cluster.url)
                    try:
                        record = await reader.get(
                            directory.parent.parent.name, request["context"]["worker_call_id"]
                        )
                        assert record["payload"]["status"] == "RUNNING"
                        observed.append(record["id"])
                    finally:
                        await reader.close()
                return await super().generate(request, directory)

        client = VisibleModel(store, "data_understanding", "understand_data")
        settings = Settings(
            servers=[
                ServerConfig(
                    id="worker",
                    command="{python}",
                    args=["-m", "mcp_execution_lab.agents.understanding.server"],
                )
            ],
            model=ModelConfig(provider="command", model_id="deterministic-test"),
        )
        source = tmp_path / "sample.csv"
        source.write_text("id,amount\n001,10\n002,20\n", encoding="utf-8")
        app = Application(store, tmp_path / "files", settings, client=client)
        handoff = await app.plan("Explain this file", [source])
        result = await app.execute(handoff.run_id)
        assert result["status"] == "COMPLETED" and len(observed) == 2
        workers = await store.list_records(handoff.run_id, "worker_call")
        assert len(workers) == 1 and workers[0]["payload"]["model_calls"] == 2
        ids = workers[0]["payload"]["result"]["usage_record_ids"]
        assert len(ids) == 2
        for call_id in ids:
            assert (await store.get(handoff.run_id, call_id))["payload"]["parent_id"] == workers[0][
                "id"
            ]
        audit = {
            "run": await store.run(handoff.run_id),
            "result": result,
            "records": await store.list_records(handoff.run_id),
            "events": await store.history(handoff.run_id),
        }
        report = tmp_path / "audit.json"
        report.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    finally:
        await store.close()
        await asyncio.to_thread(cluster.close)
