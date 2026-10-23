# Running the planner and DAG executor

Updated: 2026-10-23.

## What is available

The new data-analysis path has separate planner, executor, connection, tool-call, file, and storage modules under `src/mcp_execution_lab/orchestration/`.

The planner discovers configured MCP tools and saves their exact definitions. It creates a Main Task, draft tool selection, assigned subtasks, and a checked DAG. The LLM chooses tools and dependencies; the system prompt names no agents and supplies no preferred tool order. A goal can use a small subset of tools, or no worker calls when no worker action is needed.

The executor starts ready work within the concurrency limit, calls the exact server/tool named by each step, and saves outcomes before starting dependent work. It supports conditions, explicit alternatives, recorded failures, bounded retries, confirmed-result reuse, and D2 revisions with references to completed outputs.

The six LLM data-analysis workers are implemented. See [the agent guide](../Agents/Running.md) for their methods, limits, API, and one-command start/stop scripts. The example MCP server remains a deterministic test fixture. CSV runs support D1/D2 only. The older pricing code and Python runner have been removed; previous run evidence is retained.

## Local PostgreSQL and files

1. Copy `.env.example` in the project root to `.env`.
2. Set `MCP_LAB_DATABASE_URL` to your local PostgreSQL connection, using a database where this project may create tables. Keep the password in `.env`.
3. Set `MCP_LAB_DATA_ROOT` if you want a different file directory. Its default is `runs/data_analysis`.
4. Initialize the project tables:

```powershell
.\scripts\lab.ps1 analysis db-init
```

The application connects to PostgreSQL installed on Windows. It does not start a Docker database, modify PostgreSQL authentication, or create a database account. It does not fall back to SQLite when a production connection fails. Tests have an explicit SQLite seam as well as native PostgreSQL integration checks.

These project tables are created in the configured database:

| Table | Contents |
|---|---|
| `lab_schema_versions` | The supported database layout version |
| `lab_runs` | Each question, mode, settings, source/lock hashes, and run status |
| `lab_records` | Typed records for datasets, tool caches, tasks, selections, plans, calls, attempts, outputs, and results |
| `lab_record_links` | Connections between records, checked to belong to the same run |
| `lab_events` | Ordered progress, errors, and state changes within each run |
| `lab_plan_steps` | Each planned step and its execution state, within a specific plan version |

Records are saved throughout planning and execution. Requests are saved before model/tool dispatch. Accepted outputs are saved before dependent work starts. Related state changes and events share short database transactions. A database failure prevents new unrecorded work from starting.

CSV contents, JSON results, charts, and Markdown reports stay on disk. Database records contain their owned locations, content fingerprints, producer, and input versions. Worker calls, stages, model requests/replies, and file writes use typed records linked to the same run. Back up both PostgreSQL and the file directory. Original uploaded files are copied, not overwritten. Existing SQLite pilot evidence is retained; it is not automatically imported into the new tables.

## Configure the tools and model

Use `configs/agents_stdio.yaml` for CLI-owned agent processes, or `configs/agents.yaml` with `start_agents.ps1` for persistent local services. The commands below retain `configs/data_analysis.example.yaml` to demonstrate the original deterministic calculation fixture; substitute the chosen agent config for real agent work.

- `servers` defines project-owned server IDs and either stdio commands/arguments or loopback streamable-HTTP URLs. `{python}` resolves to the project Python executable. Only explicitly allowed environment names and basic OS variables pass to child processes.
- Each server may expose multiple tools. Different servers may expose tools with the same name; the server ID keeps them distinct.
- `model` configures the existing Codex login route or a trusted local command router.
- `limits` controls simultaneous work, calls, attempts, time, input size, and observed token usage.
- `task_rules` defines the two fixed review rules used for matching D1/D2 tasks.

The example server, `tests/mcp_analysis_server.py`, reads registered synthetic CSVs and returns deterministic results. It is not an LLM agent or a measured worker benchmark. Its simple tool descriptions are copied into the discovery cache with the raw definitions; the application does not invent missing capabilities.

Model responses use the existing non-interactive Codex connection with a structured outer response and a checked JSON record inside it. Authentication remains with Codex. Worker requests have their own instructions rather than the main planner's instructions. Subscription calls consume account allowance; no per-call dollar price is assumed. Unknown usage stays unknown. See the retained [bridge guide](../planner_bridge.md) for the adapter contract.

## Plan, inspect, and execute separately

Create a plan:

```powershell
.\scripts\lab.ps1 analysis plan --query "Calculate the total amount from the CSV using an available tool" --csv fixtures/data_analysis/example.csv --config configs/data_analysis.example.yaml --mode D1
```

The sample CSV contains six synthetic rows with amounts totaling 210. Its purpose is development verification. The planner receives a bounded preview and file description. The test calculation tool reads the full registered file.

