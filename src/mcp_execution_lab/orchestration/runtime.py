"""Shared execution ownership, MCP gate, step evidence, and final records."""

import asyncio
from contextlib import asynccontextmanager

from ..agents.common.gateway import WorkerGateway
from .broker import ToolBroker
from .mcp import Connections
from .models import OrchestrationError


class Runtime:
    def __init__(self, store, files, budget, servers, model=None):
        self.store, self.files, self.budget = store, files, budget
        self.servers, self.model = servers, model
        self.results = {}
        self.snapshots = {}
        self.states = {}
        self.completed_ids = set()
        self.completed_count = 0
        self.reviews = set()
        self.running = {}
        self.broker = None

    async def admit(self, handoff, current_source, needed):
        saved = await self.store.list_records(handoff.run_id, "handoff")
        if not saved or saved[-1]["payload"]["handoff"] != handoff.model_dump(mode="json"):
            raise OrchestrationError("HANDOFF", "Handoff differs from the saved accepted plan.")
        run = await self.store.run(handoff.run_id)
        if run["status"] != "READY_FOR_EXECUTION":
            raise OrchestrationError(
                "RUN_STATE", "Only a ready, unstarted run can begin execution."
            )
        if any(run["payload"].get(key) != value for key, value in current_source.items()):
            raise OrchestrationError(
                "CODE_CHANGED", "Code or dependency lock changed after planning."
            )
        if handoff.mode == "D2" and self.model is None:
            raise OrchestrationError(
                "MODEL_CONFIG", "D2 needs a model for its task-defined reviews."
            )
        if not needed <= {server.id for server in self.servers}:
            raise OrchestrationError(
                "SERVER_CONFIG", "A planned server has no project configuration."
            )
        await self.store.transition(handoff.run_id, "EXECUTING", expected="READY_FOR_EXECUTION")
        self.active = handoff
        self.results, self.snapshots, self.states, self.running = {}, {}, {}, {}
        self.completed_ids, self.reviews, self.completed_count = set(), set(), 0

    @asynccontextmanager
    async def tools(self, needed):
        async with (
            WorkerGateway(self.active, self.store, self.files, self.budget, self.model) as gateway,
            Connections(self.servers, initial_ids=needed) as connections,
        ):
            self.broker = ToolBroker(
                self.active, connections, self.store, self.files, self.budget, gateway
            )
            yield self.broker

    async def _finalize(self, status, outputs, error=None):
        handoff = self.active
        for rule in self.active.rules.reviews:
            if rule.id not in self.reviews:
                await self.store.event(handoff.run_id, "review_unreached", rule.model_dump())
        result = {
            "run_id": handoff.run_id,
            "status": status,
            "plan_version": self.active.version,
            "states": self.states,
            "outputs": {name: ref.model_dump() for name, ref in outputs.items()},
            "metrics": self.budget.summary()
            | {"reused_results": self.broker.reuses if self.broker else 0},
            "task_success": None,
            "evaluation_status": "NOT_EVALUATED",
            "error": {
                "code": getattr(error, "code", type(error).__name__),
                "message": str(error)[:4000],
            }
            if error
            else None,
        }
        await self.store.put(
            handoff.run_id, "execution_result", result, parents=[("plan", self.active.plan_record)]
        )
        await self.store.transition(handoff.run_id, status, result["error"])
        return result

    async def _state(self, name, state, detail=None):
        await self.store.step_state(
            self.active.run_id, self.active.plan_record, name, state, detail
        )
        self.states[name] = state

    async def _invoke(self, node, arguments):
        await self._state(node.id, "RUNNING")
        job = next(
            task.job for task in self.active.breakdown.subtasks if task.id == node.subtask_id
        )
        return await self.broker.call(node, arguments, plan_id=self.active.plan_record, job=job)

    async def _collect(self, done):
        fatal = None
        for task in done:
            name = self.running.pop(task)
            try:
                ref = task.result()
            except OrchestrationError as exc:
                state = "UNCERTAIN" if exc.code == "OUTCOME_UNKNOWN" else "FAILED"
                await self._state(name, state, {"code": exc.code, "error": str(exc)[:2000]})
                if state == "UNCERTAIN":
                    fatal = exc
                else:
                    self.completed_count += 1
            except asyncio.CancelledError:
                await self._state(name, "CANCELLED")
            except BaseException as exc:
                fatal = exc
            else:
                await self._state(name, "SUCCEEDED", {"output": ref.model_dump()})
                self.results[name] = ref
                self.snapshots[ref.id] = ref
                self.completed_ids.add(name)
                self.completed_count += 1
        if fatal:
            raise fatal

    async def _settle(self, *, cancel=False):
        if not self.running:
            return
        if cancel:
            for task in self.running:
                task.cancel()
        await asyncio.gather(*self.running, return_exceptions=True)
        await self._collect(list(self.running))

    def _due(self):
        return [
            rule
            for rule in self.active.rules.reviews
            if rule.id not in self.reviews and self.completed_count >= rule.after_completed_steps
        ]
