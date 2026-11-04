"""Published schemas validate program inputs without executing Python or an MCP call."""

import pytest

from mcp_execution_lab.orchestration.models import (
    Breakdown,
    Limits,
    OrchestrationError,
    PythonProgram,
    ToolCache,
    ToolDefinition,
)
from mcp_execution_lab.orchestration.programs import validate_program


def check(body):
    tool = ToolDefinition(
        server="example",
        name="transform",
        description="Transform only as specified",
        plain_description="Transform the supplied data",
        input_schema={
            "type": "object",
            "properties": {
                "job": {"type": "string"},
                "dataset": {"type": "object"},
                "options": {"$ref": "#/$defs/Options"},
            },
            "required": ["job", "dataset", "options"],
            "additionalProperties": False,
            "$defs": {
                "Options": {
                    "type": "object",
                    "properties": {"fields": {"type": "array", "items": {"type": "string"}}},
                    "required": ["fields"],
                    "additionalProperties": False,
                }
            },
        },
    )
    breakdown = Breakdown.model_validate(
        {
            "selection": {"tool_keys": [tool.key], "reasons": ["User request"]},
            "subtasks": [
                {
                    "id": "work",
                    "tool_key": tool.key,
                    "job": "Transform",
                    "expected_outputs": ["data"],
                }
            ],
        }
    )
    program = PythonProgram(
        source="async def run(sdk, inputs):\n"
        + body
        + "\n    return {'answer': result['output']}\n",
        outputs=["answer"],
    )
    return validate_program(program, breakdown, ToolCache(tools=[tool]), Limits())


@pytest.mark.parametrize(
    "body",
    [
        "    result = await sdk.call('work', {'job': 'Transform', 'dataset': inputs['file']})",
        "    args = {'job': 'Transform', 'dataset': inputs['file']}\n"
        "    alias = args\n    result = await sdk.call('work', alias)",
        "    if inputs['ready']:\n"
        "        result = await sdk.call('work', {'job': 'Transform', 'dataset': inputs['file']})",
    ],
)
def test_missing_required_arguments_are_rejected_for_inline_locals_and_branches(body):
    with pytest.raises(OrchestrationError, match="options") as error:
        check(body)
    assert error.value.code == "PLAN_INVALID"


@pytest.mark.parametrize(
    "options",
    ["{}", "{'fields': 'wrong'}", "{'fields': [7]}", "{'fields': [], 'invented': True}"],
)
def test_known_nested_options_are_checked_against_local_schema_refs(options):
    with pytest.raises(OrchestrationError):
        check(
            "    result = await sdk.call('work', {'job': 'Transform', "
            f"'dataset': inputs['file'], 'options': {options}}})"
        )


@pytest.mark.parametrize(
    "setup,argument",
    [
        ("", "{'job': 'Transform', 'dataset': inputs['file'], 'options': {'fields': ['name']}}"),
        (
            "    options = {'fields': ['name']}\n"
            "    args = {'job': 'Transform', 'dataset': inputs['file'], 'options': options}\n",
            "args",
        ),
        (
            "    if inputs['ready']:\n        opts = {'fields': ['name']}\n"
            "    else:\n        opts = {'fields': ['name']}\n",
            "{'job': 'Transform', 'dataset': inputs['file'], 'options': opts}",
        ),
        ("", "inputs['data_dependent_arguments']"),
    ],
)
def test_valid_known_arguments_and_unknown_runtime_values_are_not_executed(setup, argument):
    assert check(setup + f"    result = await sdk.call('work', {argument})") == "csv-python-v1"
