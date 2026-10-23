"""Structural checks only: the model owns tool choice and dependency order."""

from graphlib import CycleError, TopologicalSorter

from jsonschema import Draft202012Validator

from .models import Binding, OrchestrationError
from .schemas import at_path, dereference, incompatible


def graph_error(message):
    raise OrchestrationError("PLAN_INVALID", message)


def project(value, path):
    try:
        for part in path:
            if isinstance(value, list):
                if type(part) is not int or part < 0:
                    raise KeyError(part)
            elif not isinstance(value, dict) or not isinstance(part, str):
                raise KeyError(part)
            value = value[part]
        return value
    except (KeyError, IndexError, TypeError) as exc:
        raise OrchestrationError("BINDING_UNAVAILABLE", f"Missing output path: {path}") from exc


def schema_path(schema, path):
    """Check published property paths, without guessing unpublished output structure."""
    if schema is None:
        return
    root = schema
    for part in path:
        for _ in range(20):
            if "$ref" not in schema:
                break
            reference = schema["$ref"]
            if not reference.startswith("#/"):
                return
            schema = project(
                root,
                [key.replace("~1", "/").replace("~0", "~") for key in reference[2:].split("/")],
            )
        if isinstance(part, int):
            if schema.get("type") not in (None, "array"):
                graph_error("An output path indexes a value that is not an array.")
            schema = schema.get("items", {})
        else:
            properties = schema.get("properties", {})
            if part in properties:
                schema = properties[part]
            elif schema.get("additionalProperties", True) is False:
                graph_error(f"A producer has no published output field {part!r}.")
            else:
                return


def validate_breakdown(breakdown, cache):
    selected = breakdown.selection.tool_keys
    if len(set(selected)) != len(selected):
        graph_error("A selected tool appears more than once.")
    known = {tool.key for tool in cache.tools}
    if not set(selected) <= known:
        graph_error("Selection contains a tool outside this run's cache.")
    if breakdown.selection.missing_capabilities:
        raise OrchestrationError(
            "MISSING_CAPABILITY", "; ".join(breakdown.selection.missing_capabilities)
        )
    ids = [task.id for task in breakdown.subtasks]
    if len(ids) != len(set(ids)):
        graph_error("Subtasks need distinct IDs.")
    if {task.tool_key for task in breakdown.subtasks} != set(selected):
        graph_error("Each selected tool needs a job and every job needs a selected tool.")


