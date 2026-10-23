# Code cross-check: current application

Audit date: **2026-10-23**, using the user's Asia/Calcutta date context.

This walkthrough was written after reading the current source, reading the relevant
tests, running the complete project check, and running four small audit probes. Earlier
chat descriptions and design documents were treated as background, not proof of behavior.
No production source was changed for this audit. The probes use fixed data, no real model,
and an explicitly enabled in-memory SQLite test store; the full suite separately tests
native PostgreSQL, real MCP processes, and Docker.

## What the application is today

There are **two execution paths**, with different classes, file types, and storage:

| Path | Entry | Modes | Storage and purpose |
|---|---|---|---|
| New data analysis | `scripts/lab.ps1 analysis`, local API, `scripts/lab.ps1 eval` | D1/D2 | PostgreSQL records plus disk files; six data agents and a development evaluator. |
| Retained pricing pilot | `scripts/lab.ps1 run`, `serve`, `batch`, `compare` | D1/D2/P1/P2 | SQLite journals, a pricing-policy world, restricted Docker Python, its own grader/dashboard. |

Evidence: [main (cli.py:206)](C:/Learning/R-Project/src/mcp_execution_lab/cli.py:206), [Planner.plan (planner.py:88)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/planner.py:88),
[Application (service.py:15)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/service.py:15), [run_episode (episodes.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/episodes.py:62),
[dashboard.py:1](C:/Learning/R-Project/src/mcp_execution_lab/dashboard.py:1), [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40).

Therefore the data-analysis project does not yet provide a completed four-mode research
comparison. Its planner, DAG engine, six agents, and first evaluator exist. The old Python
runner has not been connected to the new data-analysis runtime. An old P2 pricing result
cannot stand in for a new P2 data-analysis result. See [the legacy distinction](06_Entry_Points_And_Legacy.md).

## Read the pillars in this order

1. [Planner](01_Planner.md): inputs, four model stages, tool cache, plan rules, handoff.
2. [Executor](02_Executor.md): readiness, parallel work, tool calls, failures, reviews.
3. [Agents](03_Agents.md): shared support service, every agent's input, method, and limit.
4. [Evaluation](04_Evaluation.md): independent grading, human review, paired batches.
5. [Storage and model route](05_Storage_And_Model_Route.md): database/file records,
   model requests, budgets, and credentials/process boundaries.
6. [Entry points and old pilot](06_Entry_Points_And_Legacy.md): API, scripts, ports, Python.
7. [Findings and verification](07_Findings_And_Verification.md): reproduced gaps, missing
   work, tests, and documentation mismatches.

The explanations use simple words first and then give the exact class, method, and
source link. A link ending in `:123` points to line 123 in the inspected source. These
line numbers belong to the snapshot in [source_manifest.json](evidence/source_manifest.json).
Later code changes can make them stale.

## Words used in the walkthrough

| Code word | Simple meaning here |
|---|---|
| DAG | A map of jobs and what each job must wait for; it cannot contain a loop. |
| MCP | The common way this app discovers and calls a tool in another process. |
| Schema | The allowed fields, value types, and limits of a JSON message. |
| Binding | A rule for getting an input value, such as a field from an earlier result. |
| Broker | The shared gate that checks, records, and sends a tool call. |
| Snapshot | A saved earlier output that a revised plan can reuse. |
| Hash | A fingerprint of exact content; changed bytes give a different fingerprint. |
| Transaction | A small group of database writes that commit or fail together. |
| Idempotent | Repeating an operation has the same effect as doing it once. |
| Receipt | The saved result used to confirm what a worker returned. |

## Actual workspace state checked during this audit

- The production Python source hash matches the saved 2026-10-21 validation snapshot.
  Current hash: `a5f846f0795a441ef71a040f14e4292a17e64ae462fe8a7bb009fcd2cf0d0812`.
- The dependency lock hash is
  `370815fd093cab98c60f63b3f529b2c0a27b339105c9795743217ec6ce14ef53`.
- `.env` is absent and `MCP_LAB_DATABASE_URL` is absent in the checked environment.
  User-database connectivity was consequently not claimed or tested. Tests create
  separate temporary native PostgreSQL clusters instead.
- A Codex executable is present. Its login, current model availability, subscription
  allowance, and live worker responses were not verified by this audit.
- Managed services were stopped before validation. The service lifecycle test starts and
  stops its own processes; final ownership checks are recorded with the evidence.

Evidence: [probe output](evidence/probes.json),
[validation_summary.json:1](C:/Learning/R-Project/reports/evaluation_validation/validation_summary.json:1),
[local_environment (config.py:33)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/config.py:33),
[source_identity (provenance.py:9)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/provenance.py:9), and
[fresh verification](evidence/verification.json).

## Fresh verification and what it proves

`scripts/check.ps1` passed Ruff and formatting for **120 Python files**, then
**171 tests passed, 1 skipped, in 368.27 seconds**. Native PostgreSQL and Docker checks
were enabled. The live Codex smoke was disabled. The raw test timestamp may follow the
host's clock; the audit filename/date follows the client date above.

Evidence: [check.ps1:1](C:/Learning/R-Project/scripts/check.ps1:1),
[fresh full-suite XML](evidence/full_checks_2026-10-23.xml),
[test_bounded_live_codex_planner_with_native_postgres_and_real_mcp (test_postgres.py:77)](C:/Learning/R-Project/tests/orchestration/test_postgres.py:77).

This proves the checked engineering cases passed on this code and environment. It does
not establish live model quality, correctness on arbitrary CSVs, protection against every
failure, or a research winner. The new worker integration tests use scripted replies;
their MCP calls, database writes, file calculations, and process boundaries are real.
Evidence: [AgentModel (workers.py:51)](C:/Learning/R-Project/tests/agents/workers.py:51),
[EvalModel (test_integration.py:22)](C:/Learning/R-Project/tests/evaluation/test_integration.py:22).

## Main corrections to a loose description of the project

- “No hardcoded agent order” is supported for the main planning prompt. Structural rules,
  allowed operations, service role/module mappings, and ready-step dispatch order still exist.
- The tool cache keeps the servers' descriptions directly; it does not make a separate
  model-written summary of every tool.
- Topological sorting checks the graph. Actual execution repeatedly starts ready work;
  it does not execute one fixed sorted list from top to bottom.
- Combining can join several files in one call, repeatedly applying the same keys and
  relationship rule. The public input allows two to eight files.
- A saved worker record marked `SUCCEEDED` means its receipt was saved. Inspect its
  result's `outcome` to know whether its assigned job completed.
- An execution result marked `COMPLETED` is not an independent grade. Grading is a
  separate action and record.
- “All data is saved” means registered application records/files. It does not mean
  every intermediate variable, every accessed cell, or automatic recovery after a crash.

Each point is expanded with source evidence in the relevant pillar document.
