"""Only scoped worker support requests; no model credentials in MCP workers."""

import asyncio
import base64
import json
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from ...orchestration.models import OrchestrationError


class RunClient:
    def __init__(self, context):
        url = urlparse(context.get("url", ""))
        if url.scheme != "http" or url.hostname != "127.0.0.1" or url.path != "/worker":
            raise OrchestrationError(
                "WORKER_CONTEXT", "A local trusted worker context is required."
            )
        self.url, self.token = context["url"], context["token"]
        self.usage_ids = []

    async def request(self, action, **payload):
        data = json.dumps({"action": action, **payload}, allow_nan=False).encode()

        def send():
            request = Request(
                self.url,
                data,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Content-Type": "application/json",
                },
            )
            try:
                with build_opener(ProxyHandler({})).open(request, timeout=180) as response:
                    return json.loads(response.read(33554433))
            except HTTPError as exc:
                value = json.loads(exc.read(65536))
                raise OrchestrationError(
                    value.get("error", "WORKER_SERVICE"),
                    value.get("message", "Worker request failed."),
                ) from exc

        return await asyncio.to_thread(send)

    async def table(self, ref):
        from .models import Table

        return Table.model_validate(await self.request("read", ref=ref.model_dump()))

    async def json(self, ref):
        return await self.request("read", ref=ref.model_dump())

    async def model(self, purpose, context):
        response = await self.request("model", purpose=purpose, context=context)
        self.usage_ids.append(response["record_id"])
        return response["value"]

    async def stage(self, name, detail):
        return await self.request("stage", name=name, detail=detail)

    async def publish(self, value, kind="json"):
        from ...orchestration.models import FileRef

        data = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode()
        result = await self.request("publish", kind=kind, data=base64.b64encode(data).decode())
        return FileRef.model_validate(result)
