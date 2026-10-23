"""Resolve only registered data and saved results; conditions never evaluate code."""

import operator

from .graph import project
from .models import OrchestrationError

comparisons = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
}


class Resolver:
    def __init__(self, handoff, files, results, snapshots, states=None):
        self.handoff, self.files = handoff, files
        self.results, self.snapshots = results, snapshots
        self.states = states if states is not None else {}

    async def condition(self, condition):
        left = await self.resolve(condition.left)
        right = await self.resolve(condition.right)
        try:
            return bool(comparisons[condition.op](left, right))
        except TypeError as exc:
            raise OrchestrationError(
                "CONDITION_TYPE", "Condition compares incompatible values."
            ) from exc

    async def resolve(self, binding):
        if binding.kind == "list":
            return [await self.resolve(item) for item in binding.items]
        if binding.kind == "object":
            return {key: await self.resolve(item) for key, item in binding.fields.items()}
        if binding.kind == "status":
            return project({"state": self.states[binding.key]}, binding.path)
        if binding.kind == "choice":
            branch = (
                binding.when_true if await self.condition(binding.condition) else binding.when_false
            )
            return await self.resolve(branch)
        if binding.kind == "literal":
            value = binding.value
        elif binding.kind == "task":
            value = self.handoff.task.model_dump(mode="json")
        elif binding.kind == "dataset":
            dataset = next(
                (item for item in self.handoff.datasets if item.ref.id == binding.key), None
            )
            if dataset is None:
                raise OrchestrationError("BINDING_UNAVAILABLE", "Unregistered input dataset.")
            stored = await self.files.store.get(self.handoff.run_id, dataset.ref.id)
            if stored["payload"]["dataset"] != dataset.model_dump(mode="json"):
                raise OrchestrationError(
                    "FILE_REFERENCE", "Dataset differs from its registered version."
                )
            await self.files.verify_csv(self.handoff.run_id, dataset.ref)
            value = dataset.ref.model_dump(mode="json")
        else:
            values = self.results if binding.kind == "step" else self.snapshots
            if binding.key not in values:
                raise OrchestrationError(
                    "BINDING_UNAVAILABLE", "Required producer has no valid output."
                )
            value = await self.files.read_json(self.handoff.run_id, values[binding.key])
        return project(value, binding.path)
