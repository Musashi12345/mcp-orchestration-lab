# MCP Execution Lab

A CSV data-analysis research application. Give it a question and CSV files; its planner
discovers configured MCP tools, chooses the required jobs, and creates a checked DAG
or a limited Python program. The executor supports independent jobs in parallel. The main prompt
does not prescribe an agent order.

The six agents are Understanding, Cleaning, Combining, Analysis, Prediction, and Report.
Their models choose bounded recipes; handwritten Python performs the calculations.
Planning, worker calls, reviews, files, and results are recorded during each run.
Records use local PostgreSQL; original CSV copies and generated files stay on disk.

## Current scope

| Mode | Current CSV behavior |
|---|---|
| D1 | Model-created DAG; no main-planner review calls during execution. |
| D2 | Same runtime, with two configured review opportunities for remaining work. |
| P1 | Model writes one Python program; Docker runs it through the shared MCP tool gate. No main-planner calls during execution. |
| P2 | The same Python/Docker runtime, with D2's review opportunities and fresh runners for accepted remaining-work revisions. |

D1 can still use model calls for initial planning and inside selected agents. D2/P2 review
thresholds count finished attempted steps; short graphs may leave a review unreached.
Execution completion is separate from independent evaluation of the answer.

The superseded pricing experiments, generated-Python container runner, old grader, and
old dashboard have been removed. The shared CSV Python runner requires Docker with Linux containers;
D1/D2 do not. Earlier run files,
databases, batches, and reports are retained as historical evidence. See the
[cleanup/current-state note](docs/Cross-check/README.md).

## Setup and use

Use Python 3.12 and the locked project environment. On a fresh setup:

```powershell
uv sync --locked --python 3.12
```

Copy `.env.example` to `.env` and enter the local PostgreSQL connection. Keep the password
there. Configure the model route and call limits in `configs/agents.yaml` or
`configs/agents_stdio.yaml`. The Codex route uses the CLI's saved login; a command route
can use a trusted local router. See [the bridge contract](docs/planner_bridge.md).

From the project root:

```powershell
.\scripts\lab.ps1 analysis db-init
.\start_agents.ps1
.\stop_agents.ps1
```

Start launches the orchestrator and all six agents with saved process identities/logs.
Stop checks those identities before stopping their PIDs and process trees. These commands
do not submit a model request. Health confirms service readiness, not database or model
connectivity. The orchestrator is a local API; there is no dashboard.

For a CLI run with client-owned MCP subprocesses:

```powershell
.\scripts\lab.ps1 analysis run --query "Calculate total amount" --csv fixtures/data_analysis/example.csv --config configs/agents_stdio.yaml --mode D1
.\scripts\lab.ps1 analysis inspect --run RUN_ID
```

`analysis plan` saves a plan without executing tools; `analysis execute` starts an
accepted, unstarted run. Submitting a run uses configured model allowance. Keep both
PostgreSQL and the file root when backing up evidence.

For P1/P2, build the shared runner image first, then choose `--mode P1` or `--mode P2`:

```powershell
.\scripts\lab.ps1 analysis runner-build --config configs/agents_stdio.yaml
.\scripts\lab.ps1 analysis run --query "Calculate total amount" --csv fixtures/data_analysis/example.csv --config configs/agents_stdio.yaml --mode P1
```

The image uses a pinned official Python 3.12 slim base. Generated Python runs as a
non-root user with no network or host mounts, a read-only image, 1 CPU, 512 MiB memory,
64 processes, and 16 MiB temporary space. It receives references and checked results
over pipes. Rebuild after changing `program_sdk`; execution refuses an outdated image.
See [P1 details](docs/Planner%20and%20Executor/P1.md).
For P2's `KEEP`/`REVISE`/`STOP`, saved results, and recovery declarations, see
[P2 details](docs/Planner%20and%20Executor/P2.md).

## Evaluation and checks

The CSV evaluator has ten synthetic CSVs and fifteen public development tasks, independent
answer checks, run-linked grades, human review, and explicit matched D1/D2/P1/P2 reports.

```powershell
.\scripts\lab.ps1 eval list
.\scripts\check.ps1
# Include separate temporary native PostgreSQL integration tests:
$env:MCP_LAB_POSTGRES_TEST = '1'
# Also exercise the prebuilt P1 image with real Docker:
$env:MCP_LAB_DOCKER_TEST = '1'
.\scripts\check.ps1
```

Live Codex testing is separately opt-in with `MCP_LAB_CODEX_TEST=1` and consumes account
allowance. Normal tests use fixed model replies with actual MCP processes and calculations.
These are engineering/development checks, not evidence of a research winner.

Earlier CSV cleanup validation on 2026-10-23 passed lint/format checks and **131 tests,
with 1 live-model test skipped**, including native PostgreSQL and real MCP checks.
See [the saved results](reports/csv_cleanup_2026-10-23/README.md).
The subsequent P1 validation passed **180 tests with 1 live-model skip**, including real
Docker, MCP, native PostgreSQL, and service lifecycle checks. See [P1 test evidence](reports/p1_validation_2026-10-23/README.md).

P2 validation on 2026-10-25 passed Ruff/formatting and verified **221 non-live tests
across the full run and targeted completion, with 1 live-model skip**, including real
Docker/MCP, native PostgreSQL, API/service lifecycle, and matched four-mode independent
evaluation. See [P2 evidence](reports/p2_validation_2026-10-25/README.md).

## Code and guides

- `src/mcp_execution_lab/orchestration/`: planner, graph checks, executor, MCP adapter,
  broker, model clients, budgets, files, PostgreSQL records, and local API.
- `src/mcp_execution_lab/agents/`: six modular MCP agents and their shared worker support.
- `src/mcp_execution_lab/evaluation/`: CSV suites, independent grading, human review,
  matched batches, and reports.
- [Agent methods and running guide](docs/Agents/Running.md)
- [Planner/executor running guide](docs/Planner%20and%20Executor/Running.md)
- [P2 behavior and implementation plan](docs/Planner%20and%20Executor/P2.md)
- [CSV evaluation guide](docs/evaluation/Running.md)
- [Research controls](docs/experiment_protocol.md)
- [Progress](docs/progress.md) and [current limits](docs/limitations.md)
- [Original reference guide](docs/reference/Execution_Engine_Research_App_Build_Guide.md)

No employer source or proprietary data belongs in this independent project.
