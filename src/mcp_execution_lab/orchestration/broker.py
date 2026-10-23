"""Shared tool execution boundary, independent of graph order or agent roles."""

import asyncio
from collections import defaultdict

from jsonschema import Draft202012Validator

from .models import FileRef, OrchestrationError, canonical, fingerprint


class ToolBroker:
    def __init__(self, handoff, connections, store, files, budget, gateway=None):
        self.handoff, self.connections, self.store = handoff, connections, store
        self.files, self.budget = files, budget
        self.locks = defaultdict(asyncio.Lock)
        self.completed = {}
        self.uncertain = set()
        self.reuses = 0
        self.gateway = gateway

    async def call(self, step, arguments, *, plan_id, job):
        self.budget.check()
        tool = self.handoff.cache.lookup(step.server, step.tool)
        worker_role = tool.raw_definition.get("meta", {}).get("lab_worker_role")
        if worker_role and arguments.get("job") != job:
            raise OrchestrationError("WORKER_JOB", "Worker job differs from the assigned subtask.")
        errors = list(Draft202012Validator(tool.input_schema).iter_errors(arguments))
        if errors:
            raise OrchestrationError("TOOL_ARGUMENTS", errors[0].message)
        await self._check_references(arguments)
        operation_id = fingerprint(
            {
                "run_id": self.handoff.run_id,
                "occurrence": step.id,
                "tool": tool.model_dump(),
                "arguments": arguments,
                "job": job,
            }
        )
        async with self.locks[operation_id]:
            if operation_id in self.uncertain:
                raise OrchestrationError(
                    "OUTCOME_UNKNOWN", "Operation outcome needs reconciliation."
                )
            if operation_id in self.completed:
                ref = self.completed[operation_id]
                await self.files.read_json(self.handoff.run_id, ref)
                self.reuses += 1
                await self.store.event(
                    self.handoff.run_id,
                    "result_reused",
                    {"operation_id": operation_id, "step_id": step.id, "output": ref.model_dump()},
                )
                return ref
            return await self._perform(step, arguments, operation_id, plan_id, job, tool)

    async def _check_references(self, value):
        if isinstance(value, dict):
            if {"id", "run_id", "sha256", "kind"} <= value.keys():
                if value["run_id"] != self.handoff.run_id:
                    raise OrchestrationError("FILE_OWNERSHIP", "Tool input references another run.")
                row = await self.store.get(self.handoff.run_id, value["id"])
                stored = row["payload"]
                ref = stored.get("ref") or stored.get("dataset", {}).get("ref")
                if ref != value:
                    raise OrchestrationError(
                        "FILE_REFERENCE", "Tool input reference is not registered."
                    )
                await self.files.checked_path(self.handoff.run_id, FileRef.model_validate(value))
            for item in value.values():
                await self._check_references(item)
        elif isinstance(value, list):
            for item in value:
                await self._check_references(item)

    async def _perform(self, step, arguments, operation_id, plan_id, job, tool):
        run_id = self.handoff.run_id
        safe_retry = any(
            tool.annotations.get(name) is True for name in ("read_only_hint", "idempotent_hint")
        )
        for attempt in range(self.budget.limits.transport_retries + 1):
            self.budget.tool()
            record = {
                "operation_id": operation_id,
                "step_id": step.id,
                "plan_id": plan_id,
                "server": step.server,
                "tool": step.tool,
                "job": job,
                "arguments": arguments,
                "attempt": attempt + 1,
                "status": "RUNNING",
            }
            attempt_id = await self.store.put(
                run_id, "tool_attempt", record, parents=[("plan", plan_id)]
            )
            worker_context = None
            worker_role = tool.raw_definition.get("meta", {}).get("lab_worker_role")
            if worker_role:
                try:
                    worker_context = await self.gateway.open(
                        worker_role, step, arguments, attempt_id, operation_id, job
                    )
                except OrchestrationError as exc:
                    await self.store.finish(
                        run_id, attempt_id, record | {"status": "FAILED", "error": str(exc)}
                    )
                    raise
            try:
                request = self.connections.call(
                    step.server,
                    step.tool,
                    arguments,
                    operation_id,
                    **({"worker_context": worker_context} if worker_context else {}),
                )
                response = await asyncio.wait_for(
                    request,
                    timeout=min(self.budget.remaining, self.budget.limits.tool_seconds),
                )
            except BaseException as exc:
                if worker_context:
                    await self.gateway.close_call(
                        self.gateway.contexts[worker_context["token"]], "UNCERTAIN"
                    )
                record.update(status="UNCERTAIN", error=f"{type(exc).__name__}: {str(exc)[:2000]}")
                await self.store.finish(run_id, attempt_id, record)
                if isinstance(exc, asyncio.CancelledError):
                    self.uncertain.add(operation_id)
                    raise
                transient = isinstance(exc, (TimeoutError, OSError, ConnectionError))
                if transient and safe_retry and attempt < self.budget.limits.transport_retries:
                    await self.store.event(
                        run_id, "transport_retry", {"operation_id": operation_id}
                    )
                    continue
                self.uncertain.add(operation_id)
                raise OrchestrationError(
                    "OUTCOME_UNKNOWN", "Tool outcome could not be confirmed."
                ) from exc
            try:
                if len(canonical(response).encode()) > self.budget.limits.max_result_bytes:
                    raise OrchestrationError(
                        "RESULT_SIZE", "MCP result exceeded its byte allowance."
                    )
                record["response"] = response
                if response.get("is_error"):
                    if worker_context:
                        await self.gateway.close_call(
                            self.gateway.contexts[worker_context["token"]], "FAILED"
                        )
                    raise OrchestrationError(
                        "TOOL_FAILED", "The MCP tool returned a known failure."
                    )
                content = response.get("structured_content")
                if not isinstance(content, dict):
                    raise OrchestrationError(
                        "TOOL_RESULT_SCHEMA", "A structured JSON object is required."
                    )
                if tool.output_schema is not None:
                    errors = list(Draft202012Validator(tool.output_schema).iter_errors(content))
                    if errors:
                        raise OrchestrationError("TOOL_RESULT_SCHEMA", errors[0].message)
                if worker_context:
                    await self.gateway.accept(worker_context, content)
                    await self.gateway.close_call(
                        self.gateway.contexts[worker_context["token"]], "SUCCEEDED"
                    )
                    if content["outcome"] != "COMPLETED":
                        raise OrchestrationError("WORKER_" + content["outcome"], content["summary"])
                ref = await self.files.put_json(run_id, content, parents=[("attempt", attempt_id)])
            except OrchestrationError as exc:
                record.update(status="FAILED", error=str(exc), code=exc.code)
                await self.store.finish(run_id, attempt_id, record)
                raise
            record.update(status="SUCCEEDED", output=ref.model_dump())
            await self.store.finish(run_id, attempt_id, record)
            self.completed[operation_id] = ref
            return ref
        raise AssertionError("Retry loop must return or raise")
