# Entry points, service processes, and the retained pricing pilot

## 1. Which command reaches which application

`scripts/lab.ps1` runs the project `.venv` Python module from the project root. The root
CLI forwards `analysis` and `eval` to the new modules. Older commands keep their older
episode/batch/dashboard code. Similar mode names do not join those runtimes together.
Evidence: [lab.ps1:1](C:/Learning/R-Project/scripts/lab.ps1:1), [main (cli.py:206)](C:/Learning/R-Project/src/mcp_execution_lab/cli.py:206).

| Route | Current behavior |
|---|---|
| `analysis db-init` | Create/check the new PostgreSQL schema. |
| `analysis plan` | Discover, register CSVs, make and save D1/D2 handoff; do not execute tools. |
| `analysis execute` | Execute a saved, unstarted handoff with matching config. |
| `analysis run` | Plan and execute in one CLI request. |
| `analysis inspect` | Read a new run's records and events from PostgreSQL. |
| `eval list/grade/review/run/report` | New data-analysis development evaluation. |
| Root `run/batch/compare/analyze/inspect/export` | Retained pricing-pilot runs and evidence, not new CSV runs. |
| Root `serve` | Retained pricing dashboard, default port 8765. |

Evidence: [main (cli.py:48)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/cli.py:48),
[dispatch (cli.py:15)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/cli.py:15), [main (cli.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/cli.py:62),
[main (cli.py:206)](C:/Learning/R-Project/src/mcp_execution_lab/cli.py:206).

Example shapes from the new CLI parser, after local database/model configuration:

```powershell
.\scripts\lab.ps1 analysis db-init
.\scripts\lab.ps1 analysis plan --query "YOUR QUESTION" --csv C:\path\input.csv --config configs/agents_stdio.yaml --mode D1
.\scripts\lab.ps1 analysis execute --run RUN_ID --config configs/agents_stdio.yaml
.\scripts\lab.ps1 analysis inspect --run RUN_ID
```

`agents_stdio.yaml` starts MCP subprocesses through the client. `agents.yaml` connects
to managed HTTP services started by the root start script. Planning/model commands use
the configured provider; these examples were not submitted to a live model in this audit.
Evidence: [agents_stdio.yaml:1](C:/Learning/R-Project/configs/agents_stdio.yaml:1), [agents.yaml:1](C:/Learning/R-Project/configs/agents.yaml:1),
[Connections._own_session (mcp.py:45)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/mcp.py:45).

## 2. New local HTTP API

| Route | Authentication | Behavior |
|---|---|---|
| `GET /` and `/health` | None | Service/PID/instance and whether a non-placeholder DB URL is present. |
| `GET /tools` | Admin bearer token | Discover current configured tools; no database is required. |
| `GET /runs` | Admin bearer token | Latest 50 PostgreSQL runs. |
| `GET /runs/{run_id}` | Admin bearer token | Run, records, ordered events. |
| `POST /runs` | Admin bearer token | Parse question/CSV paths, plan, then execute unless `plan_only` is true. |
| `POST /runs/{run_id}/execute` | Admin bearer token | Execute accepted saved handoff. |
| `POST /shutdown` | Admin bearer token | Request graceful service shutdown. |

Evidence: [create_app (server.py:34)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:34),
[create_app.authorized (server.py:38)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:38),
[create_app.endpoint (server.py:64)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:64).

`POST /runs` allows a body up to 64 KiB, a question up to 10,000 characters, and one to
eight local CSV paths. Paths are resolved on the host, copied, and registered; this is
not a multipart browser upload service. Execution is awaited in the HTTP request rather
than queued as a durable background job. Other requests can inspect committed progress.
Evidence: [RunRequest (server.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:25),
[create_app.endpoint (server.py:64)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:64).

The health route's `READY` and `database: CONFIGURED` do **not** confirm PostgreSQL
connectivity or a working model login. Connection/schema checks occur on actual run or
inspection requests. There is no new analysis dashboard, evaluation HTTP route, or
clarification-answer/resume endpoint. Evidence:
[create_app.health (server.py:43)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:43),
[create_app (server.py:34)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:34).

The server binds loopback and uses constant-time token comparison. Managed MCP HTTP
addresses also use loopback. This is a trusted local-development API, not a deployed
multi-user service with TLS, user accounts, or per-user database isolation.
Evidence: [main (server.py:155)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:155),
[create_app.authorized (server.py:38)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:38),
[ServerConfig.connection (models.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/models.py:40),
[serve (server.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/server.py:25).

## 3. Start and stop scripts

The root `start_agents.ps1` starts seven hidden project-Python processes: orchestrator
plus the six MCP agents. The default base port is 8766; agents use 8767 through 8772.
The script validates the base range, checks ports, takes a project-specific mutex, creates
an instance ID and random admin token, redirects logs, saves PID identities, and waits
for matching healthy instances. It does not start the user's PostgreSQL service or submit
a model request. Evidence: [start_agents.ps1:1](C:/Learning/R-Project/start_agents.ps1:1),
[agent_processes.ps1:7](C:/Learning/R-Project/scripts/agent_processes.ps1:7),
[create_app.health (server.py:43)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:43),
[serve (server.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/server.py:25).

State is saved under `.runtime/agents/pids.json`; every launch has retained logs and a
PID snapshot. The admin token is kept in a local file and process environment, not
printed as part of the process table. Repeating start with all seven owned healthy
services keeps them running. A partial existing launch requires stop first. Failed
startup rolls back processes owned by that launch.
Evidence: [start_agents.ps1:1](C:/Learning/R-Project/start_agents.ps1:1),
[agent_processes.ps1:20](C:/Learning/R-Project/scripts/agent_processes.ps1:20).

`stop_agents.ps1` checks the saved project root, Python executable, and exact process
creation time. When CIM is available it also checks module and instance in the command
line. If CIM access is denied it falls back to executable plus exact creation time.
It requests token-authenticated shutdown, waits up to four seconds, checks identity again,
and uses `taskkill /PID ... /T /F` for remaining owned processes. This avoids killing an
unrelated process merely because Windows reused its PID.
Evidence: [stop_agents.ps1:1](C:/Learning/R-Project/stop_agents.ps1:1),
[agent_processes.ps1:32](C:/Learning/R-Project/scripts/agent_processes.ps1:32),
[agent_processes.ps1:52](C:/Learning/R-Project/scripts/agent_processes.ps1:52),
[test_start_discovery_repeat_start_and_safe_stop (test_services.py:15)](C:/Learning/R-Project/tests/agents/test_services.py:15).

Logs and history are retained on stop. Forced termination is not a graceful run-resume
mechanism. Restart after source changes is necessary: already loaded worker processes
keep their startup source identity, and the planner checks that identity.
Evidence: [agent_processes.ps1:52](C:/Learning/R-Project/scripts/agent_processes.ps1:52),
[serve (server.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/server.py:25), [Planner._prepare (planner.py:148)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/planner.py:148).

Port assignment and the six role/module mappings are fixed infrastructure choices.
They do not force a planner sequence. The code still needs an address and implementation
for every configured service. Evidence: [main (server.py:155)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/server.py:155),
[MODULES (registry.py:5)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/registry.py:5), [SYSTEM_PROMPT (model.py:12)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/model.py:12).

## 4. The old four-mode pricing pilot

`episodes.run_episode()` loads a pricing-policy task, creates its `World`, SQLite
`Journal`, transport, `Broker`, and `PlanningSession`, and runs the selected representation.
The old `DAGExecutor` and old `PythonRunner` both receive **that same old broker**. Its
task grading and fault support belong to this path.
Evidence: [run_episode (episodes.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/episodes.py:62), [Broker (broker.py:14)](C:/Learning/R-Project/src/mcp_execution_lab/broker.py:14),
[DAGExecutor (dag.py:134)](C:/Learning/R-Project/src/mcp_execution_lab/dag.py:134), [PythonRunner (python_runner.py:46)](C:/Learning/R-Project/src/mcp_execution_lab/python_runner.py:46),
[evaluate (benchmark.py:30)](C:/Learning/R-Project/src/mcp_execution_lab/benchmark.py:30).

| Mode | Retained pilot meaning | New data-analysis meaning today |
|---|---|---|
| D1 | DAG with no checkpoint replanning | New DAG with no execution review calls; workers can still call models. |
| D2 | DAG with two shared task checkpoints | New DAG with configured count-based review opportunities. |
| P1 | Restricted generated Python without checkpoint replanning | Not wired into the new runtime. |
| P2 | Restricted generated Python with shared checkpoints | Not wired into the new runtime. |

Evidence: [run_episode (episodes.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/episodes.py:62),
[Planner.plan (planner.py:88)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/planner.py:88),
[Executor._review (executor.py:290)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:290),
[run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40).

D1 never meant “no model anywhere”: it disables execution replanning, while initial
planning and selected LLM agents can still use models. The four study cells distinguish
representation and execution review, not whether data tools contain model requests.
Evidence: [Planner._prepare (planner.py:148)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/planner.py:148),
[choose (worker.py:11)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/worker.py:11),
[Executor._review (executor.py:290)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:290).

The dashboard imported by root `serve` uses old tasks/episodes. Its four selectors are
not evidence of a four-mode CSV dashboard. The private old grader reads its own fixtures
and effect evidence; those contents should not be copied into a planning request.
Evidence: [dashboard.py:1](C:/Learning/R-Project/src/mcp_execution_lab/dashboard.py:1), [evaluate (benchmark.py:30)](C:/Learning/R-Project/src/mcp_execution_lab/benchmark.py:30),
[run_episode (episodes.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/episodes.py:62).

## 5. Where generated Python actually runs

The old `PythonRunner` validates restricted source syntax, resolves an immutable Docker
image ID, and starts a Linux container. Controls include no network, read-only filesystem,
non-root UID, dropped capabilities, no-new-privileges, PID/memory/CPU limits, and a small
temporary filesystem. Missing Docker/image fails; it does not fall back to running
generated source in the host Python process.
Evidence: [validate_source (policy.py:57)](C:/Learning/R-Project/src/mcp_execution_lab/runner_sdk/policy.py:57),
[PythonRunner.image (python_runner.py:53)](C:/Learning/R-Project/src/mcp_execution_lab/python_runner.py:53),
[PythonRunner.run (python_runner.py:87)](C:/Learning/R-Project/src/mcp_execution_lab/python_runner.py:87), [sandbox_args (python_runner.py:15)](C:/Learning/R-Project/src/mcp_execution_lab/python_runner.py:15).

A framed stdin/stdout bridge exposes bounded host-broker operations to the container.
AST restrictions are an additional language check, not the security boundary on their
own. In contrast, the six new agents run trusted handwritten operations in local worker
processes; they do not run generated programs.
Evidence: [PythonRunner.run (python_runner.py:87)](C:/Learning/R-Project/src/mcp_execution_lab/python_runner.py:87),
[validate_source (policy.py:57)](C:/Learning/R-Project/src/mcp_execution_lab/runner_sdk/policy.py:57),
[analyze (operations.py:16)](C:/Learning/R-Project/src/mcp_execution_lab/agents/analysis/operations.py:16),
[predict (operations.py:11)](C:/Learning/R-Project/src/mcp_execution_lab/agents/prediction/operations.py:11).

## 6. Work needed to close the representation gap

To evaluate all four modes on the new domain, the project still needs a generated-Python
frontend over the **new shared broker/runtime contract**, a safe container bridge for
the new references/jobs, matching review semantics, identical information/budgets, and
four-mode independent evaluation. Simply selecting P1 in the old dashboard would run
a different task/runtime. This is a conclusion from the separate current call graphs,
not a production change made during this audit.
Evidence: [ToolBroker (broker.py:11)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/broker.py:11),
[Broker (broker.py:14)](C:/Learning/R-Project/src/mcp_execution_lab/broker.py:14), [Application.execute (service.py:46)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/service.py:46),
[run_episode (episodes.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/episodes.py:62), [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40).

Read next: [findings and verification](07_Findings_And_Verification.md).
