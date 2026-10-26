"""Saved Python ordering, host-owned reviews, and one shared run/tool allowance."""

import asyncio

from ..agents.common.gateway import references
from ..program_sdk.policy import VERSION
from ..program_sdk.protocol import ProtocolError, encode
from .config import ProgramRunnerConfig
from .models import CallSpec, FileRef, Handoff, OrchestrationError, ProgramReviewDecision
from .program_container import Container, ProgramRevised, image_identity
from .programs import PROGRAM_REVIEW_INSTRUCTIONS, validate_program
from .provenance import source_identity
from .reviews import checked_snapshot, review
from .runtime import Runtime


class ProgramExecutor(Runtime):
    def __init__(self, *args, runner_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner_config = runner_config or ProgramRunnerConfig()

    async def run(self, handoff: Handoff):
        if handoff.mode not in {"P1", "P2"} or handoff.program is None:
            raise OrchestrationError("MODE", "The Python executor requires a P1/P2 program.")
        validate_program(handoff.program, handoff.breakdown, handoff.cache, self.budget.limits)
        async with asyncio.timeout(self.budget.remaining):
            image = await image_identity(self.runner_config)
        needed = {handoff.cache.by_key(task.tool_key).server for task in handoff.breakdown.subtasks}
        await self.admit(handoff, source_identity(), needed)
        self.condition = asyncio.Condition()
        self.review_task = None
        self.fatal = None
        self.handled = set()
        self.frame_limit = max(4194304, self.budget.limits.max_result_bytes * 2)
        outputs = {}
        try:
            async with asyncio.timeout(self.budget.remaining):
                async with self.tools(needed):
                    try:
                        await self._activate(handoff)
                        while True:
                            epoch = self.active.version
                            try:
                                value = await self._run_version(image)
                                await self._barrier(epoch)
                            except ProgramRevised:
                                # The old bridge has drained and confirmed container removal.
                                continue
                            self.budget.check()
                            if not isinstance(value, dict) or set(value) != set(
                                self.active.program.outputs
                            ):
                                raise OrchestrationError(
                                    "PROGRAM_OUTPUT", "Return exactly the declared output names."
                                )
                            await self._check_scope(value)
                            for name, result in value.items():
                                outputs[name] = await self.files.put_json(
                                    handoff.run_id,
                                    result,
                                    parents=[("program", self.active.plan_record)],
                                )
                            for name, state in list(self.states.items()):
                                if state == "WAITING":
                                    await self._state(name, "SKIPPED")
                            status = "FAILED" if self._unhandled() else "COMPLETED"
                            break
                    finally:
                        await self._shutdown()
        except BaseException as exc:
            await self._shutdown()
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
        return await self._finalize(status, outputs)

    def _packet(self, program, breakdown, snapshot):
        return {
            "type": "start",
            "source": program.source,
            "jobs": [task.id for task in breakdown.subtasks],
            "frame_limit": self.frame_limit,
            "max_source_chars": self.budget.limits.max_prompt_chars,
            "inputs": {
                "task": self.active.task.model_dump(),
                "datasets": {item.ref.id: item.ref.model_dump() for item in self.active.datasets},
                "snapshot": snapshot,
            },
        }

    async def _activate(self, handoff):
        validate_program(
            handoff.program,
            handoff.breakdown,
            handoff.cache,
            self.budget.limits,
            completed=self.completed_ids,
        )
        record = await self.store.get(handoff.run_id, handoff.plan_record)
        source = FileRef.model_validate(record["payload"]["source"])
        path = await self.files.checked_path(handoff.run_id, source)
        if await asyncio.to_thread(path.read_text, encoding="utf-8") != handoff.program.source:
            raise OrchestrationError(
                "PROGRAM_SOURCE", "Saved program differs from its source file."
            )
        snapshot = {}
        if handoff.continuation is not None:
            snapshot = await self.files.read_json(handoff.run_id, handoff.continuation)
            if snapshot != await checked_snapshot(self, list(snapshot)):
                raise OrchestrationError(
                    "PROGRAM_SNAPSHOT", "Continuation differs from checked results."
                )
        needed = {handoff.cache.by_key(task.tool_key).server for task in handoff.breakdown.subtasks}
        await self.broker.connections.ensure(needed)
        await self.broker.connections.verify(handoff.cache)
        self.active = handoff
        self.snapshot_inputs = snapshot
        self.allowed = {item.ref.id: item.ref for item in handoff.datasets}
        for ref in references(snapshot):
            await self.files.checked_path(handoff.run_id, ref)
            self.allowed[ref.id] = ref
        self.calls = {}
        for task in handoff.breakdown.subtasks:
            tool = handoff.cache.by_key(task.tool_key)
            self.calls[task.id] = CallSpec(
                id=task.id, subtask_id=task.id, server=tool.server, tool=tool.name
            )
        self.states = dict.fromkeys(self.calls, "WAITING")
        self.results = {}
        self.claimed, self.handled, self.recoveries = set(), set(), {}
        await self.store.register_calls(
            handoff.run_id, handoff.plan_record, list(self.calls.values())
        )
        await self.store.event(
            handoff.run_id,
            "program_activated",
            {"program_id": handoff.plan_record, "version": handoff.version},
        )

    async def _run_version(self, image):
        active = self.active
        self.container = container = Container(self.runner_config, image, self.frame_limit)
        await self.store.put(
            active.run_id,
            "program_runtime",
            image | {"version": active.version},
            parents=[("program", active.plan_record)],
        )

        async def started(evidence):
            await self.store.put(
                active.run_id,
                "program_container",
                evidence | {"epoch": active.version},
                parents=[("program", active.plan_record)],
            )

        try:
            return await container.run(
                self._packet(active.program, active.breakdown, self.snapshot_inputs),
                lambda packet: self._call(packet, active.version),
                started,
            )
        finally:
            await self.store.put(
                active.run_id,
                "program_diagnostics",
                {
                    "container": container.name,
                    "cleanup": container.cleanup,
                    "stderr": container.stderr.decode(errors="replace"),
                    "policy": VERSION,
                    "epoch": active.version,
                },
                parents=[("program", active.plan_record)],
            )
            if container.cleanup != "REMOVED":
                raise OrchestrationError("OUTCOME_UNKNOWN", "Runner cleanup needs confirmation.")

    async def _shutdown(self):
        if self.review_task is not None:
            self.review_task.cancel()
            await asyncio.gather(self.review_task, return_exceptions=True)
        await self._settle(cancel=True)

    def _epoch(self, epoch):
        if self.fatal is not None:
            raise self.fatal
        if epoch != self.active.version:
            raise ProgramRevised()

    async def _barrier(self, epoch):
        while True:
            async with self.condition:
                if self.fatal is not None:
                    raise self.fatal
                if self.review_task is None:
                    self._epoch(epoch)
                    if self._due():
                        if self.running:
                            await self.condition.wait()
                            continue
                        self.review_task = asyncio.create_task(self._review_due())
                    else:
                        return
                pending = self.review_task
            # Model calls never hold the collection/dispatch condition lock.
            await asyncio.shield(pending)

    async def _review_due(self):
        try:
            while self._due():
                await review(
                    self,
                    self._due()[0],
                    ProgramReviewDecision,
                    self._validate_review,
                    instructions=PROGRAM_REVIEW_INSTRUCTIONS,
                )
        except BaseException as exc:
            self.fatal = exc
            raise
        finally:
            async with self.condition:
                self.review_task = None
                self.condition.notify_all()

    async def _validate_review(self, decision):
        validate_program(
            decision.replacement,
            decision.breakdown,
            self.active.cache,
            self.budget.limits,
            completed=self.completed_ids,
        )
        self._validate_recoveries(decision, [task.id for task in decision.breakdown.subtasks])
        snapshot = await checked_snapshot(self, decision.preserve)
        try:
            encode(
                self._packet(decision.replacement, decision.breakdown, snapshot), self.frame_limit
            )
        except ProtocolError as exc:
            raise OrchestrationError(
                "PLAN_INVALID", "Continuation startup frame is too large."
            ) from exc

    async def _replace(self, decision, *, review_id, snapshot_id):
        old = self.active
        parents = [
            ("previous_program", old.plan_record),
            ("review", review_id),
            ("review_snapshot", snapshot_id),
        ]
        snapshot = await checked_snapshot(self, decision.preserve)
        continuation = await self.files.put_json(old.run_id, snapshot, parents=parents)
        breakdown_id = await self.store.put(
            old.run_id, "breakdown", decision.breakdown.model_dump(), parents=parents
        )
        source = await self.files.put_program(
            old.run_id, decision.replacement.source, parents=parents
        )
        program_id = await self.store.put(
            old.run_id,
            "program",
            {
                "version": old.version + 1,
                "program": decision.replacement.model_dump(),
                "valid": True,
                "source": source.model_dump(),
                "language_policy": VERSION,
                "continuation": continuation.model_dump(),
                "preserve": decision.preserve,
            },
            parents=parents
            + [
                ("breakdown", breakdown_id),
                ("cache", old.cache_record),
                ("task", old.task_record),
                ("continuation", continuation.id),
            ],
        )
        handoff = old.model_copy(
            update={
                "program": decision.replacement,
                "breakdown": decision.breakdown,
                "plan_record": program_id,
                "version": old.version + 1,
                "continuation": continuation,
            }
        )
        await self.store.put(
            old.run_id,
            "handoff",
            {"handoff": handoff.model_dump(mode="json"), "usage": self.budget.summary()},
            parents=[("program", program_id)],
        )
        await self._retire(decision)
        for name, state in list(self.states.items()):
            if state in {"WAITING", "READY", "BLOCKED"}:
                await self._state(name, "REPLACED")
        await self._activate(handoff)

    async def _check_scope(self, value):
        for ref in references(value):
            if self.allowed.get(ref.id) != ref:
                raise OrchestrationError("FILE_SCOPE", "Program used a file it has not received.")
            await self.files.checked_path(self.active.run_id, ref)

    def _unhandled(self):
        return super()._unhandled() - self.handled

    def _recover(self, name):
        if name not in self.handled:
            self.handled.add(name)
            for parent in self.recoveries.get(name, []):
                self._recover(parent)

    async def _call(self, packet, epoch):
        name, arguments, handles = packet["subtask_id"], packet["arguments"], packet["handles"]
        await self._barrier(epoch)
        if not isinstance(name, str) or name not in self.calls or not isinstance(arguments, dict):
            raise OrchestrationError(
                "PROGRAM_CALL", "Call must match an assigned job and object arguments."
            )
        if (
            not isinstance(handles, list)
            or any(not isinstance(key, str) for key in handles)
            or len(handles) != len(set(handles))
        ):
            raise OrchestrationError(
                "PROGRAM_CALL", "handles must contain distinct failed job IDs."
            )
        async with self.condition:
            self._epoch(epoch)
            if name in self.claimed:
                raise OrchestrationError("PROGRAM_CALL", "An assigned subtask can run only once.")
            self.claimed.add(name)
        while True:
            await self._barrier(epoch)
            async with self.condition:
                self.budget.check()
                self._epoch(epoch)
                if self.review_task is not None or self._due():
                    continue
                if len(self.running) >= self.budget.limits.concurrency:
                    await self.condition.wait()
                    continue
                await self._check_scope(arguments)
                if any(self.states.get(key) != "FAILED" for key in handles):
                    raise OrchestrationError(
                        "PROGRAM_CALL", "A fallback handles only confirmed failures."
                    )
                self.recoveries[name] = handles
                await self._state(name, "READY", {"arguments": arguments, "handles": handles})
                task = asyncio.create_task(self._invoke(self.calls[name], arguments))
                self.running[task] = name
                self.states[name] = "DISPATCHING"
                break
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
                    result = {
                        "state": "SUCCEEDED",
                        "value": value,
                        "output": ref.model_dump(),
                        "error": None,
                    }
                else:
                    result = {
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
        await self._barrier(epoch)
        return result
