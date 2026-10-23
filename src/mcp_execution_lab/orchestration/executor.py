"""Event-driven DAG scheduling with durable step records and task-defined reviews."""

import asyncio

from .bindings import Resolver
from .graph import validate_plan
from .models import Handoff, OrchestrationError, ReviewDecision
from .provenance import source_identity
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
                    failures = {
                        key for key, state in self.states.items() if state in {"FAILED", "BLOCKED"}
                    }
                    handled = set()
                    nodes = {node.id: node for node in self.active.plan.steps}

                    def recover(name):
                        if name in failures and name not in handled:
                            handled.add(name)
                            for parent in nodes[name].depends_on:
                                recover(parent)

                    for node in nodes.values():
                        if (
                            node.dependency_policy == "settled"
                            and self.states[node.id] == "SUCCEEDED"
                        ):
                            for parent in node.depends_on:
                                recover(parent)
                    status = (
                        "FAILED"
                        if failures - handled or len(outputs) != len(self.active.plan.outputs)
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

    async def _review(self, rule):
        self.reviews.add(rule.id)
        record = {
            "rule": rule.model_dump(),
            "completed_steps": self.completed_count,
            "status": "RUNNING",
            "mode": self.active.mode,
        }
        review_id = await self.store.put(
            self.active.run_id, "review", record, parents=[("plan", self.active.plan_record)]
        )
        if self.active.mode == "D1":
            await self.store.finish(
                self.active.run_id, review_id, record | {"status": "PASSED_WITHOUT_MODEL"}
            )
            return
        if self.broker.uncertain:
            raise OrchestrationError(
                "OUTCOME_UNKNOWN", "Cannot replan around unresolved operations."
            )
        observations, used = {}, 0
        for key, ref in self.snapshots.items():
            value = await self.files.read_json(self.active.run_id, ref)
            from .models import canonical

            size = len(canonical(value))
            if used + size <= self.budget.limits.max_prompt_chars // 3:
                observations[key] = value
                used += size
        context = {
            "original_request": (await self.store.run(self.active.run_id))["payload"]["request"],
            "main_task": self.active.task.model_dump(),
            "datasets": [dataset.model_dump() for dataset in self.active.datasets],
            "tool_cache": self.active.cache.model_dump(),
            "task_rules": self.active.rules.model_dump(),
            "review_rule": rule.model_dump(),
            "current_plan": self.active.plan.model_dump(),
            "current_breakdown": self.active.breakdown.model_dump(),
            "states": self.states,
            "valid_outputs": {key: ref.model_dump() for key, ref in self.snapshots.items()},
            "observations": observations,
            "completed_step_ids": sorted(self.completed_ids),
        }
        context["public_failures"] = []
        for attempt in await self.store.list_records(self.active.run_id, "tool_attempt"):
            payload = attempt["payload"]
            if payload["status"] == "FAILED":
                response = payload.get("response", {})
                context["public_failures"].append(
                    {
                        "attempt_id": attempt["id"],
                        "step_id": payload["step_id"],
                        "code": payload.get("code"),
                        "error": payload.get("error", "")[:2000],
                        "response_excerpt": str(
                            response.get("structured_content") or response.get("content", "")
                        )[:2000],
                    }
                )
        errors = []
        try:
            for attempt in range(self.budget.limits.correction_attempts + 1):
                try:
                    decision = await self.model.ask(
                        self.active.run_id,
                        "review",
                        ReviewDecision,
                        context | {"validation_errors": errors},
                        parent=review_id,
                    )
                    await self.store.put(
                        self.active.run_id,
                        "review_candidate",
                        decision.model_dump(),
                        parents=[("review", review_id)],
                    )
                    if decision.decision == "REVISE":
                        validate_plan(
                            decision.replacement,
                            decision.breakdown,
                            self.active.cache,
                            self.active.datasets,
                            self.budget.limits,
                            snapshots=self.snapshots,
                            completed=self.completed_ids,
                        )
                    break
                except OrchestrationError as exc:
                    if exc.code not in {"MODEL_FORMAT", "PLAN_INVALID", "UNKNOWN_TOOL"}:
                        raise
                    errors = [{"code": exc.code, "message": str(exc)}]
                    await self.store.put(
                        self.active.run_id,
                        "validation",
                        {"stage": "review", "attempt": attempt, "valid": False, "errors": errors},
                        parents=[("review", review_id)],
                    )
                    if attempt == self.budget.limits.correction_attempts:
                        raise
            await self.store.finish(
                self.active.run_id,
                review_id,
                record | {"status": "SUCCEEDED", "decision": decision.model_dump()},
            )
        except BaseException as exc:
            await self.store.finish(
                self.active.run_id,
                review_id,
                record | {"status": "FAILED", "error": str(exc)[:2000]},
            )
            raise
        if decision.decision == "STOP":
            raise OrchestrationError("PLANNER_STOPPED", decision.reason)
        if decision.decision == "REVISE":
            await self._replace(decision)

    async def _replace(self, decision):
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
