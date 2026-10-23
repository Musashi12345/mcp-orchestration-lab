import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from mcp_execution_lab.orchestration.config import ModelConfig, Settings
from mcp_execution_lab.orchestration.models import ServerConfig
from mcp_execution_lab.orchestration.service import Application
from mcp_execution_lab.orchestration.storage import Store

from .workers import AgentModel


async def test_actual_worker_execution_over_official_http_mcp(tmp_path):
    for _ in range(50):
        port = 10000 + secrets.randbelow(20000)
        with socket.socket() as probe:
            try:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
                break
            except OSError:
                continue
    else:
        raise RuntimeError("No test port available")
    token = secrets.token_urlsafe(32)
    instance = secrets.token_hex(16)
    root = Path(__file__).resolve().parents[2]
    log = (tmp_path / "http_worker.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_execution_lab.agents.understanding.server",
            "--port",
            str(port),
            "--instance",
            instance,
        ],
        cwd=root,
        stdout=log,
        stderr=log,
        env=os.environ | {"MCP_LAB_ADMIN_TOKEN": token},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    opener = build_opener(ProxyHandler({}))

    def health():
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
            return json.load(response)

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        for _ in range(100):
            try:
                value = await asyncio.to_thread(health)
                if value["instance"] == instance:
                    break
            except OSError:
                pass
            if process.poll() is not None:
                raise RuntimeError("HTTP worker exited; inspect its test log.")
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("HTTP worker did not become ready.")
        await store.initialize()
        settings = Settings(
            servers=[
                ServerConfig(
                    id="worker", transport="streamable-http", url=f"http://127.0.0.1:{port}/mcp"
                )
            ],
            model=ModelConfig(provider="command", model_id="test"),
        )
        source = tmp_path / "input.csv"
        source.write_text("id,amount\na,10\nb,20\n", encoding="utf-8")
        app = Application(
            store,
            tmp_path / "data",
            settings,
            client=AgentModel(store, "data_understanding", "understand_data"),
        )
        handoff = await app.plan("Explain the input", [source])
        result = await app.execute(handoff.run_id)
        assert result["status"] == "COMPLETED" and result["metrics"]["model_calls"] == 6
    finally:
        await store.close()
        try:
            request = Request(
                f"http://127.0.0.1:{port}/shutdown",
                data=b"",
                headers={"Authorization": "Bearer " + token},
            )
            response = await asyncio.to_thread(opener.open, request, timeout=2)
            response.close()
        except OSError:
            pass
        try:
            await asyncio.to_thread(process.wait, timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                )
            else:
                process.kill()
            await asyncio.to_thread(process.wait, timeout=5)
        log.close()
