# Running the six data-analysis agents

Updated: 2026-10-23. Live worker-model quality is not yet tested.

## What is built

Each agent runs as a separate MCP server with one public tool. The main planner chooses
which tools are needed and how their work connects. Starting six servers does not mean
calling six tools. No preferred agent order is written into the main system prompt.

| Agent | Public tool | Supported first version |
|---|---|---|
| Understanding | `understand_data` | Row/column checks, missing values, observed types, duplicates, numeric ranges, and key checks. |
| Cleaning | `clean_data` | Explicit trim, replacement, fill, date/number conversion, duplicate removal, and missing-row rules; saves a new copy and a change log. |
| Combining | `combine_data` | Append matching column sets, or join two to eight files using the same explicit keys, join type, and relationship rule at each stage, with bounded row growth. |
| Analysis | `analyze_data` | One CSV: filters, count/sum/mean/min/max, groups, time groups, a before/after comparison, correlation, and PNG bar/line charts. |
| Prediction | `predict_data` | Linear numeric prediction, nearest-centroid label prediction, or last-value time forecasting, with held-back checks and a simple reference method. |
| Report | `create_report` | Markdown from saved JSON facts and PNG charts, with a saved map from claims to source facts. |

The agents use LLM calls to choose a supported approach and explain measured facts.
Handwritten functions perform the calculations. Arbitrary generated code, SQL, and shell
commands are not executed. A worker cannot call another agent or change the main plan.
Unsupported work returns a clear outcome instead of pretending to finish.

## Set up PostgreSQL and the model route

From `C:\Learning\R-Project`:

1. Copy `.env.example` to `.env` if you have not already created it.
2. Enter `MCP_LAB_DATABASE_URL` for a native local PostgreSQL database where this project
   may create its `lab_*` tables. Keep the password in that file.
3. Initialize the tables:

```powershell
.\scripts\lab.ps1 analysis db-init
```

The scripts use the project `.venv`. On a fresh setup, install Python 3.12 and sync the
locked dependencies with `uv sync --locked --python 3.12`.

`configs/agents.yaml` uses the existing Codex command route. Keep the exact model and
reasoning setting appropriate for your local installation. Worker processes receive
neither database credentials nor model login files; they request model work from the
executor's support service. The existing command-router option also remains available.

No live model calls were made while building these agents. Starting services, checking
health, and listing tools consume no model calls. Planning and executing a submitted
question use the configured model route and its account allowance. Unknown dollar cost
is not recorded as zero.

## Start and stop all seven processes

```powershell
.\start_agents.ps1
```

The script starts hidden background processes, waits for readiness, and prints the ports
and PIDs. Default addresses:

| Service | Address |
|---|---|
| Orchestrator API | `http://127.0.0.1:8766` |
| Understanding MCP | `http://127.0.0.1:8767/mcp` |
| Cleaning MCP | `http://127.0.0.1:8768/mcp` |
| Combining MCP | `http://127.0.0.1:8769/mcp` |
| Analysis MCP | `http://127.0.0.1:8770/mcp` |
| Prediction MCP | `http://127.0.0.1:8771/mcp` |
| Report MCP | `http://127.0.0.1:8772/mcp` |

Each service also has `/health`. The orchestrator root returns health JSON, not a web
dashboard. `READY` confirms service readiness. Its database field means a connection
setting is present, not that the database has accepted a connection.

If ports are in use or reserved by Windows, choose another seven-port range:

```powershell
.\start_agents.ps1 -BasePort 18000
```

The managed orchestrator adjusts its six known worker URLs to that range. If using the
HTTP configuration directly from the CLI, update its URLs to match your selected ports.
Running start again checks the existing services and keeps their PIDs. Stop first before
changing the configuration, port range, or code.

```powershell
.\stop_agents.ps1
```

Stop checks the project executable, saved creation time, and available command details
before stopping any saved PID. It requests graceful shutdown, then uses PID/tree termination
for an owned process that remains alive. A reused PID does not authorize killing an
unrelated process. Stopping during a run may leave interrupted or uncertain work; use it
after active work finishes when possible. Such work is not automatically replayed.

Saved process information:

- `.runtime/agents/pids.json`: latest process state.
- `.runtime/agents/launch_<ID>/`: launch snapshots and per-service output/error logs.
- `.runtime/agents/access.token`: local API/shutdown access token; do not share it.

Logs and run evidence are retained when stopping. `.runtime/` is excluded from source
control. This is a trusted local-user service, not a hosted multi-user application.

## Use the orchestrator API

After starting the services, read the token into a header without printing it:

```powershell
$base = 'http://127.0.0.1:8766'
$headers = @{ Authorization = 'Bearer ' + (Get-Content .runtime/agents/access.token -Raw).Trim() }
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/tools" -Headers $headers
```

Create a saved plan first:

