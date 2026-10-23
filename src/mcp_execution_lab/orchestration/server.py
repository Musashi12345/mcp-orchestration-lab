"""Authenticated local API for planning/executing data-analysis runs and discovery."""

import argparse
import hmac
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..agents.common.registry import MODULES
from .config import load_settings, local_environment
from .mcp import Connections
from .models import Record
from .service import Application
from .storage import Store, runs


class RunRequest(Record):
    query: str = Field(min_length=1, max_length=10000)
    csv_paths: list[str] = Field(min_length=1, max_length=8)
    mode: str = "D1"
    plan_only: bool = False
    encoding: str = "utf-8-sig"
    delimiter: str = ","


def create_app(settings, token, instance="manual", root=None, client=None):
    root = Path(root or Path.cwd()).resolve()
    holder = {}

    def authorized(request):
        return bool(token) and hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        )

    async def health(request):
        load_dotenv(root / ".env", override=False)
        url = os.environ.get("MCP_LAB_DATABASE_URL", "")
        return JSONResponse(
            {
                "status": "READY",
                "service": "orchestrator",
                "pid": os.getpid(),
                "instance": instance,
                "database": "CONFIGURED" if url and "YOUR_" not in url else "NOT_CONFIGURED",
                "note": "Database connectivity is checked when a run or inspection is requested.",
                "endpoints": ["/health", "/tools", "/runs", "/runs/{run_id}"],
            }
        )

    async def shutdown(request):
        if not authorized(request):
            return JSONResponse({"error": "UNAUTHORIZED"}, 403)
        holder["server"].should_exit = True
        return JSONResponse({"status": "STOPPING"})

    async def endpoint(request):
        if not authorized(request):
            return JSONResponse({"error": "UNAUTHORIZED"}, 403)
        store = None
        try:
            if request.url.path == "/tools":
                async with Connections(settings.servers) as connections:
                    return JSONResponse((await connections.discover()).model_dump(mode="json"))
            url, data_root = local_environment(root)
            store = Store(url)
            await store.initialize()
            app = Application(store, data_root, settings, client=client)
            run_id = request.path_params.get("run_id")
            if request.method == "GET" and run_id:
                return JSONResponse(
                    {
                        "run": await store.run(run_id),
                        "records": await store.list_records(run_id),
                        "events": await store.history(run_id),
                    }
                )
            if request.method == "GET":
                rows = await store.transact(
                    lambda connection: [
                        dict(row)
                        for row in connection.execute(
                            select(runs).order_by(runs.c.created_at.desc()).limit(50)
                        ).mappings()
                    ]
                )
                return JSONResponse({"runs": rows})
            if run_id:
                return JSONResponse(await app.execute(run_id))
            if int(request.headers.get("content-length", "0")) > 65536:
                return JSONResponse({"error": "REQUEST_SIZE"}, 413)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse({"error": "REQUEST_SIZE"}, 413)
            value = RunRequest.model_validate_json(body)
            handoff = await app.plan(
                value.query,
                [
                    (Path(path) if Path(path).is_absolute() else root / path).resolve()
                    for path in value.csv_paths
                ],
                mode=value.mode,
                encoding=value.encoding,
                delimiter=value.delimiter,
            )
            if value.plan_only:
                return JSONResponse(
                    {
                        "status": "READY_FOR_EXECUTION",
                        "run_id": handoff.run_id,
                        "handoff": handoff.model_dump(mode="json"),
                    }
                )
            return JSONResponse(await app.execute(handoff.run_id))
        except SQLAlchemyError:
            return JSONResponse(
                {
                    "error": "DATABASE_ERROR",
                    "message": "Check the local PostgreSQL connection in .env.",
                },
                503,
            )
        except (ValueError, OSError, TimeoutError) as exc:
            return JSONResponse(
                {"error": getattr(exc, "code", type(exc).__name__), "message": str(exc)[:2000]}, 400
            )
        finally:
            if store:
                await store.close()

    app = Starlette(
        routes=[
            Route("/", health),
            Route("/health", health),
            Route("/shutdown", shutdown, methods=["POST"]),
            Route("/tools", endpoint),
            Route("/runs", endpoint, methods=["GET", "POST"]),
            Route("/runs/{run_id}", endpoint),
            Route("/runs/{run_id}/execute", endpoint, methods=["POST"]),
        ]
    )
    app.state.server_holder = holder
    return app


def main():
    parser = argparse.ArgumentParser(description="Local data-analysis orchestrator")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--base-port", type=int, default=8766)
    parser.add_argument("--instance", default="manual")
    parser.add_argument("--config", type=Path, default=Path("configs/agents.yaml"))
    args = parser.parse_args()
    settings = load_settings(args.config)
    servers = []
    offsets = {role: index + 1 for index, role in enumerate(MODULES)}
    for server in settings.servers:
        if server.id in offsets and server.transport == "streamable-http":
            server = server.model_copy(
                update={"url": f"http://127.0.0.1:{args.base_port + offsets[server.id]}/mcp"}
            )
        servers.append(server)
    settings = settings.model_copy(update={"servers": servers})
    token = os.environ.get("MCP_LAB_ADMIN_TOKEN", "")
    if not token:
        parser.error(
            "Use start_agents.ps1, or supply MCP_LAB_ADMIN_TOKEN in the process environment."
        )
    app = create_app(settings, token, args.instance)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=3,
        )
    )
    app.state.server_holder["server"] = server
    server.run()


if __name__ == "__main__":
    main()
