"""Run-scoped model accounting, file publication, and worker receipts on loopback."""

import asyncio
import base64
import csv
import hmac
import json
import secrets
import socket
from contextlib import nullcontext
from dataclasses import dataclass, field

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ...orchestration.models import FileRef, OrchestrationError, canonical
from .models import Explanation
from .registry import WORKER_INSTRUCTIONS, definition


def references(value):
    if isinstance(value, dict):
        if {"id", "run_id", "kind", "sha256"} <= value.keys():
            yield FileRef.model_validate(value)
        else:
            for part in value.values():
                yield from references(part)
    elif isinstance(value, list):
        for part in value:
            yield from references(part)


@dataclass
class WorkerCall:
    id: str
    token: str
    role: str
    allowed: dict
    payload: dict
    calls: int = 0
    active: bool = True
    result: dict | None = None
    tasks: set = field(default_factory=set)
    claimed: bool = False


class WorkerGateway:
    def __init__(self, handoff, store, files, budget, model):
        self.handoff, self.store, self.files = handoff, store, files
        self.budget, self.model = budget, model
        self.contexts = {}
        self.server = self.task = self.sock = None

    async def __aenter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(128)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/worker"
        app = Starlette(routes=[Route("/worker", self.endpoint, methods=["POST"])])
        self.server = uvicorn.Server(
            uvicorn.Config(app, log_level="critical", timeout_graceful_shutdown=2, access_log=False)
        )
        self.server.capture_signals = nullcontext
        self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
        for _ in range(200):
            if self.server.started:
                return self
            if self.task.done():
                await self.task
                raise OrchestrationError("WORKER_SERVICE", "Worker support could not start.")
            await asyncio.sleep(0.01)
        raise OrchestrationError("WORKER_SERVICE", "Worker support startup timed out.")

    async def __aexit__(self, *_):
        for call in self.contexts.values():
            await self.close_call(call, "UNCERTAIN")
        if self.server:
            self.server.should_exit = True
        if self.task:
            await self.task
        if self.sock:
            self.sock.close()

    async def open(self, role, step, arguments, attempt_id, operation_id, job):
        definition(role)
        if arguments.get("job") != job:
            raise OrchestrationError("WORKER_JOB", "Worker job differs from its assigned subtask.")
        if self.model is None:
            raise OrchestrationError("MODEL_CONFIG", "Worker agents require a model route.")
        payload = {
            "status": "RUNNING",
            "role": role,
            "step_id": step.id,
            "operation_id": operation_id,
            "job": job,
            "attempt_id": attempt_id,
        }
        call_id = await self.store.put(
            self.handoff.run_id, "worker_call", payload, parents=[("attempt", attempt_id)]
        )
        call = WorkerCall(
            call_id,
            secrets.token_urlsafe(32),
            role,
            {ref.id: ref for ref in references(arguments)},
            payload,
        )
        self.contexts[call.token] = call
        return {"url": self.url, "token": call.token, "worker_call_id": call.id}

    async def close_call(self, call, status):
        call.active = False
        tasks = list(call.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if call.result is None and call.payload["status"] == "RUNNING":
            call.payload = call.payload | {"status": status}
            await self.store.finish(self.handoff.run_id, call.id, call.payload)

    async def accept(self, context, content):
        call = self.contexts[context["token"]]
        if call.result != content:
            raise OrchestrationError(
                "WORKER_RECEIPT", "MCP reply differs from the saved worker receipt."
            )

    async def endpoint(self, request: Request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        call = next(
            (item for key, item in self.contexts.items() if hmac.compare_digest(key, token)), None
        )
        if call is None or not call.active:
            return JSONResponse(
                {"error": "WORKER_CONTEXT", "message": "Inactive worker context."}, 403
            )
        task = asyncio.current_task()
        call.tasks.add(task)
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 33554432:
                    raise OrchestrationError(
                        "REQUEST_SIZE", "Worker request exceeded its allowance."
                    )
            value = json.loads(body)
            self.budget.check()
            result = await self.dispatch(call, value)
            return JSONResponse(result)
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse(
                {"error": getattr(exc, "code", "WORKER_REQUEST"), "message": str(exc)[:2000]}, 400
            )
        finally:
            call.tasks.discard(task)

    async def dispatch(self, call, value):
        run_id = self.handoff.run_id
        action = value["action"]
        if action == "claim":
            if call.result is not None:
                return {"result": call.result}
            if call.claimed:
                raise OrchestrationError(
                    "WORKER_IN_PROGRESS", "This worker operation is already running."
                )
            call.claimed = True
            await self.store.put(
                run_id, "worker_stage", {"name": "claimed"}, parents=[("worker", call.id)]
            )
            return {"status": "CLAIMED"}
        if call.result is not None:
            raise OrchestrationError("WORKER_STATE", "This worker call already finished.")
        if not call.claimed:
            raise OrchestrationError("WORKER_STATE", "Claim the worker operation before using it.")
        if action == "read":
            ref = FileRef.model_validate(value["ref"])
            if call.allowed.get(ref.id) != ref:
                raise OrchestrationError(
                    "FILE_OWNERSHIP", "File is not an input of this worker call."
                )
            path = await self.files.checked_path(run_id, ref)
            if ref.kind == "csv":
                if path.stat().st_size > 16777216:
                    raise OrchestrationError(
                        "WORKER_SIZE", "Worker inputs support at most 16 MiB per CSV."
                    )
                registered = await self.store.get(run_id, ref.id)
                dataset = registered["payload"]["dataset"]
                if dataset["row_count"] > self.budget.limits.worker_max_rows:
                    raise OrchestrationError(
                        "WORKER_ROWS", "Dataset exceeds the worker row allowance."
                    )

                def read():
                    with path.open(encoding=dataset["encoding"], newline="") as stream:
                        return list(csv.DictReader(stream, delimiter=dataset["delimiter"]))

                rows = await asyncio.to_thread(read)
                response = {"ref": ref.model_dump(), "columns": dataset["columns"], "rows": rows}
                if len(canonical(response)) > 30000000:
                    raise OrchestrationError(
                        "WORKER_SIZE", "Expanded CSV exceeds the message allowance."
                    )
                return response
            if ref.kind == "json":
                data = await self.files.read_json(run_id, ref)
                for nested in references(data):
                    await self.files.checked_path(run_id, nested)
                    call.allowed[nested.id] = nested
                return data
            return {"ref": ref.model_dump(), "size_bytes": path.stat().st_size}
        if action == "stage":
            record_id = await self.store.put(
                run_id,
                "worker_stage",
                {
                    "name": value["name"],
                    "detail": value["detail"],
                },
                parents=[("worker", call.id)],
            )
            return {"record_id": record_id}
        if action == "model":
            if call.calls >= self.budget.limits.worker_model_calls:
                raise OrchestrationError(
                    "BUDGET_EXHAUSTED", "Worker model-call allowance exhausted."
                )
            purpose = value["purpose"]
            if purpose not in {"recipe", "explanation"}:
                raise OrchestrationError("WORKER_MODEL", "Unknown worker model-call purpose.")
            call.calls += 1
            records = definition(call.role)
            record_type = records.Recipe if purpose == "recipe" else Explanation
            result, record_id = await self.model.ask(
                run_id,
                f"worker.{call.role}.{purpose}",
                record_type,
                {
                    "assigned_job": call.payload["job"],
                    "worker_call_id": call.id,
                    "worker_role": call.role,
                    "facts": value["context"],
                },
                parent=call.id,
                role="worker",
                with_record=True,
                instructions=WORKER_INSTRUCTIONS + "\n" + records.INSTRUCTIONS,
            )
            return {"value": result.model_dump(mode="json"), "record_id": record_id}
        if action == "publish":
            data = base64.b64decode(value["data"], validate=True)
            parents = [("worker", call.id)] + [("input", key) for key in call.allowed]
            ref = await self.files.put_bytes(run_id, data, value["kind"], parents=parents)
            call.allowed[ref.id] = ref
            return ref.model_dump()
        if action == "finish":
            result = definition(call.role).Result.model_validate(value["result"])
            for ref in references(result.model_dump(mode="json")):
                if call.allowed.get(ref.id) != ref:
                    raise OrchestrationError(
                        "FILE_REFERENCE", "Worker returned an unregistered output."
                    )
                await self.files.checked_path(run_id, ref)
            model_calls = await self.store.list_records(run_id, "model_call")
            ids = [row["id"] for row in model_calls if row["payload"].get("parent_id") == call.id]
            saved_result = result.model_copy(update={"usage_record_ids": ids}).model_dump(
                mode="json"
            )
            payload = call.payload | {
                "status": "SUCCEEDED",
                "result": saved_result,
                "model_calls": call.calls,
            }
            await self.store.finish(run_id, call.id, payload)
            call.result, call.payload = saved_result, payload
            return {"status": "SAVED", "result": saved_result}
        raise OrchestrationError("WORKER_ACTION", "Unknown worker support operation.")
