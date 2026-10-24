"""P1 ordering comes only from saved Python; calls use the shared execution runtime."""

import asyncio

from ..agents.common.gateway import references
from ..program_sdk.policy import VERSION
from .config import ProgramRunnerConfig
from .models import CallSpec, FileRef, Handoff, OrchestrationError
from .program_container import Container, image_identity
from .programs import validate_program
from .provenance import source_identity
from .runtime import Runtime


class ProgramExecutor(Runtime):
    def __init__(self, *args, runner_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner_config = runner_config or ProgramRunnerConfig()

    async def run(self, handoff: Handoff):
        if handoff.mode != "P1" or handoff.program is None:
            raise OrchestrationError("MODE", "The Python executor requires a P1 program.")
        validate_program(handoff.program, handoff.breakdown, handoff.cache, self.budget.limits)
        async with asyncio.timeout(self.budget.remaining):
            image = await image_identity(self.runner_config)
        needed = {handoff.cache.by_key(task.tool_key).server for task in handoff.breakdown.subtasks}
        await self.admit(handoff, source_identity(), needed)
        outputs = {}
        self.condition = asyncio.Condition()
        self.claimed, self.handled, self.recoveries = set(), set(), {}
        self.allowed = {item.ref.id: item.ref for item in handoff.datasets}
        self.fatal = None
        self.container = Container(
            self.runner_config, image, max(4194304, self.budget.limits.max_result_bytes * 2)
        )
        try:
            async with asyncio.timeout(self.budget.remaining):
                record = await self.store.get(handoff.run_id, handoff.plan_record)
                source = FileRef.model_validate(record["payload"]["source"])
                source_path = await self.files.checked_path(handoff.run_id, source)
                if (
                    await asyncio.to_thread(source_path.read_text, encoding="utf-8")
                    != handoff.program.source
                ):
                    raise OrchestrationError(
                        "PROGRAM_SOURCE", "Saved program differs from its source file."
                    )
                async with self.tools(needed):
                    await self.broker.connections.verify(handoff.cache)
                    self.calls = {}
                    for task in handoff.breakdown.subtasks:
                        tool = handoff.cache.by_key(task.tool_key)
                        self.calls[task.id] = CallSpec(
                            id=task.id, subtask_id=task.id, server=tool.server, tool=tool.name
                        )
                    self.states = dict.fromkeys(self.calls, "WAITING")
                    await self.store.register_calls(
                        handoff.run_id, handoff.plan_record, list(self.calls.values())
                    )
                    await self.store.put(
                        handoff.run_id,
                        "program_runtime",
                        image,
                        parents=[("program", handoff.plan_record)],
                    )

                    async def started(evidence):
                        await self.store.put(
                            handoff.run_id,
                            "program_container",
                            evidence,
                            parents=[("program", handoff.plan_record)],
                        )

                    try:
                        value = await self.container.run(
                            {
                                "type": "start",
                                "source": handoff.program.source,
                                "jobs": list(self.calls),
                                "frame_limit": self.container.limit,
                                "max_source_chars": self.budget.limits.max_prompt_chars,
                                "inputs": {
                                    "task": handoff.task.model_dump(),
                                    "datasets": {
                                        item.ref.id: item.ref.model_dump()
                                        for item in handoff.datasets
                                    },
                                },
                            },
                            self._call,
                            started,
                        )
                        self.budget.check()
                        await self._pass_reviews()
                        if not isinstance(value, dict) or set(value) != set(
                            handoff.program.outputs
                        ):
                            raise OrchestrationError(
                                "PROGRAM_OUTPUT", "Return exactly the declared output names."
                            )
                        await self._check_scope(value)
                        for name, result in value.items():
                            outputs[name] = await self.files.put_json(
                                handoff.run_id, result, parents=[("program", handoff.plan_record)]
                            )
                        for name, state in list(self.states.items()):
                            if state == "WAITING":
                                await self._state(name, "SKIPPED")
                        failures = {
                            name for name, state in self.states.items() if state == "FAILED"
                        }
                        status = "FAILED" if failures - self.handled else "COMPLETED"
                    finally:
                        await self._settle(cancel=True)
        except BaseException as exc:
            await self._settle(cancel=True)
            for name, state in list(self.states.items()):
                if state in {"WAITING", "READY", "DISPATCHING"}:
                    await self._state(name, "CANCELLED")
            status = (
                "INTERRUPTED"
                if isinstance(exc, asyncio.CancelledError)
                else ("UNCERTAIN" if getattr(exc, "code", "") == "OUTCOME_UNKNOWN" else "FAILED")
            )
            await self._finalize(status, outputs, exc)
            raise
        finally:
            await self.store.put(
                handoff.run_id,
                "program_diagnostics",
                {
                    "container": self.container.name,
                    "cleanup": self.container.cleanup,
                    "stderr": self.container.stderr.decode(errors="replace"),
                    "policy": VERSION,
                },
                parents=[("program", handoff.plan_record)],
            )
        return await self._finalize(status, outputs)

    async def _check_scope(self, value):
        for ref in references(value):
            if self.allowed.get(ref.id) != ref:
                raise OrchestrationError("FILE_SCOPE", "Program used a file it has not received.")
            await self.files.checked_path(self.active.run_id, ref)

    async def _pass_reviews(self):
        if self.running:
            return
        for rule in self._due():
            self.reviews.add(rule.id)
            await self.store.put(
                self.active.run_id,
                "review",
                {
                    "rule": rule.model_dump(),
                    "status": "PASSED_WITHOUT_MODEL",
                    "completed_steps": self.completed_count,
                },
                parents=[("program", self.active.plan_record)],
            )

    def _recover(self, name):
        if name not in self.handled:
            self.handled.add(name)
            for parent in self.recoveries.get(name, []):
                self._recover(parent)

    async def _call(self, packet):
        name, arguments, handles = packet["subtask_id"], packet["arguments"], packet["handles"]
        if not isinstance(name, str) or name not in self.calls or not isinstance(arguments, dict):
            raise OrchestrationError(
                "PROGRAM_CALL", "Call must match an assigned subtask and object arguments."
            )
        if (
            not isinstance(handles, list)
            or any(not isinstance(key, str) for key in handles)
            or len(handles) != len(set(handles))
        ):
            raise OrchestrationError(
                "PROGRAM_CALL", "handles must contain distinct failed subtask IDs."
            )
        await self._check_scope(arguments)
        async with self.condition:
            if name in self.claimed:
                raise OrchestrationError("PROGRAM_CALL", "An assigned subtask can run only once.")
            self.claimed.add(name)
            while True:
                self.budget.check()
                if self.fatal:
                    raise self.fatal
                await self._pass_reviews()
                if len(self.running) < self.budget.limits.concurrency and not self._due():
                    break
                await self.condition.wait()
            if any(self.states.get(key) != "FAILED" for key in handles):
                raise OrchestrationError(
                    "PROGRAM_CALL", "A fallback may handle only confirmed failures."
                )
            self.recoveries[name] = handles
            await self._state(name, "READY", {"arguments": arguments, "handles": handles})
            task = asyncio.create_task(self._invoke(self.calls[name], arguments))
            self.running[task] = name
            self.states[name] = "DISPATCHING"
        error = None
        try:
            await asyncio.shield(task)
        except OrchestrationError as exc:
            error = exc
        except BaseException as exc:
            async with self.condition:
                self.fatal = exc
                self.condition.notify_all()
            raise
        async with self.condition:
            try:
                await self._collect([task])
                if self.states[name] == "SUCCEEDED":
                    ref = self.results[name]
                    value = await self.files.read_json(self.active.run_id, ref)
                    for nested in references(value):
                        await self.files.checked_path(self.active.run_id, nested)
                        self.allowed[nested.id] = nested
                    self.allowed[ref.id] = ref
                    for parent in handles:
                        self._recover(parent)
                    await self._pass_reviews()
                    return {
                        "state": "SUCCEEDED",
                        "value": value,
                        "output": ref.model_dump(),
                        "error": None,
                    }
                await self._pass_reviews()
                return {
                    "state": "FAILED",
                    "value": None,
                    "output": None,
                    "error": {"code": error.code, "message": str(error)[:2000]},
                }
            except BaseException as exc:
                self.fatal = exc
                raise
            finally:
                self.condition.notify_all()