```powershell
$body = @{
    query = 'Calculate total amount and explain the result in simple English.'
    csv_paths = @('fixtures/data_analysis/example.csv')
    mode = 'D1'
    plan_only = $true
} | ConvertTo-Json
$planned = Invoke-RestMethod "$base/runs" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 1800
$planned.run_id
```

Relative CSV paths resolve from the project directory. Use absolute local paths for
other files. Up to eight registered CSVs may be supplied. These are local file paths,
not multipart browser uploads.

Inspect and execute the same accepted plan:

```powershell
$runId = $planned.run_id
Invoke-RestMethod "$base/runs/$runId" -Headers $headers
$result = Invoke-RestMethod "$base/runs/$runId/execute" -Method Post -Headers $headers -TimeoutSec 1800
$result
Invoke-RestMethod "$base/runs" -Headers $headers
```

Set `plan_only = $false` to plan and execute in one POST. POST requests wait for their
work to finish; this version is not a background job queue. Use another terminal to read
`/runs/<run_id>` during execution. Records are written throughout the run. `/runs` lists
the latest fifty runs. Routes other than health require the local access token.

## Use the CLI instead

For owned stdio agents, no persistent services need to be started:

```powershell
.\scripts\lab.ps1 analysis plan --query "Calculate total amount" --csv fixtures/data_analysis/example.csv --config configs/agents_stdio.yaml --mode D1
.\scripts\lab.ps1 analysis inspect --run RUN_ID
.\scripts\lab.ps1 analysis execute --run RUN_ID --config configs/agents_stdio.yaml
```

`analysis run` combines plan and execute. Repeat `--csv` for multiple files. For already
running HTTP agents, use `configs/agents.yaml` instead. Planning and execution must use
the same configuration, source version, dependency lock, and published tool definitions.
An older running worker is rejected after a code change; restart services and create a
new run. A completed or interrupted run is not silently restarted.

## Files, records, and limits

The record chain is:

```text
run -> plan version -> step -> tool attempt -> worker call
    -> worker stages -> worker model calls -> checked results -> registered files
```

PostgreSQL stores these records and links while work happens. Files stay under
`MCP_LAB_DATA_ROOT` (default `runs/data_analysis`). Original files are copied and remain
unchanged. New CSVs, JSON findings, PNG charts, and Markdown reports receive new file
references with hashes and input links. Later calls must use owned, unchanged references.
Back up both the file directory and database.

The executor starts a small local support service for each active run. Each worker call
gets its own temporary access in trusted MCP metadata, limited to its supplied files and
attempt. It cannot use another run's files. Access closes when the call finishes or the
run closes. This service is distinct from the persistent orchestrator API.

Current managed configuration:

| Limit | Value |
|---|---|
| Simultaneous tool calls per run | 2 |
| Total model requests, including planning/reviews/workers | 32 |
| Model requests per worker call, including corrections | 3 |
| Observed input + output tokens per run | 120,000 |
| Run / tool time | 1,800 / 300 seconds |
| Worker CSV bytes / rows | 16 MiB / 100,000 |

Token limits are checked after a response, not guaranteed generation limits. Unknown
usage stays unknown. Larger initially registered files can still be refused by a worker.
Cleaning and Combining also bound change records and output rows; Analysis limits groups
and chart points. Exact typed tool definitions are the source of truth for argument rules.

D1 still uses LLMs inside selected workers; it does not replan the main workflow during
execution. D2/P2 add the two configured task reviews after the first and second finished
attempted steps. Short plans may leave a review unreached. This rule does not force two
agents, any named agent, or unnecessary work. Freeze task rules and equal allowances
before comparing treatments.

A result marked `COMPLETED` means execution finished its required work. Its execution
record leaves `task_success` unknown (`NOT_EVALUATED`). The separate
[evaluation commands](../evaluation/Running.md) can grade the published development
tasks and save a run-linked result. See [remaining limits](../limitations.md)
for prediction limits, Python continuation limits, and research boundaries.

## Validation

After the CSV-only cleanup on 2026-10-23, the full check passed **131 tests, 1 skipped**
with native PostgreSQL and real MCP enabled. Docker is not required. See the
[current validation](../../reports/csv_cleanup_2026-10-23/README.md).

```powershell
.\scripts\check.ps1
# Optional native PostgreSQL checks:
$env:MCP_LAB_POSTGRES_TEST = '1'
.\scripts\check.ps1
```

Native PostgreSQL tests create a separate temporary password-protected cluster; they
do not change the user's installed service. PostgreSQL binaries must be on PATH. Windows
may require a normal user terminal for `initdb`.

The full check on 2026-10-21 passed **142 tests, 1 skipped**. A later API test passed
separately with native PostgreSQL and a real MCP worker. It checked planning, execution,
reading the same run, token rejection, request size, and refusal to execute a completed
run again. The full-suite skip was the explicit live Codex smoke. All worker model
responses in this validation were fixed fixtures. See [saved evidence](../../reports/agents_validation/README.md).
