"""Language-conformance checks only; Docker is the execution security boundary."""

import ast
import math

VERSION = "csv-python-v1"
ALLOWED = (
    ast.Module,
    ast.AsyncFunctionDef,
    ast.arguments,
    ast.arg,
    ast.Assign,
    ast.Expr,
    ast.Await,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Dict,
    ast.List,
    ast.Tuple,
    ast.Subscript,
    ast.If,
    ast.Return,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.IfExp,
    ast.keyword,
    ast.Pass,
)


def method(node):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sdk"
    ):
        return node.func.attr
    return None


def validate_source(source, jobs, max_chars=100000):
    if not isinstance(source, str) or not source.strip() or len(source) > max_chars:
        raise ValueError("Program source is empty or exceeds its character allowance.")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError("Program must be valid Python.") from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.AsyncFunctionDef):
        raise ValueError("Provide exactly one async function: run(sdk, inputs).")
    function = tree.body[0]
    args = function.args
    if (
        function.name != "run"
        or [arg.arg for arg in args.args] != ["sdk", "inputs"]
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
        or args.defaults
        or args.kw_defaults
        or function.decorator_list
        or function.returns
        or any(arg.annotation for arg in args.args)
    ):
        raise ValueError("The function must have the exact signature run(sdk, inputs).")
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    names = {"sdk", "inputs"}
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise ValueError(f"Unsupported program syntax: {type(node).__name__}.")
        if isinstance(node, ast.Constant) and (
            type(node.value) not in {str, int, float, bool, type(None)}
            or (isinstance(node.value, float) and not math.isfinite(node.value))
        ):
            raise ValueError("Program literals must be finite JSON values.")
        if isinstance(node, ast.AsyncFunctionDef) and node is not function:
            raise ValueError("Nested functions are not supported.")
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Assign only to one local name, not an object or subscript.")
            name = node.targets[0].id
            if name in {"sdk", "inputs", "run"} or name.startswith("_"):
                raise ValueError("SDK, inputs, and private names cannot be reassigned.")
            names.add(name)
        if isinstance(node, ast.Dict) and any(key is None for key in node.keys):
            raise ValueError("Dictionary unpacking is not supported.")
        if isinstance(node, ast.Attribute):
            parent = parents.get(node)
            if (
                not isinstance(parent, ast.Call)
                or parent.func is not node
                or method(parent) not in {"call", "parallel"}
            ):
                raise ValueError("Use dictionary indexing; only SDK method attributes are allowed.")
        if isinstance(node, ast.Await) and method(node.value) not in {"call", "parallel"}:
            raise ValueError("Await only sdk.call or sdk.parallel.")
        if not isinstance(node, ast.Call):
            continue
        api = method(node)
        parent = parents.get(node)
        if api == "call":
            if (
                len(node.args) != 2
                or any(key.arg != "handles" for key in node.keywords)
                or len(node.keywords) > 1
            ):
                raise ValueError("Use sdk.call(subtask_id, arguments, handles=[failed_ids]).")
            identity = node.args[0]
            if (
                not isinstance(identity, ast.Constant)
                or type(identity.value) is not str
                or identity.value not in jobs
            ):
                raise ValueError(
                    "Each call must name an exact assigned subtask ID as a string literal."
                )
            calls.append(identity.value)
            if not isinstance(parent, ast.Await) and method(parent) != "parallel":
                raise ValueError("Await each call or include it directly in sdk.parallel.")
        elif api == "parallel":
            if (
                node.keywords
                or not node.args
                or any(method(arg) != "call" for arg in node.args)
                or not isinstance(parent, ast.Await)
            ):
                raise ValueError("Use await sdk.parallel(sdk.call(...), sdk.call(...)).")
        else:
            raise ValueError("Only sdk.call and sdk.parallel may be called.")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in names or node.id.startswith("_"):
                raise ValueError(f"Unknown or private program name: {node.id}.")
            if node.id == "sdk" and not isinstance(parents.get(node), ast.Attribute):
                raise ValueError("The SDK object may only be used to call its public methods.")
    if len(calls) != len(set(calls)) or set(calls) != set(jobs):
        raise ValueError(
            "Each assigned subtask needs exactly one call site; conditions may skip it."
        )
    if not any(isinstance(node, ast.Return) for node in ast.walk(function)):
        raise ValueError("Return the declared final output mapping.")
    return tree