Supply more than one CSV by repeating `--csv`. Use `--encoding` and `--delimiter` when necessary. Ambiguous headers, inconsistent row widths, invalid encoding, and file-size violations are recorded as planning errors instead of silently dropping data.

The response contains `run_id`, `plan_id`, and the accepted handoff. Planning alone does not execute any selected worker tool.

Inspect the saved records:

```powershell
.\scripts\lab.ps1 analysis inspect --run RUN_ID
```

Execute that accepted plan:

```powershell
.\scripts\lab.ps1 analysis execute --run RUN_ID --config configs/data_analysis.example.yaml
```

The executor checks that the run is ready and that its settings, source, dependency lock, and tool definitions have not changed. It restores the allowance already spent on planning. A completed or interrupted run cannot be silently started again.

To plan and execute in one command:

```powershell
.\scripts\lab.ps1 analysis run --query "Calculate the total amount from the CSV using an available tool" --csv fixtures/data_analysis/example.csv --config configs/data_analysis.example.yaml --mode D1
```

The installed `mcp-analysis` command exposes the same actions.

## D1 and D2 review rules

D1 follows its original plan, including written conditions. At a review boundary it records passage without asking the main model again.

D2 can ask the main model to keep, revise, or stop the remaining work. A revision is validated and saved as a new plan version. Prior outputs remain linked to their original producing attempts.

The current task rule is a configured finished-step count, independent of agent names. It counts successful and known-failed attempted steps. Blocked or skipped steps do not create extra tool calls. The example configuration places reviews after the first and second finished steps; choose and freeze task rules before any measured comparison.

At a reached threshold, the scheduler stops starting work and settles already running calls. The recorded count can therefore exceed the threshold. The second review may be reached at the same settled boundary. A short or failed plan can leave a review unreached; that is recorded rather than forcing unnecessary agents to run.

An uncertain action must be handled before revising around its effects. Planning, correction, review, and worker model calls all consume the same recorded run allowance. Token limits are observed after a reply, not reserved as a guaranteed generation cap.

For a planned backup after a known failure, use `dependency_policy: settled`, a condition reading the earlier step's `status`, and an explicit final output choice. The default dependency policy still requires success. Unknown or cancelled work does not become safe to bypass. Failed attempts remain saved even when the backup finishes the required work. List/object bindings can assemble several checked references; definite mismatches between published output and input types are rejected before execution.

## Current boundaries

- Execution completion means the plan's required work finished. That execution record keeps `task_success` unknown and `evaluation_status` as `NOT_EVALUATED`. The separate [evaluation mechanism](../evaluation/Running.md) grades the exact published development tasks and saves run-linked evaluation records.
- Worker outputs use structured JSON with registered file references. A non-completed worker outcome fails that step; receiving an MCP reply alone does not mean the job succeeded.
- The executor cannot run worker-generated analysis code. The old container runner has been removed. Future generated-code execution requires an isolated design; never run it in the host process.
- The connection manager uses the official SDK for stdio and local streamable HTTP. Remote hosting is outside this version.
- Worker AI calls share the run's live allowance and are saved with their worker/attempt links. The worker support service only grants access to supplied files and checked output publication.
- Automatic restart of running or uncertain actions is not implemented. A confirmed saved result can be reused within the run; an unknown outcome is not silently replayed.
- A low-level tool's declared read-only/idempotent behavior permits bounded transport retries. This does not promise that an interrupted external model call is charged only once.
- There is no dashboard. Use the CSV commands or local API for planning, execution, and inspection.

## Validation

Run the normal project checks:

```powershell
.\scripts\check.ps1
```

The tests include real MCP servers, planner-stage persistence, neutral prompts, tool-selection refinement, invalid graphs, conditional alternatives, parallel readiness, changed file/tool definitions, cross-run references, retries, uncertainty, cancellation, concurrent start protection, and D2 replacement plans.

To test native PostgreSQL, with the installed PostgreSQL binaries available:

```powershell
$env:MCP_LAB_POSTGRES_TEST = '1'
.\scripts\check.ps1
```

This starts and stops a separate temporary, password-protected PostgreSQL cluster on a free local port. It does not need or alter the existing PostgreSQL service's login. Windows restricted shells may prevent `initdb` from starting; use a normal user terminal for this integration check.

Docker and its old integration checks have been removed. A live Codex smoke is separately opt-in with `MCP_LAB_CODEX_TEST=1` together with `MCP_LAB_POSTGRES_TEST=1`; it uses the model in `configs/agents_stdio.yaml`, consumes subscription allowance, and caps planning at eight calls. Live smoke attempts keep their files under `runs/data_analysis_smoke/` and audit exports under `reports/orchestration_validation/`, including failed attempts.
