"""Official MCP server bootstrap: stdio for owned children, HTTP for the service scripts."""

import argparse
import hmac
import os

import uvicorn
from mcp import types
from mcp.server import MCPServer
from starlette.responses import JSONResponse

from ...orchestration.provenance import source_identity
from .client import RunClient


def run_client(context):
    meta = context.request_context.meta
    metadata = meta if isinstance(meta, dict) else (meta.model_dump() if meta else {})
    value = metadata.get("lab_worker_context")
    if not isinstance(value, dict):
        raise ValueError("This agent must be called through the project execution broker.")
    return RunClient(value)


def serve(role, function):
    parser = argparse.ArgumentParser(description=role + " MCP server")
    parser.add_argument("--port", type=int)
    parser.add_argument("--instance", default="manual")
    args = parser.parse_args()
    loaded_source = source_identity()["source_sha256"]
    server = MCPServer(role.replace("_", "-"), version="0.1.0")
    server.tool(
        annotations=types.ToolAnnotations(
            read_only_hint=False, idempotent_hint=False, open_world_hint=False
        ),
        meta={"lab_worker_role": role, "lab_worker_source_sha256": loaded_source},
    )(function)
    holder = {}

    @server.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse(
            {
                "status": "READY",
                "service": role,
                "pid": os.getpid(),
                "instance": args.instance,
                "version": "0.1.0",
                "source_sha256": loaded_source,
            }
        )

    @server.custom_route("/shutdown", methods=["POST"])
    async def shutdown(request):
        token = os.environ.get("MCP_LAB_ADMIN_TOKEN", "")
        if not token or not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            return JSONResponse({"error": "UNAUTHORIZED"}, 403)
        holder["server"].should_exit = True
        return JSONResponse({"status": "STOPPING"})

    if args.port is None:
        server.run(transport="stdio")
    else:
        app = server.streamable_http_app(stateless_http=True)
        holder["server"] = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=args.port,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=3,
            )
        )
        holder["server"].run()
