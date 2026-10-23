# Data-analysis agents: implementation and shared design

Date: 2026-10-21. Status: first version implemented and checked with fixed model replies
through real MCP. See [Running.md](Running.md) for commands, actual supported methods,
arguments, and limits. Live worker-model quality has not been tested.

This folder contains a separate build plan for each of the six agreed agents. This
document defines the rules they share, so six servers do not become six different ways
of saving records, spending model calls, or handling files.

In these plans, an input/output schema means the rules for fields and their allowed
values. A reference points to a saved file; a hash detects whether that file changed.
An artifact is a saved output file. A receipt is the saved completion record used to
avoid repeating work that already finished.

## 1. The six MCP servers

Each agent runs as its own local Python MCP server. Each initially exposes one
main tool. Its private helper functions are not extra tools for the main planner to call.
More public tools can be added later when they have a clear purpose and tested rules.

| Plan | Server ID | First public tool | Purpose |
|---|---|---|---|
| [Data Understanding](Data_Understanding_Agent.md) | `data_understanding` | `understand_data` | Explain files and check their contents. |
| [Data Cleaning](Data_Cleaning_Agent.md) | `data_cleaning` | `clean_data` | Produce a checked, cleaned copy. |
| [Data Combining](Data_Combining_Agent.md) | `data_combining` | `combine_data` | Join files or append their rows. |
| [Data Analysis](Data_Analysis_Agent.md) | `data_analysis` | `analyze_data` | Calculate findings and make useful charts. |
| [Prediction](Prediction_Agent.md) | `prediction` | `predict_data` | Build and check a suitable prediction. |
| [Report](Report_Agent.md) | `report` | `create_report` | Write an answer from saved evidence. |

These are available choices. There is no required agent sequence. The planner chooses
tools and dependencies from the question, file descriptions, and discovered capabilities.
Understanding is optional when the supplied facts are enough. Cleaning, combining,
prediction, and reporting are also optional. One agent can be called several times for
different jobs. A direct agent result can be the final answer without a Report call.

## 2. How an agent becomes an MCP server

Use the official MCP SDK already locked in this repository. Follow the locally tested
`MCPServer`, `@server.tool(...)`, and `server.run(transport="stdio")` pattern in
`tests/mcp_analysis_server.py`. The framework adapter remains
`src/mcp_execution_lab/orchestration/mcp.py`.

Each server must:

1. Start as a separate process using the project `.venv` Python.
2. Complete MCP initialization and publish its server name and version.
3. Publish a clear tool description and complete typed input/output definitions.
4. Answer tool discovery without making an LLM call or reading a dataset.
5. Accept a tool request, carry out only its assigned job, and return structured JSON.
6. Write diagnostic logs to stderr; stdout belongs to the MCP connection.
7. Handle cancellation and close its running work when the parent connection ends.

Both stdio and local streamable HTTP are implemented through the official SDK adapter.
With stdio, the executor starts the process and exchanges MCP messages through it.
The root start/stop scripts use HTTP to manage seven persistent loopback processes.
The executor may reuse a server connection for several calls. Request-specific state must
not leak between those calls or between runs.

Implemented modules:

```text
src/mcp_execution_lab/agents/
  common/                 # Input/output records, file access, bounded job loop
  understanding/          # server.py, worker.py, operations.py, models.py
  cleaning/               # Same separation, with cleaning-specific code
  combining/
  analysis/
  prediction/
  report/
```

For example, the working stdio configuration entry for Understanding is:

```yaml
servers:
  - id: data_understanding
    command: "{python}"
    args: ["-m", "mcp_execution_lab.agents.understanding.server"]
```

The other plans name their own modules. Server-list order carries no preference.
`configs/agents_stdio.yaml` lists all six for discovery; worker tool calls occur only when
selected by an accepted plan. `configs/agents.yaml` connects to persistent local HTTP services.

Tool descriptions explain what the tool can do, required inputs, limits, and outputs.
They must not say "call me first", "always call agent X next", or claim an unsupported
ability. Save versioned definitions in the existing per-run tool cache.

## 3. Shared request and result rules

Every public tool must have a required `job` string. This is the actual subtask given to
the agent, not merely text stored in the database. Validate it against the saved subtask
before dispatch. Reject a mismatch rather than silently changing the accepted plan.

Other public arguments are typed file references and task options, as listed in the
individual plans. Use the existing reference shape: `id`, `run_id`, `kind`, and `sha256`.
Accept registered references rather than arbitrary disk paths, SQL, Python, or URLs.
File ownership, file kind, and the content hash must be checked before reading.

Trusted request metadata will supply the run ID, plan ID, step ID, attempt ID, worker-call
ID, and stable operation ID. Extend the adapter's existing `lab_operation_id` metadata.
These values come from the broker, not from LLM-written job text. The server checks them
with the shared run service before beginning work.