def validate_plan(plan, breakdown, cache, datasets, limits, *, snapshots=None, completed=()):
    validate_breakdown(breakdown, cache)
    if len(plan.steps) > limits.max_steps:
        graph_error("The plan exceeds its step allowance.")
    nodes = {node.id: node for node in plan.steps}
    if len(nodes) != len(plan.steps):
        graph_error("Duplicate step IDs.")
    if set(nodes) & set(completed):
        graph_error("A replacement must contain remaining work, not completed steps.")
    for node in plan.steps:
        if len(set(node.depends_on)) != len(node.depends_on):
            graph_error("A dependency is repeated.")
        if not set(node.depends_on) <= nodes.keys():
            graph_error("An earlier step does not exist.")
    try:
        order = list(
            TopologicalSorter({node.id: node.depends_on for node in plan.steps}).static_order()
        )
    except CycleError as exc:
        raise OrchestrationError("PLAN_INVALID", "The plan contains a circle.") from exc
    ancestors = {}
    for name in order:
        ancestors[name] = set(nodes[name].depends_on)
        for dependency in nodes[name].depends_on:
            ancestors[name].update(ancestors[dependency])
    jobs = {task.id: task for task in breakdown.subtasks}
    if {node.subtask_id for node in plan.steps} != set(jobs):
        graph_error("DAG steps and assigned subtasks do not agree.")
    if len(plan.steps) != len(jobs):
        graph_error("Each step needs its own assigned subtask.")
    dataset_ids = {dataset.ref.id for dataset in datasets}
    snapshots = snapshots or {}

    def condition(value, consumer, assumptions):
        binding(value.left, consumer, assumptions)
        binding(value.right, consumer, assumptions)

    def binding(value: Binding, consumer, assumptions=()):
        if value.kind in {"list", "object"}:
            for item in value.items if value.kind == "list" else value.fields.values():
                binding(item, consumer, assumptions)
        elif value.kind == "status":
            if value.key not in nodes or (
                consumer is not None and value.key not in ancestors[consumer]
            ):
                graph_error("A status input needs a known dependency.")
            if consumer is not None and nodes[consumer].dependency_policy != "settled":
                graph_error("Failure-status inputs require an explicit settled dependency policy.")
            schema_path(
                {
                    "type": "object",
                    "properties": {"state": {"type": "string"}},
                    "additionalProperties": False,
                },
                value.path,
            )
        elif value.kind == "choice":
            condition(value.condition, consumer, assumptions)
            binding(value.when_true, consumer, (*assumptions, (value.condition, True)))
            binding(value.when_false, consumer, (*assumptions, (value.condition, False)))
        elif value.kind == "dataset":
            if value.key not in dataset_ids:
                graph_error("A dataset reference is not registered in this run.")
            schema_path(
                {
                    "type": "object",
                    "properties": {key: {} for key in ("id", "run_id", "kind", "sha256")},
                    "additionalProperties": False,
                },
                value.path,
            )
        elif value.kind == "snapshot":
            if value.key not in snapshots:
                graph_error("A saved output is unavailable in this run's snapshot.")
        elif value.kind == "step":
            if value.key not in nodes:
                graph_error("An output references an unknown producer.")
            if consumer is not None and value.key not in ancestors[consumer]:
                graph_error("An input references a producer without a dependency path.")
            producer = nodes[value.key]
            if producer.condition is not None and (producer.condition, True) not in assumptions:
                graph_error(
                    "A conditional producer needs a guarded consumer or explicit alternative."
                )
            schema_path(cache.lookup(producer.server, producer.tool).output_schema, value.path)
        elif value.kind == "literal":
            project(value.value, value.path)

    def input_types(value, expected, root):
        expected = dereference(expected, root)
        if value.kind == "choice":
            input_types(value.when_true, expected, root)
            input_types(value.when_false, expected, root)
            return
        if value.kind == "list":
            if incompatible({"type": "array"}, {}, expected, root):
                graph_error("A list input is incompatible with the receiving argument.")
            if len(value.items) < expected.get("minItems", 0) or len(value.items) > expected.get(
                "maxItems", 1000000
            ):
                graph_error("An input list has an invalid item count.")
            for item in value.items:
                input_types(item, expected.get("items", {}), root)
        elif value.kind == "object":
            if incompatible({"type": "object"}, {}, expected, root):
                graph_error("An object input is incompatible with the receiving argument.")
            if not set(expected.get("required", [])) <= value.fields.keys():
                graph_error("An object input is missing required fields.")
            properties = expected.get("properties", {})
            if (
                expected.get("additionalProperties") is False
                and not value.fields.keys() <= properties.keys()
            ):
                graph_error("An object input contains unsupported fields.")
            for key, item in value.fields.items():
                input_types(item, properties.get(key, {}), root)
        elif value.kind == "literal":
            errors = list(
                Draft202012Validator(root)
                .evolve(schema=expected)
                .iter_errors(project(value.value, value.path))
            )
            if errors:
                graph_error(f"Invalid literal argument: {errors[0].message}")
        elif value.kind == "step":
            producer = nodes[value.key]
            published = cache.lookup(producer.server, producer.tool).output_schema or {}
            source, source_root = at_path(published, value.path)
            if incompatible(source, source_root, expected, root):
                graph_error("A producer output type is incompatible with its receiving input.")
        elif value.kind == "dataset":
            published = {
                "type": "object",
                "properties": {
                    key: {"type": "string"} for key in ("id", "run_id", "kind", "sha256")
                },
            }
            source, source_root = at_path(published, value.path)
            if incompatible(source, source_root, expected, root):
                graph_error("A dataset reference type is incompatible with its receiving input.")

    for node in plan.steps:
        tool = cache.lookup(node.server, node.tool)
        job = jobs[node.subtask_id]
        if tool.key != job.tool_key:
            graph_error("The DAG uses a different tool than its assigned subtask.")
        if tool.raw_definition.get("meta", {}).get("lab_worker_role"):
            assigned = node.arguments.get("job")
            if assigned is None or assigned.kind != "literal" or assigned.value != job.job:
                graph_error("The worker job must exactly match its assigned subtask.")
        schema = tool.input_schema
        properties = schema.get("properties", {})
        if not set(schema.get("required", [])) <= node.arguments.keys():
            graph_error("Required tool arguments are missing.")
        if (
            schema.get("additionalProperties", True) is False
            and not node.arguments.keys() <= properties.keys()
        ):
            graph_error("The tool does not accept one of the argument names.")
        assumptions = ((node.condition, True),) if node.condition else ()
        if node.condition:
            condition(node.condition, node.id, ())
        for name, value in node.arguments.items():
            binding(value, node.id, assumptions)
            input_types(value, properties.get(name, {}), schema)
            if value.kind == "literal" and name in properties:
                # Retain $defs when validating a property's schema.
                validator = Draft202012Validator(schema).evolve(schema=properties[name])
                errors = list(validator.iter_errors(project(value.value, value.path)))
                if errors:
                    graph_error(f"Invalid literal argument {name}: {errors[0].message}")
    for value in plan.outputs.values():
        binding(value, None)
    return order
