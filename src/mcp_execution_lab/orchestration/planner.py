"""Discovery -> Main Task -> tool choice -> subtasks -> checked plan."""

import asyncio
from pathlib import Path

from .graph import validate_breakdown, validate_plan
from .mcp import Connections
from .models import (
    Breakdown,
    Handoff,
    MainTask,
    OrchestrationError,
    Plan,
    Selection,
    fingerprint,
)
from .provenance import source_identity


class Planner:
    def __init__(self, store, files, model, budget, servers, *, configuration=None):
        self.store, self.files, self.model = store, files, model
        self.budget, self.servers = budget, servers
        self.configuration = configuration or {
            "servers": [server.model_dump(mode="json") for server in servers],
            "limits": budget.limits.model_dump(mode="json"),
        }

    async def _stage(self, run_id, name, action):
        stage_id = await self.store.put(run_id, "stage", {"name": name, "status": "RUNNING"})
        try:
            result = await action(stage_id)
            await self.store.finish(run_id, stage_id, {"name": name, "status": "SUCCEEDED"})
            return result
        except BaseException as exc:
            await self.store.finish(
                run_id, stage_id, {"name": name, "status": "FAILED", "error": str(exc)[:4000]}
            )
            raise

    async def _generate(self, run_id, stage, result_type, context, validate=None):
        async def produce(stage_id):
            errors = []
            previous = None
            for attempt in range(self.budget.limits.correction_attempts + 1):
                try:
                    result = await self.model.ask(
                        run_id,
                        stage,
                        result_type,
                        context | {"validation_errors": errors, "previous_candidate": previous},
                        parent=stage_id,
                    )
                    previous = result.model_dump(mode="json")
                    await self.store.put(
                        run_id,
                        "candidate",
                        {
                            "stage": stage,
                            "attempt": attempt,
                            "value": result.model_dump(mode="json"),
                        },
                        parents=[("stage", stage_id)],
                    )
                    if validate:
                        validate(result)
                    return result
                except OrchestrationError as exc:
                    if exc.code not in {"MODEL_FORMAT", "PLAN_INVALID", "UNKNOWN_TOOL"}:
                        raise
                    errors = [{"code": exc.code, "message": str(exc)}]
                    await self.store.put(
                        run_id,
                        "validation",
                        {
                            "stage": stage,
                            "attempt": attempt,
                            "valid": False,
                            "errors": errors,
                        },
                        parents=[("stage", stage_id)],
                    )
                    if attempt == self.budget.limits.correction_attempts:
                        raise

        return await self._stage(run_id, stage, produce)

    async def plan(
        self,
        request: str,
        sources: list[Path],
        *,
        mode="D1",
        rules=None,
        encoding="utf-8-sig",
        delimiter=",",
    ):
        from .models import TaskRules

        if mode not in {"D1", "D2"}:
            raise OrchestrationError("MODE", "The new DAG path accepts D1 and D2.")
        rules = rules or TaskRules()
        if mode == "D2" and len(rules.reviews) != 2:
            raise OrchestrationError("TASK_RULES", "D2 requires two task-defined review points.")
        if not request.strip() or not sources:
            raise OrchestrationError("INPUT", "Provide a user request and at least one CSV.")
        run_id = await self.store.create_run(
            {
                "request": request,
                "mode": mode,
                "rules": rules.model_dump(),
                "limits": self.budget.limits.model_dump(),
                "is_model": self.model.client.is_model,
                "provider": self.model.client.provider,
                "model_id": self.model.config.model_id,
                "exploratory": not self.model.client.is_model,
                "study_stage": "development",
                **source_identity(),
            }
        )
        try:
            await self.store.put(
                run_id,
                "configuration",
                {
                    "settings": self.configuration,
                    "fingerprint": fingerprint(self.configuration),
                    "csv_reading": {"encoding": encoding, "delimiter": delimiter},
                },
            )
            async with asyncio.timeout(self.budget.remaining):
                return await self._prepare(
                    run_id, request, sources, mode, rules, encoding, delimiter
                )
        except BaseException as exc:
            status = (
                "INTERRUPTED"
                if isinstance(exc, asyncio.CancelledError)
                else (
                    "NEEDS_CLARIFICATION"
                    if getattr(exc, "code", "") in {"NEEDS_CLARIFICATION", "MISSING_CAPABILITY"}
                    else "PLANNING_FAILED"
                )
            )
            await self.store.transition(run_id, status, {"error": str(exc)[:4000]})
            raise

    async def _prepare(self, run_id, request, sources, mode, rules, encoding, delimiter):
        async def discover(stage_id):
            async with Connections(self.servers) as connections:
                cache = await connections.discover()
            record_id = await self.store.put(
                run_id,
                "tool_cache",
                {"cache": cache.model_dump(mode="json"), "fingerprint": cache.digest},
                parents=[("stage", stage_id)],
            )
            current = source_identity()["source_sha256"]
            for tool in cache.tools:
                metadata = tool.raw_definition.get("meta", {})
                if (
                    metadata.get("lab_worker_role")
                    and metadata.get("lab_worker_source_sha256") != current
                ):
                    raise OrchestrationError(
                        "WORKER_CODE_CHANGED",
                        "Restart the agent services to load the current project code.",
                    )
            return cache, record_id

        cache, cache_id = await self._stage(run_id, "tool_discovery", discover)

        async def read_files(stage_id):
            result = []
            for source in sources:
                self.budget.check()
                dataset = await self.files.register_csv(
                    run_id, source, encoding=encoding, delimiter=delimiter
                )
                result.append(dataset)
                await self.store.event(
                    run_id, "dataset_registered", {"stage": stage_id, "dataset_id": dataset.ref.id}
                )
            return result

        datasets = await self._stage(run_id, "csv_reading", read_files)
        dataset_ids = {dataset.ref.id for dataset in datasets}

        def check_task(task):
            if not set(task.dataset_ids) <= dataset_ids or not task.dataset_ids:
                raise OrchestrationError(
                    "PLAN_INVALID", "Main Task has unregistered or missing datasets."
                )

        task = await self._generate(
            run_id,
            "main_task",
            MainTask,
            {
                "original_request": request,
                "datasets": [dataset.model_dump() for dataset in datasets],
                "task_rules": rules.model_dump(),
            },
            check_task,
        )
        task_id = await self.store.put(
            run_id,
            "main_task",
            task.model_dump(),
            parents=[("dataset", dataset.ref.id) for dataset in datasets],
        )
        if task.clarification_questions:
            raise OrchestrationError("NEEDS_CLARIFICATION", "; ".join(task.clarification_questions))
        common = {
            "original_request": request,
            "main_task": task.model_dump(),
            "datasets": [dataset.model_dump() for dataset in datasets],
            "tool_cache": cache.model_dump(),
            "task_rules": rules.model_dump(),
        }

        def check_selection(selection):
            known = {tool.key for tool in cache.tools}
            if not set(selection.tool_keys) <= known:
                raise OrchestrationError(
                    "UNKNOWN_TOOL",
                    f"Copy exact discovered keys, including server identity: {sorted(known)}",
                )
            if selection.missing_capabilities:
                raise OrchestrationError(
                    "MISSING_CAPABILITY", "; ".join(selection.missing_capabilities)
                )

        selection = await self._generate(
            run_id, "tool_selection", Selection, common, check_selection
        )
        selection_id = await self.store.put(
            run_id,
            "tool_selection",
            selection.model_dump(),
            parents=[("task", task_id), ("cache", cache_id)],
        )
        breakdown = await self._generate(
            run_id,
            "subtasks",
            Breakdown,
            common | {"draft_selection": selection.model_dump()},
            lambda value: validate_breakdown(value, cache),
        )
        breakdown_id = await self.store.put(
            run_id,
            "breakdown",
            breakdown.model_dump(),
            parents=[("task", task_id), ("cache", cache_id), ("draft_selection", selection_id)],
        )
        plan = await self._generate(
            run_id,
            "dag",
            Plan,
            common | {"breakdown": breakdown.model_dump()},
            lambda value: validate_plan(value, breakdown, cache, datasets, self.budget.limits),
        )
        plan_id = await self.store.put(
            run_id,
            "plan",
            {
                "version": 1,
                "plan": plan.model_dump(),
                "valid": True,
            },
            parents=[("breakdown", breakdown_id), ("cache", cache_id), ("task", task_id)],
        )
        handoff = Handoff(
            run_id=run_id,
            mode=mode,
            task=task,
            datasets=datasets,
            cache=cache,
            cache_record=cache_id,
            task_record=task_id,
            breakdown=breakdown,
            plan=plan,
            plan_record=plan_id,
            rules=rules,
        )
        await self.store.put(
            run_id,
            "handoff",
            {"handoff": handoff.model_dump(mode="json"), "usage": self.budget.summary()},
            parents=[("plan", plan_id)],
        )
        await self.store.transition(run_id, "READY_FOR_EXECUTION")
        return handoff
