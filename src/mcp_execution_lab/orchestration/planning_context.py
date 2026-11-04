"""Public host capabilities supplied to every initial planning stage."""


def execution_contract(mode):
    return {
        "mode": mode,
        "representation": "python" if mode in {"P1", "P2"} else "dag",
        "scheduling": (
            "The host executes the accepted plan, resolves references, and applies shared "
            "concurrency and run limits. Choose jobs and their dependencies from the request "
            "and discovered capabilities; the host prescribes no tool choice or sequence."
        ),
        "tool_access": (
            "The host connects to the discovered MCP servers and checks calls to selected "
            "tools. Generated Python uses the supplied SDK in Docker. Data calculations "
            "must be supported by selected tools; the host does not invent missing operations."
        ),
        "storage": (
            "The host registers input files and saves run records, model calls, tool results "
            "and links during execution. Tool-published files stay on disk with registered "
            "references. Required answer tables or other content must still be produced by "
            "tools that support those outputs."
        ),
        "reviews": {
            "owner": "host_runtime",
            "requires_mcp_tool": False,
            "model_replanning": mode in {"D2", "P2"},
            "behavior": (
                "The host applies task_rules.reviews at finished-attempt thresholds. "
                "D1/P1 record reached checkpoints without main-planner calls; D2/P2 ask "
                "the main planner to review remaining work. Unreached checkpoints stay "
                "unreached. Do not add a review tool or job to the plan."
            ),
        },
    }
