"""Composition boundary: plan first, execute only an accepted saved handoff."""

from pathlib import Path

from .budget import Budget
from .executor import Executor
from .files import Files
from .model import ModelCalls
from .model_clients import make_planner
from .models import Handoff, OrchestrationError, fingerprint
from .planner import Planner


class Application:
    def __init__(self, store, root: Path, settings, *, client=None):
        self.store, self.root, self.settings = store, root, settings
        self.client = client or make_planner(settings.model)

    def components(self, limits=None):
        budget = Budget(limits or self.settings.limits)
        files = Files(self.root, self.store, budget.limits)
        model = ModelCalls(self.client, self.settings.model, self.store, files, budget)
        return budget, files, model

    async def plan(self, request, sources, *, mode="D1", encoding="utf-8-sig", delimiter=","):
        budget, files, model = self.components()
        planner = Planner(
            self.store,
            files,
            model,
            budget,
            self.settings.servers,
            configuration=self.settings.model_dump(mode="json"),
        )
        handoff = await planner.plan(
            request,
            sources,
            mode=mode,
            rules=self.settings.task_rules,
            encoding=encoding,
            delimiter=delimiter,
        )
        return handoff

    async def execute(self, run_id):
        saved = await self.store.list_records(run_id, "handoff")
        configurations = await self.store.list_records(run_id, "configuration")
        if not saved or not configurations:
            raise OrchestrationError("HANDOFF", "No accepted planner handoff is available.")
        expected = configurations[-1]["payload"]["fingerprint"]
        if fingerprint(self.settings.model_dump(mode="json")) != expected:
            raise OrchestrationError(
                "CONFIG_CHANGED", "Execution settings differ from this run's planning settings."
            )
        handoff = Handoff.model_validate(saved[-1]["payload"]["handoff"])
        budget, files, model = self.components()
        budget.restore(saved[-1]["payload"]["usage"])
        runner = Executor(self.store, files, budget, self.settings.servers, model)
        return await runner.run(handoff)