Each tool publishes its own complete result schema with these common fields:

| Field | Meaning |
|---|---|
| `contract_version` | Version of the tool's input/output rules. |
| `outcome` | `COMPLETED`, `NEEDS_INPUT`, `UNSUPPORTED`, or `FAILED`. |
| `summary` | A short explanation of what happened. |
| `datasets` | Registered CSV references created by this call; can be empty. |
| `artifacts` | Registered findings, chart, report, or other supported file references. |
| `facts` | Checked facts with IDs, values, units, and links to their source/calculation. |
| `details` | A typed, agent-specific result, described in that agent's plan. |
| `warnings` and `questions` | Limits and information needed from the user. |
| `error` | A public error code and short explanation when applicable. |
| `usage_record_ids` | Links to actual saved worker model calls; usage is owned by the runtime. |

An MCP reply arriving successfully does not mean the requested job succeeded. The
executor handles non-completed outcomes before marking a step successful or
starting work that needs its outputs. Known errors, a request for information, and an
unknown transport outcome remain different cases. A worker cannot award research success.

## 4. One shared run service

The executor creates a small local service for worker support during each active run.
This is an internal support component, not another agent or a planner-selectable tool.
It owns access to the existing local PostgreSQL records, model route, and file registry.

The executor calls an MCP agent; that agent asks the support service to save progress,
request a bounded model call, or register an output. The service uses the existing model
connection through a general worker-call adapter. Worker instructions are separate from
the current planner prompt, which explicitly forbids doing analysis.

The service uses authenticated loopback connections. The broker creates short-lived,
call-scoped access and passes it through trusted MCP metadata. This replaces the original
proposal to use a shared worker environment token and also supports persistent processes.
Do not put the token in prompts, saved settings, reports, or raw request logs. Check the
active run/attempt on every request; reject cross-run access and cancelled/closed work.
Servers do not need a PostgreSQL password or model login files of their own.

The first version exposes only narrow operations: claim a worker call, read an allowed
reference, save a stage, request a model reply, publish a staged file, finish a worker
call, and return an existing receipt when the same context is claimed. It does not expose arbitrary file access,
SQL execution, shell commands, or a general tool-execution proxy.

Why share this service: six process-local counters cannot enforce one run allowance.
A database run claim permits one active executor. Its central allowance object reserves
requests before dispatch, without yielding between checking and reserving. Worker claim
state prevents duplicate active delivery, and saved records retain attempts and receipts.
Parallel worker tests check that two workers cannot spend the same remaining request slot.
This is not a distributed allowance service or automatic host-crash recovery.

## 5. Save records while work happens

Retain this chain with database-enforced ownership:

```text
Run -> plan version -> step -> tool attempt -> worker call
    -> worker stages -> worker model calls -> calculations -> registered outputs
```

Before any model request, reserve its allowance and save its request and `RUNNING` record.
Save its actual reply, known usage, errors, and timing before continuing. Save the proposed
recipe, checks, calculation settings, and file publication as separate stages. Save a
worker receipt before returning its final result to MCP. The broker then saves its own
accepted result before starting dependent work.

Reuse `lab_records`, `lab_record_links`, and `lab_events` where appropriate; add typed
worker record kinds and migrations/constraints where needed. Avoid six separate storage
implementations. A missing database write stops new work. Keep uncertain work and partial
evidence instead of assuming a cancelled or disconnected model request was never charged.

Files remain on disk. Publish each output as a new owned version with its type, hash,
size, producer, and exact input versions in PostgreSQL. Register produced CSVs as datasets
that later agents can use. Extend the current CSV/JSON-only file helpers for charts,
Markdown, and other explicitly supported types. An unfinished staged file is not a valid
output; record its interrupted state and retain evidence without returning a usable ref.

## 6. How each agent uses its LLM

The shared job loop is:

1. Validate the request and build bounded facts/previews from the allowed files.
2. Ask the LLM for a structured approach within that agent's published abilities.
3. Save and check the proposed approach: columns, operations, limits, and expected outputs.
4. Run checked, handwritten operations to calculate or transform the data.
5. Save results and let the LLM explain the checked facts when that adds value.
6. Check the reply against the facts and publish the final result.

The implemented default is at most three model requests per worker call, including
corrections. Most agents use one recipe request and one explanation request; Report can
use a single draft request. Limits should be frozen before measured runs. No unbounded "keep trying"
loop, self-created agent, call to another MCP role, or change to the main DAG is allowed.

The LLM chooses from supported operations; the first build does not execute LLM-written
Python, shell text, expressions, or generated SQL. Use checked functions with typed
options. If generated analysis code is added later, it must run in the restricted
container, never in the host or MCP server process.

