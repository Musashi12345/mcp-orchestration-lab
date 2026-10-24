"""Direct Python generation contract, without a DAG intermediate."""

from ..program_sdk.policy import VERSION, validate_source
from .graph import validate_breakdown
from .model import SYSTEM_PROMPT
from .models import OrchestrationError

PROGRAM_INSTRUCTIONS = (
    SYSTEM_PROMPT
    + """
For this response, write Python directly instead of a DAG. Return the PythonProgram
record: source and the distinct names of final outputs. Define exactly one async function
run(sdk, inputs). Use local assignments, dictionary/list values, dictionary indexing,
if/else, comparisons, boolean conditions, and return. No imports, loops, helper functions,
arithmetic, exceptions, file/network/database access, or built-in function calls.
inputs['datasets'] maps each registered dataset ID to its FileRef; inputs['task'] is the
Main Task. Call await sdk.call('EXACT_SUBTASK_ID', arguments). The host selects that
subtask's already assigned server/tool and checks all arguments, including the exact job.
Each assigned subtask has one call site; conditions may skip it. Repeated tool use needs
distinct assigned subtasks. A call returns {'state','value','output','error'}: state is
SUCCEEDED or FAILED, value is the checked structured tool result, output is its saved
FileRef, and error contains a public code/message for confirmed failures. An unknown
outcome stops execution and cannot be bypassed. For a prewritten fallback, pass
handles=['FAILED_SUBTASK_ID'] to the recovery call; only its success handles that failure.
Use await sdk.parallel(sdk.call(...), sdk.call(...)) for independent calls; returned items
preserve argument order and the host applies the shared concurrency limit. Return a JSON
object with exactly the declared output names. Use only registered input/output references.
Do not request a review, rewrite the program during execution, or execute analysis in
Python. The supported operations inside agents perform data calculations.
"""
)


def validate_program(program, breakdown, cache, limits):
    validate_breakdown(breakdown, cache)
    if len(breakdown.subtasks) > limits.max_steps:
        raise OrchestrationError("PLAN_INVALID", "Program exceeds the shared step allowance.")
    try:
        validate_source(
            program.source, {task.id for task in breakdown.subtasks}, limits.max_prompt_chars
        )
    except ValueError as exc:
        raise OrchestrationError("PLAN_INVALID", str(exc)) from exc
    return VERSION
