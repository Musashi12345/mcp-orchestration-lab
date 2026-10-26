"""Event-driven DAG scheduling with durable step records and task-defined reviews."""

import asyncio

from .bindings import Resolver
from .graph import validate_plan
from .models import Handoff, OrchestrationError, ReviewDecision
from .provenance import source_identity
from .reviews import checked_snapshot, review, snapshot_keys
from .runtime import Runtime


class Executor(Runtime):
    async def run(self, handoff: Handoff):
        if handoff.plan is None or handoff.mode not in {"D1", "D2"}:
            raise OrchestrationError("MODE", "The DAG executor requires a D1/D2 plan.")
        needed = {step.server for step in handoff.plan.steps}
        await self.admit(handoff, source_identity(), needed)
        outputs = {}
        try:
            async with asyncio.timeout(self.budget.remaining):
                async with self.tools(needed):
                    try:
                        await self._activate(handoff)
                        outputs = await self._schedule()
                    except BaseException:
                        await self._settle(cancel=True)
                        raise
                    status = (
                        "FAILED"
                        if self._unhandled() or len(outputs) != len(self.active.plan.outputs)
                        else "COMPLETED"
                    )
        except BaseException as exc:
            await self._settle(cancel=True)
            status = (
                "INTERRUPTED"
                if isinstance(exc, asyncio.CancelledError)
                else ("UNCERTAIN" if getattr(exc, "code", "") == "OUTCOME_UNKNOWN" else "FAILED")
            )
            await self._finalize(status, outputs, exc)
            raise
        return await self._finalize(status, outputs)

    async def _activate(self, handoff):
        validate_plan(
            handoff.plan,
            handoff.breakdown,
            handoff.cache,
            handoff.datasets,
            self.budget.limits,
            snapshots=self.snapshots,
            completed=self.completed_ids,
        )
        await self.broker.connections.ensure({step.server for step in handoff.plan.steps})
        await self.broker.connections.verify(handoff.cache)
        self.active = handoff
        self.results = {}
        self.states = {step.id: "WAITING" for step in handoff.plan.steps}
        self.resolver = Resolver(handoff, self.files, self.results, self.snapshots, self.states)
        await self.store.register_steps(handoff.run_id, handoff.plan_record, handoff.plan)
        await self.store.event(
            handoff.run_id,
            "plan_activated",
            {"plan_id": handoff.plan_record, "version": handoff.version},
        )

    async def _schedule(self):
        while True:
            self.budget.check()
            if self._due():
                # Drain already running work, without starting anything across the barrier.
                await self._settle()
                rule = self._due()[0]
                await self._review(rule)
                continue
            changed = False
            local_changes = False
            for node in self.active.plan.steps:
                if self.states[node.id] != "WAITING":
                    continue
                dependencies = [self.states[name] for name in node.depends_on]
                forbidden = {"UNCERTAIN", "CANCELLED"}
                if node.dependency_policy == "success":
                    forbidden |= {"FAILED", "BLOCKED"}
                if any(value in forbidden for value in dependencies):
                    await self._state(node.id, "BLOCKED")
                    changed = True
                    local_changes = True
                    continue
                settled = {"SUCCEEDED", "SKIPPED"}
                if node.dependency_policy == "settled":
                    settled |= {"FAILED", "BLOCKED"}
                if not all(value in settled for value in dependencies):
                    continue
                if len(self.running) >= self.budget.limits.concurrency:
                    continue
                try:
                    if node.condition is not None and not await self.resolver.condition(
                        node.condition
                    ):
                        await self._state(node.id, "SKIPPED")
                        changed = True
                        local_changes = True
                        continue
                    arguments = {
                        key: await self.resolver.resolve(value)
                        for key, value in node.arguments.items()
                    }
                except OrchestrationError as exc:
                    await self._state(node.id, "FAILED", {"code": exc.code, "error": str(exc)})
                    changed = True
                    local_changes = True
                    continue
                await self._state(node.id, "READY", {"arguments": arguments})
                task = asyncio.create_task(self._invoke(node, arguments))
                self.running[task] = node.id
                # Reserve the node immediately; actual RUNNING is written by the step runner.
                self.states[node.id] = "DISPATCHING"
                changed = True
            if local_changes and len(self.running) < self.budget.limits.concurrency:
                continue
            if self.running:
                done, _ = await asyncio.wait(self.running, return_when=asyncio.FIRST_COMPLETED)
                await self._collect(done)
                continue
            if not any(state in {"WAITING", "DISPATCHING"} for state in self.states.values()):
                break
            if not changed:
                raise OrchestrationError(
                    "GRAPH_STALLED", "No remaining step can provide required work."
                )
        outputs = {}
        for name, binding in self.active.plan.outputs.items():
            try:
                value = await self.resolver.resolve(binding)
                outputs[name] = await self.files.put_json(
                    self.active.run_id, value, parents=[("plan", self.active.plan_record)]
                )
            except OrchestrationError:
                if not any(state in {"FAILED", "BLOCKED"} for state in self.states.values()):
                    raise
        return outputs

    def _unhandled(self):
        failures = {key for key, state in self.states.items() if state in {"FAILED", "BLOCKED"}}
        handled = set()
        nodes = {node.id: node for node in self.active.plan.steps}

        def recover(name):
            if name in failures and name not in handled:
                handled.add(name)
                for parent in nodes[name].depends_on:
                    recover(parent)

        for node in nodes.values():
            if node.dependency_policy == "settled" and self.states[node.id] == "SUCCEEDED":
                for parent in node.depends_on:
                    recover(parent)
        return failures - handled

    async def _validate_review(self, decision):
        validate_plan(
            decision.replacement,
            decision.breakdown,
            self.active.cache,
            self.active.datasets,
            self.budget.limits,
            snapshots=self.snapshots,
            completed=self.completed_ids,
        )
        self._validate_recoveries(decision, [step.id for step in decision.replacement.steps])
        await checked_snapshot(self, snapshot_keys(decision.replacement))

    async def _review(self, rule):
        await review(self, rule, ReviewDecision, self._validate_review)

    async def _replace(self, decision, *, review_id, snapshot_id):
        await self._retire(decision)
        for name, state in self.states.items():
            if state in {"WAITING", "READY", "BLOCKED"}:
                await self._state(name, "REPLACED")
        old = self.active
        breakdown_id = await self.store.put(
            old.run_id,
            "breakdown",
            decision.breakdown.model_dump(),
            parents=[("previous_plan", old.plan_record)],
        )
        plan_id = await self.store.put(
            old.run_id,
            "plan",
            {
                "version": old.version + 1,
                "plan": decision.replacement.model_dump(),
                "valid": True,
            },
            parents=[
                ("breakdown", breakdown_id),
                ("previous_plan", old.plan_record),
                ("review", review_id),
                ("review_snapshot", snapshot_id),
                ("cache", old.cache_record),
                ("task", old.task_record),
            ],
        )
        handoff = old.model_copy(
            update={
                "plan": decision.replacement,
                "breakdown": decision.breakdown,
                "plan_record": plan_id,
                "version": old.version + 1,
            }
        )
        await self.store.put(
            old.run_id,
            "handoff",
            {"handoff": handoff.model_dump(mode="json"), "usage": self.budget.summary()},
            parents=[("plan", plan_id)],
        )
        await self._activate(handoff)
