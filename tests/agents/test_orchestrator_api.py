import asyncio
import json
import os

import pytest
from orchestration.postgres import LocalPostgres

from mcp_execution_lab.orchestration.config import ModelConfig, Settings
from mcp_execution_lab.orchestration.models import ServerConfig
from mcp_execution_lab.orchestration.server import create_app
from mcp_execution_lab.orchestration.storage import Store

from .workers import AgentModel


async def call(app, path, method="GET", body=None, token="test-admin"):
    messages = []
    raw = json.dumps(body).encode() if body is not None else b""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [
            (b"authorization", ("Bearer " + token).encode()),
            (b"content-length", str(len(raw)).encode()),
            (b"content-type", b"application/json"),
        ],
        "server": ("127.0.0.1", 8766),
        "client": ("127.0.0.1", 1),
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )
    content = b"".join(message.get("body", b"") for message in messages)
    return status, json.loads(content)


@pytest.mark.skipif(
    os.environ.get("MCP_LAB_POSTGRES_TEST") != "1", reason="Native PostgreSQL opt-in required."
)
@pytest.mark.parametrize("mode", ["D1", "P1"])
async def test_orchestrator_api_plans_executes_and_reads_the_same_run(tmp_path, monkeypatch, mode):
    if mode == "P1" and os.environ.get("MCP_LAB_DOCKER_TEST") != "1":
        pytest.skip("Real Docker opt-in required for P1.")
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres").start)
    store = Store(cluster.url)
    monkeypatch.setenv("MCP_LAB_DATABASE_URL", cluster.url)
    monkeypatch.setenv("MCP_LAB_DATA_ROOT", str(tmp_path / "files"))
    try:
        await store.initialize()
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
        model = AgentModel(store, "data_understanding", "understand_data")
        app = create_app(settings, "test-admin", root=tmp_path, client=model)
        (tmp_path / "sample.csv").write_text("id,amount\n001,10\n002,20\n", encoding="utf-8")
        status, _ = await call(app, "/runs", token="incorrect")
        assert status == 403 and not model.requests
        status, _ = await call(app, "/runs", "POST", {"query": "x" * 65536})
        assert status == 413 and not model.requests
        status, planned = await call(
            app,
            "/runs",
            "POST",
            {
                "query": "Explain this file",
                "csv_paths": ["sample.csv"],
                "plan_only": True,
                "mode": mode,
            },
        )
        assert status == 200 and planned["status"] == "READY_FOR_EXECUTION"
        run_id = planned["run_id"]
        assert len(model.requests) == 4
        assert model.requests[-1]["stage"] == ("program" if mode == "P1" else "dag")
        status, result = await call(app, f"/runs/{run_id}/execute", "POST")
        assert status == 200 and result["status"] == "COMPLETED"
        assert len(model.requests) == 6
        status, saved = await call(app, f"/runs/{run_id}")
        assert status == 200 and saved["run"]["id"] == run_id
        assert any(row["kind"] == "worker_call" for row in saved["records"])
        status, listing = await call(app, "/runs")
        assert status == 200 and [row["id"] for row in listing["runs"]] == [run_id]
        status, _ = await call(app, f"/runs/{run_id}/execute", "POST")
        assert status == 400 and len(model.requests) == 6
    finally:
        await store.close()
        await asyncio.to_thread(cluster.close)
