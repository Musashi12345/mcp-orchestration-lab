# MCP Execution Lab

The data-analysis planner and DAG executor now live in
`src/mcp_execution_lab/orchestration/`. They accept a question and CSV files, discover
configured MCP tools, create an LLM-chosen plan, and execute only its required steps.
The system prompt contains no preferred agent or fixed tool sequence. Plans and live
execution records use local PostgreSQL; registered CSVs and generated files stay on disk.

The six LLM data-analysis agents are implemented as separate MCP servers: Understanding,
Cleaning, Combining, Analysis, Prediction, and Report. Each has its own checked operations
and tests. The planner selects only the tools needed for the question.

Start with [the agent running guide](docs/Agents/Running.md),
[planner/executor instructions](docs/Planner%20and%20Executor/Running.md),
[planner design](docs/Planner%20and%20Executor/Planner.md), and
[executor design](docs/Planner%20and%20Executor/Executor.md).
Copy `.env.example` to `.env` and enter your local database connection before running:

```powershell
.\scripts\lab.ps1 analysis db-init
.\start_agents.ps1
# Stop the orchestrator and all six managed agent processes:
.\stop_agents.ps1
```

Start-up and tool discovery consume no model calls. Submitting a run uses the configured
Codex or command route. The start script prints ports and PIDs, saves logs under `.runtime/agents/`,
and waits for all seven services to answer. The stop script checks process identity before
stopping saved PIDs; it retains logs. The orchestrator exposes a local API, not a new dashboard.

For a CLI-only run, `configs/agents_stdio.yaml` starts owned MCP child processes automatically:

```powershell
.\scripts\lab.ps1 analysis run --query "Calculate total amount" --csv fixtures/data_analysis/example.csv --config configs/agents_stdio.yaml --mode D1
```

Workers use LLM calls to choose a supported approach and explain checked results. Their
calculations use handwritten functions. Main and worker model calls share one run allowance,
and requests, replies, progress, and file versions are saved during the run.

See [agent modules and plans](docs/Agents/README.md) for supported methods and limits.
Validation on 2026-10-21 passed **142 tests, with 1 skipped**, including native PostgreSQL,
real MCP, process scripts, and Docker checks. A separate native PostgreSQL API check passed.
Worker model replies in these checks were fixed test data; live worker-model behavior has
not been tested. Saved results are under [agent validation](reports/agents_validation/README.md).

There is also a first [evaluation mechanism](docs/evaluation/Running.md), with ten synthetic
CSVs, fifteen public development tasks, independent answer checks, native PostgreSQL grades,
human review, and paired D1/D2 reports. List the questions without model calls:

```powershell
.\scripts\lab.ps1 eval list
```

This data-analysis path currently supports D1/D2. Data-analysis P1/P2, a broader unseen
evaluation collection, and a new dashboard remain future work. The original four-mode pricing pilot is
retained below for regression checks and its saved evidence.

## Existing pricing pilot

A local research application for **DAG Plans or Generated Programs? A Controlled Study of
Adaptive MCP Orchestration**. This project is separate from MS admissions work.

The working pilot implements all four modes through one broker and the same genuine MCP
workers. DAGs run in a validated scheduler; generated Python runs exclusively inside a
restricted Linux Docker container. Codex supplies structured initial plans and checkpoint
replans through your existing ChatGPT CLI login. The app owns execution and independent grading.

| Mode | Representation | Execution checkpoint model calls |
|---|---|---|
| D1 | DAG | None |
| D2 | DAG | After inspection and after initial checks |
| P1 | Python | None |
| P2 | Python | The same two checkpoints |

Handwritten and deterministic stub runs are explicitly exploratory and have no research
treatment label. Real model runs are development feasibility episodes, not a held-out study.
See [progress](docs/progress.md) and [limitations](docs/limitations.md).

## Start locally

From `C:\Learning\R-Project` in your normal PowerShell terminal, with Docker Desktop running:

```powershell
.\scripts\lab.ps1 doctor
.\scripts\lab.ps1 runner-build
.\scripts\lab.ps1 serve --config configs/smoke.yaml
```

Open **http://127.0.0.1:8765**. Select a task, mode and fault condition; queue an episode.
The dashboard displays persisted jobs, outcomes, checkpoint decisions, all plan versions,
DAG dependencies and actual Python dispatch traces. Its default configuration uses stubs.
Stop the foreground server with Ctrl+C. It binds only to loopback.

