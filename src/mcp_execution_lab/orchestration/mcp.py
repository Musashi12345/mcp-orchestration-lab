"""Configured MCP servers discovered through the official SDK, with run-local sessions."""

import asyncio
import os
import sys
from contextlib import AsyncExitStack

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .models import OrchestrationError, ServerConfig, ToolCache, ToolDefinition


def check_schema(schema):
    Draft202012Validator.check_schema(schema)

    def local_references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef"} and not str(item).startswith("#"):
                    raise OrchestrationError(
                        "TOOL_SCHEMA", "External schema references are unsupported."
                    )
                local_references(item)
        elif isinstance(value, list):
            for item in value:
                local_references(item)

    local_references(schema)


class Connections:
    def __init__(self, servers: list[ServerConfig], *, initial_ids=None):
        if len({server.id for server in servers}) != len(servers):
            raise OrchestrationError("SERVER_CONFIG", "Configured server IDs must be unique.")
        self.config = servers
        self.initial_ids = {server.id for server in servers} if initial_ids is None else initial_ids
        self.sessions = {}
        self.server_info = {}
        self.owners = {}
        self.lock = asyncio.Lock()

    async def _own_session(self, server, ready, stop):
        # Official stdio/session contexts must open and close in the same task.
        try:
            async with AsyncExitStack() as stack:
                if server.transport == "streamable-http":
                    read, write = await stack.enter_async_context(
                        streamable_http_client(server.url)
                    )
                else:
                    params = StdioServerParameters(
                        command=server.command.replace("{python}", sys.executable),
                        args=[value.replace("{python}", sys.executable) for value in server.args],
                        env={
                            name: os.environ[name]
                            for name in [*server.env_names, "WINDIR", "SYSTEMROOT"]
                            if name in os.environ
                        },
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                initialized = await session.initialize()
                self.sessions[server.id] = session
                self.server_info[server.id] = {
                    "protocol_version": initialized.protocol_version,
                    "server_info": initialized.server_info.model_dump(mode="json"),
                }
                ready.set_result(None)
                await stop.wait()
        except BaseException as exc:
            if not ready.done():
                if isinstance(exc, asyncio.CancelledError):
                    ready.cancel()
                else:
                    ready.set_exception(exc)
            raise

    async def ensure(self, server_ids):
        configured = {server.id: server for server in self.config}
        if not set(server_ids) <= configured.keys():
            raise OrchestrationError(
                "SERVER_CONFIG", "A required server has no project configuration."
            )
        for server_id in sorted(server_ids):
            async with self.lock:
                if server_id not in self.owners:
                    ready = asyncio.get_running_loop().create_future()
                    stop = asyncio.Event()
                    task = asyncio.create_task(
                        self._own_session(configured[server_id], ready, stop)
                    )
                    self.owners[server_id] = (task, ready, stop)
                task, ready, _ = self.owners[server_id]
            await asyncio.shield(ready)
            if task.done():
                raise OrchestrationError(
                    "SERVER_CONNECTION", "A server session ended unexpectedly."
                )

    async def __aenter__(self):
        try:
            await self.ensure(self.initial_ids)
            return self
        except BaseException:
            await self.__aexit__()
            raise

    async def __aexit__(self, *exc):
        tasks = []
        for task, ready, stop in self.owners.values():
            stop.set()
            if not ready.done():
                task.cancel()
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def discover(self) -> ToolCache:
        definitions = []
        for server_id, session in self.sessions.items():
            cursor, visited, seen = None, set(), set()
            for _ in range(100):
                page = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
                for tool in page.tools:
                    if tool.name in seen:
                        raise OrchestrationError(
                            "TOOL_DISCOVERY", "Duplicate tool name on one server."
                        )
                    seen.add(tool.name)
                    check_schema(tool.input_schema)
                    if tool.output_schema is not None:
                        check_schema(tool.output_schema)
                    description = tool.description or "No description supplied by the server."
                    definitions.append(
                        ToolDefinition(
                            server=server_id,
                            name=tool.name,
                            description=description,
                            plain_description=description,
                            capabilities=[description],
                            raw_definition=tool.model_dump(mode="json", exclude_none=True),
                            input_schema=tool.input_schema,
                            output_schema=tool.output_schema,
                            annotations=tool.annotations.model_dump(mode="json", exclude_none=True)
                            if tool.annotations
                            else {},
                        )
                    )
                cursor = page.next_cursor
                if cursor is None:
                    break
                if cursor in visited:
                    raise OrchestrationError("TOOL_DISCOVERY", "Repeated discovery page cursor.")
                visited.add(cursor)
            else:
                raise OrchestrationError("TOOL_DISCOVERY", "Discovery page allowance exhausted.")
        if not definitions:
            raise OrchestrationError("TOOL_DISCOVERY", "No tools were discovered.")
        return ToolCache(
            tools=sorted(definitions, key=lambda tool: tool.key), servers=self.server_info
        )

    async def verify(self, expected: ToolCache):
        if not self.sessions:
            return
        actual = await self.discover()
        selected = set(self.sessions)
        subset = ToolCache(
            tools=[tool for tool in expected.tools if tool.server in selected],
            servers={key: value for key, value in expected.servers.items() if key in selected},
        )
        if actual.digest != subset.digest:
            raise OrchestrationError("TOOLS_CHANGED", "MCP definitions changed after planning.")

    async def call(self, server, name, arguments, operation_id, *, worker_context=None):
        if server not in self.sessions:
            raise OrchestrationError(
                "SERVER_CONFIG", "Plan references a server without a connection."
            )
        metadata = {"lab_operation_id": operation_id}
        if worker_context:
            metadata["lab_worker_context"] = worker_context
        result = await self.sessions[server].call_tool(
            name,
            arguments,
            meta=types.RequestParamsMeta(**metadata),
        )
        return result.model_dump(mode="json")