Counts, totals, metrics, and chart values come from calculations, not LLM guesses. Treat
CSV cells, filenames, and earlier prose as data, not instructions. Use bounded previews
and only the columns needed for the assigned job. Record omitted/truncated context.

## 7. Allowances, retries, and the comparison

All main-planner, correction, review, and worker model calls count toward the run's
shared allowance. Also save role-specific totals. Enforce per-worker time, call, input,
output, and computation limits. A token cap checked after a reply cannot guarantee a hard
generation limit. Unknown usage and unknown subscription dollar cost remain unknown.

The agent configurations allow 32 total requests and three per worker call. For
example, six selected agents using two calls each would consume twelve worker calls,
before initial planning, reviews, or corrections. This example is not a reason to select
all six agents. Define sufficient equal allowances per matched task.

Initially publish conservative MCP retry hints: `read_only_hint=False` and
`idempotent_hint=False` for model-backed tools. They can create files, records, and paid
or quota-consuming model calls. `open_world_hint=False` describes their limited access;
the hints do not replace runtime checks.

Pass the stable operation ID through retries. Return a known saved receipt without new
model calls when its job, inputs, settings, and occurrence match. An incomplete or unknown
model request is not automatically repeated. Only advertise retry safety after tests prove
the complete claim/receipt behavior, including crashes between model reply and save.

D1/P1 may still use LLMs inside workers. Their restriction is no main-orchestrator
replanning during execution. D2/P2 add only their shared task-defined main reviews.
Worker calls do not create extra review points. All four treatments must eventually use
the same worker versions, prompts, access, limits, and runtime. No cross-run response reuse
or private evaluator answers may be exposed to a worker, planner, or generated runner.

## 8. Runtime changes included

The implementation includes:

- Fixes for the five findings in the [2026-10-19 audit](../../reports/orchestration_audit_2026-10-19/README.md):
  known-failure backups, D2 public error details, linked-input type checks, readiness after
  skips, and final summaries on early stops.
- Shared worker records, central call reservations, operation claims, cancellation,
  and the narrow run service described above.
- Trusted call metadata and the actual assigned `job` delivered to every agent.
- Typed results and handling of non-completed worker outcomes.
- Registered output CSVs, charts, and reports with checked versions and links to their sources.
- General list/object input bindings so several resolved references can become one typed
  tool argument, with recursive validation and checks for definite linked type mismatches.
  Matching new Python support remains future work.
- Model routing separate from the worker's reasoning prompt. Freeze model, recipe,
  prompt, tool, library, source, and configuration versions for comparison runs.

These are general runtime abilities. They must not introduce a preferred agent order.

## 9. Build and test plan

Shared records and the run service were built first. Each server was then implemented
and checked independently using its own plan. A convenient developer build order is not a runtime
workflow and must not appear as one in the main planner prompt.

The following test goals guided implementation. The current checks cover normal execution,
refusals, live records, budget races, cancellation, real MCP, and PID safety. Broad database
failure/process-crash testing and live model quality remain extensions, not proven guarantees.

- Discovery lists every server/tool/schema without executing work or making model calls.
- One selected server runs without needing the other five; one process handles repeated calls safely.
- The actual assigned job reaches the worker; forged IDs and mismatched jobs are rejected.
- Model requests, replies, calculations, and outputs are visible during a run in native PostgreSQL.
- Concurrent workers cannot exceed the shared allowance or reuse another run's files.
- Replies with invented columns, invalid recipes, wrong numbers, or mismatched output types fail checks.
- Duplicate delivery reuses a known receipt; unknown outcomes do not trigger another model call.
- Cancellation, database loss, process death, and partial file publication retain accurate evidence.
- D1 does not ask the main model again; D2 reviews receive bounded public worker facts and errors.
- No hidden grader information enters prompts; generated code never executes in the host.

Use the project `.venv`, Ruff, `scripts/check.ps1`, and native PostgreSQL checks. Retain
old pilot evidence. Do not relabel deterministic worker tests as model-generated research
runs. Live model smokes come only after these checks and use an explicit bounded config.

## 10. Completion checklist

- [x] Implement the shared worker support and check its core invariants.
- [x] Implement the six independent MCP servers and their published contracts.
- [x] Add deterministic calculation tests and representative refusal cases.
- [x] Run real-MCP and native-PostgreSQL integration tests.
- [x] Check shared budgets, prompt separation, saved usage links, and version records.
- [ ] Complete a bounded live-model smoke and retain both successful and failed attempts.
- [x] Update running instructions and remaining limits based on what actually passed.

CSV P1/P2 execution, remote MCP hosting, and a new dashboard remain separate work.
An independent development grader is now implemented; see [evaluation](../evaluation/Running.md).
