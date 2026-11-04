"""Check known Python tool arguments from syntax alone; never run generated code."""

import ast

from jsonschema import Draft202012Validator

from ..program_sdk.policy import method
from .models import OrchestrationError
from .schemas import dereference

UNKNOWN = object()


def known(value):
    if isinstance(value, dict):
        return all(known(item) for item in value.values())
    if isinstance(value, list):
        return all(known(item) for item in value)
    return value is not UNKNOWN


def value_of(node, scope):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return scope.get(node.id, UNKNOWN)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [value_of(item, scope) for item in node.elts]
    if isinstance(node, ast.Dict):
        keys = [value_of(key, scope) for key in node.keys]
        if all(isinstance(key, str) for key in keys):
            return {key: value_of(item, scope) for key, item in zip(keys, node.values, strict=True)}
    if isinstance(node, ast.Subscript):
        container, key = value_of(node.value, scope), value_of(node.slice, scope)
        if isinstance(container, dict) and isinstance(key, str):
            return container.get(key, UNKNOWN)
        if isinstance(container, list) and type(key) is int and 0 <= key < len(container):
            return container[key]
    return UNKNOWN


def invalid(label, message):
    raise OrchestrationError("PLAN_INVALID", f"{label}: {message}")


def check_value(value, schema, root, label):
    if value is UNKNOWN:
        return  # The shared broker validates actual inputs before MCP dispatch.
    if known(value):
        error = next(Draft202012Validator(root).evolve(schema=schema).iter_errors(value), None)
        if error:
            invalid(label, error.message)
        return
    schema = dereference(schema, root)
    if "anyOf" in schema or "oneOf" in schema:
        return  # A data-dependent value cannot select a schema branch here.
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            invalid(label, f"required tool arguments are missing: {sorted(missing)}.")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            invalid(label, f"unsupported arguments: {sorted(value.keys() - properties.keys())}.")
        for name, item in value.items():
            check_value(item, properties.get(name, {}), root, f"{label}.{name}")
    elif isinstance(value, list):
        for item in value:
            check_value(item, schema.get("items", {}), root, label)


def validate_arguments(tree, breakdown, cache):
    """Follow immutable locals and both branches; unknown values stay runtime-checked."""
    tools = {tool.key: tool for tool in cache.tools}
    jobs = {job.id: job for job in breakdown.subtasks}

    def expression(node, scope):
        for part in ast.walk(node):
            if method(part) != "call":
                continue
            job = jobs[part.args[0].value]  # validate_source already checked call identities.
            tool = tools[job.tool_key]
            arguments = value_of(part.args[1], scope)
            label = f"{job.id} ({tool.key})"
            check_value(arguments, tool.input_schema, tool.input_schema, label)
            if isinstance(arguments, dict) and tool.raw_definition.get("meta", {}).get(
                "lab_worker_role"
            ):
                assigned = arguments.get("job", UNKNOWN)
                if assigned is not UNKNOWN and assigned != job.job:
                    invalid(label, "worker job must exactly match its assigned subtask.")

    def statements(body, scope):
        for statement in body:
            if isinstance(statement, ast.If):
                expression(statement.test, scope)
                before = dict(scope)
                left, right = dict(scope), dict(scope)
                statements(statement.body, left)
                statements(statement.orelse, right)
                for name in before.keys() | left.keys() | right.keys():
                    a, b = left.get(name, UNKNOWN), right.get(name, UNKNOWN)
                    scope[name] = a if a == b else UNKNOWN
            else:
                expression(statement, scope)
                if isinstance(statement, ast.Assign):
                    scope[statement.targets[0].id] = value_of(statement.value, scope)

    statements(tree.body[0].body, {})