## Use your ChatGPT login for planning

```powershell
codex login status
# If needed: codex login
.\scripts\lab.ps1 models
.\scripts\lab.ps1 run --mode D1 --task repair_01 --config configs/codex.yaml
.\scripts\lab.ps1 run --mode P2 --task repair_03 --config configs/codex.yaml
.\scripts\lab.ps1 serve --config configs/codex.yaml
```

`configs/codex.yaml` selects the locally discovered `gpt-6.1-sol` model and low reasoning.
Every request starts an ephemeral non-interactive Codex invocation. The planner receives
public contracts and observations, returns structured JSON, and is forbidden from doing
its own tool execution. The adapter rejects actual Codex tool activity and retains CLI logs.
Authentication stays with Codex; the app never reads login credentials or needs an API key.

These calls consume your subscription quota. Dollar cost is **unknown**, not reported as
zero. Explicit ceilings limit calls per episode and batch/dashboard session. The token cap
is observed after each CLI response; `response_token_hint` is advisory. It cannot guarantee
a hard generation token limit. Details and a custom-router contract are in
[the planner bridge guide](docs/planner_bridge.md).

## Compare, analyze and export

```powershell
.\scripts\lab.ps1 compare --task repair_01 --config configs/smoke.yaml
.\scripts\lab.ps1 batch --config configs/smoke.yaml
.\scripts\lab.ps1 analyze --batch BATCH_ID
.\scripts\lab.ps1 export --batch BATCH_ID --output reports/my-batch
.\scripts\lab.ps1 inspect --run RUN_ID
.\scripts\lab.ps1 export --run RUN_ID --output reports/my-run
```

The smoke batch schedules 16 fresh episodes; `configs/offline.yaml` schedules 96 stub
episodes across six fixtures, two conditions and two repeats. Both make no model calls.
A Codex batch requires a sufficient explicit `max_model_calls` ceiling. Episodes run one
at a time, with randomized mode order inside paired task/condition/repeat blocks. A batch
stops if its source changes. Failed episodes remain in the evidence and analysis.

Each batch produces episode/model-call CSV files, descriptive factorial contrasts,
exploratory task-cluster bootstrap intervals, a Markdown report and PNG/SVG plots.
Unreported token usage stays null. Reports never promote stub outcomes to model findings.

`run` returns JSON and a nonzero exit code for a failed episode. Expected naive fixed-plan
failures on challenge fixtures are retained too. `--transport local` is a recorded unit-test
seam; normal runs use MCP. `--plan file.json` and `--program file.py` accept handwritten
sources, with matching `--mode`; Python still requires Docker. Examples of fixed recovery
are generated by `fallback_plan()` and `reference_program(fallback=True)`.

Evidence stays in `runs/<run_id>/` and `batches/<batch_id>/`. Exports require a new directory,
include all source versions and call logs, redact common credentials and private grading
case diagnostics, and include file hashes. Hidden evaluator fixture files and databases
are not exported. Review selected exports before publication; redaction is conservative.

## Validation and setup

```powershell
.\scripts\check.ps1
# Also run the real Docker tests:
$env:MCP_LAB_DOCKER = '1'
.\scripts\check.ps1
```

The scripts use `.venv\Scripts\python.exe`, so Python need not be on PATH. For a new machine,
install Python 3.12 and uv, then run `uv sync --locked --python 3.12`. Install Docker Desktop
with Linux containers and the Codex CLI separately. No global Python was changed here.
The project lockfile pins resolved dependencies; the runner base image is pinned by digest.

## Context

- [Experiment protocol](docs/experiment_protocol.md)
- [Implementation progress](docs/progress.md)
- [Boundaries and research work remaining](docs/limitations.md)
- [Codex and external-router integration](docs/planner_bridge.md)
- [Original build guide](docs/reference/Execution_Engine_Research_App_Build_Guide.md)
- `src/mcp_execution_lab/`: controller, planners, shared runtime, executors, workers and reports.
- `tests/`: grading, runtime budgets, receipts, adaptation, bridge, Docker and export checks.

The deeper architecture discussion can follow this working pilot. General code-repair
transfer, LLM workers and a statistically meaningful held-out evaluation remain research
extensions; six related policy simulations do not establish a representation winner.
