# Current source map

Updated: 2026-10-27. The active application is CSV data analysis with D1/D2/P1/P2.
D1/D2 execute graphs; P1/P2 execute model-written limited Python in Docker. Both paths
share the tool gate, worker model gateway, budgets, file checks and PostgreSQL records.

| Component | Current source under `src/mcp_execution_lab/` |
|---|---|
| CLI | `cli.py`, `orchestration/cli.py`, `evaluation/cli.py` |
| Planner | `orchestration/planner.py`, `planning_context.py`, `graph.py`, `programs.py`, `program_arguments.py` |
| Executor | `orchestration/runtime.py`, `executor.py`, `program_executor.py`, `reviews.py`, `broker.py`, `mcp.py` |
| Python runner | `orchestration/program_container.py`, `program_sdk/`; image definition in `containers/csv_python/Dockerfile` |
| Model calls and usage | `orchestration/model_clients.py`, `model.py`, `model_pacing.py`, `budget.py`, `tokens.py` |
| Storage | `orchestration/storage.py`, `files.py`, `atomic_json.py` |
| Agents | `agents/understanding/`, `cleaning/`, `combining/`, `analysis/`, `prediction/`, `report/`, and `common/` |
| Evaluation | `evaluation/`: suites, independent answer checks, human review, matched batches, comparison and tokens |
| Services | `orchestration/server.py`; root `start_agents.ps1` and `stop_agents.ps1` |

The reusable background queue is `scripts/evaluation_queue.py`, launched with
`start_evaluation.ps1`. It monitors saved state without model calls. The completed Q01
batch's report-specific wrapper is retained locally with cleanup records.

Read the [setup guide](../../README.md), [planner/executor guide](../Planner%20and%20Executor/Running.md),
[P1](../Planner%20and%20Executor/P1.md), [P2](../Planner%20and%20Executor/P2.md),
[agent guide](../Agents/Running.md), and [evaluation guide](../evaluation/Running.md).
The [results summary](../evaluation/Results.md) records the current twelve question/mode
results and their limits. [Progress](../progress.md) retains the dated validation history.

## Historical material

The [2026-10-23 walkthrough](2026-10-23-before-cleanup/README.md) and its evidence remain
intact. They describe the earlier source; removed module links and old status statements
are historical. The superseded pricing implementation is absent from active source.
Its old guides were removed from the versioned tree during the 2026-10-27 cleanup,
with verified copies retained in local `reports/repository_cleanup_2026-10-27/`.

Runs, batches, detailed reports, user CSVs and historical databases remain on disk and
outside normal commits. The original [research build guide](../reference/Execution_Engine_Research_App_Build_Guide.md)
is preserved. No retained run evidence was selected for deletion.
