# Implementation progress

## CSV P2 implemented and validated: 2026-10-25

P2 now generates Python directly and uses the same host-defined review rules as D2.
The shared review controller saves public snapshots and bounded correction attempts.
KEEP resumes the same runner; REVISE starts remaining work in a fresh runner with
verified saved results after the previous container is removed; STOP retains its reason.
One broker, official MCP adapter, gateway, allowance, and deadline span all versions.

D2 and P2 now preserve unresolved failures across revisions. A review can assign a
replacement step to recover specific failure IDs; only that step's success clears them.
The shared selected-snapshot byte bound is `max_result_bytes`. Earlier D2 evidence
predates these controls and remains retained under its original source identity.

CLI/API routing and explicit four-mode evaluation are implemented. Focused baseline
validation passed 31 existing checks; the new snapshot/revision smoke passed 14 checks.
Final-source Ruff/formatting passed for 111 Python files. The full check passed 205
tests and skipped one before an existing worker-access test hit a Windows loopback
reset. The unchanged case and remaining CLI/support checks passed in a 17-test
completion run: **221 distinct non-live cases verified, 1 live-model skip**. Both
reports and their combined coverage record are retained. An earlier core-source full
run passed 215 tests and one skip before shared Docker image lookup was hardened.
Real Docker, official MCP processes, native PostgreSQL, API/service lifecycle, and
matched four-mode independent evaluation were enabled. The P2 evaluation episode
used two containers, one worker tool attempt, and seven scripted model calls. Seven
local services now run the final source, with six MCP tools and confirmed application
database access. No live provider request was submitted. See
[retained validation](../reports/p2_validation_2026-10-25/README.md),
[P2](Planner%20and%20Executor/P2.md) and
[the build checklist](Planner%20and%20Executor/P2_Implementation_Plan.md).

## CSV P1 implemented: 2026-10-23

The shared CSV planner now accepts P1. Its last stage generates a limited async Python
program directly, saves candidates and corrections, and saves accepted source/hash before
execution. P1 has no DAG intermediate and no main-planner calls after acceptance.

The new `ProgramExecutor` inherits the shared `Runtime` and uses the same `ToolBroker`,
official MCP adapter, worker gateway, budgets, states, attempts, and file checks as D1/D2.
The program can request sequence, parallel calls, conditions, and prewritten fallbacks.
Unknown outcomes stop execution. Jobs that are not needed can be skipped without calls.

Generated code runs only in the new CSV Docker image. The official Python 3.12 slim base
is pinned by digest. The image contains only the small SDK, without project data or
evaluator code. Runs use the approved 1 CPU, 512 MiB, 64 PID, 16 MiB temporary-space profile,
non-root identity, no network/host mounts, a read-only root, and dropped capabilities.
Image identity, actual settings, diagnostics, cleanup, and results are saved per run.

CLI/API execution and independent evaluation now support D1/D2/P1. Explicit batches can
compare all three; P2 remains unimplemented. Fixed-reply tests already exercised real
Docker/MCP execution and a matched native PostgreSQL D1/D2/P1 evaluation. Full validation
and retained-evidence checks are linked from [Cross-check](Cross-check/README.md).

Final `scripts/check.ps1` validation passed Ruff/formatting for 107 Python files and
**180 tests passed, 1 live-model test skipped in 547.46 seconds**. Real Docker, official
MCP processes, API/service lifecycle, and native PostgreSQL checks were enabled. All
8,902 prior evidence files were unchanged. No test containers, owned managed services,
or test PostgreSQL processes remained. See [saved P1 evidence](../reports/p1_validation_2026-10-23/README.md).

README conflict markers were removed while preserving the full guide and the title
`MCP Execution Lab`, as requested. See [P1 setup and contract](Planner%20and%20Executor/P1.md).

## Shared runtime preparation: 2026-10-23 (earlier state)

Extracted shared execution admission, MCP/worker contexts, step evidence, collection,
review tracking, and final records into `orchestration/runtime.py`. The DAG executor
inherits this common layer. Ruff passed; 33 executor/boundary/audit-fix tests passed
using real MCP fixtures. No live model calls were made.

At this earlier point P1 was not enabled. After discussing Windows isolation options, the user selected a
new CSV-only Docker runner and is committing the current changes before implementation
continues. No runner or Windows sandbox setup was performed. See
[P1 status and agreed behavior](Planner%20and%20Executor/P1.md).

## CSV-only cleanup: 2026-10-23

Removed the superseded pricing-policy source, its DAG/broker/world/SQLite journal,
generated-Python runner and SDK, container definition, old independent grader, dashboard,
experiment plotting/export code, pricing fixtures/configs, and their tests. The root CLI
now exposes only `analysis`, `eval`, and `models`.

Moved the needed model-provider bridge into `orchestration/model_clients.py`. It uses
current orchestration errors and explicitly supplied response schemas. Pricing fallback
types and reference/stub provider branches are gone. The CSV live-smoke configuration
now comes from the existing agent settings. Removed unused async-SQLite dependencies
from the project and regenerated the lockfile.

Saved run files, SQLite databases, batches, and reports were not selected for deletion.
The pre-cleanup audit and its evidence were moved intact to a dated history folder.
See [current state and removal details](Cross-check/README.md) and
[cleanup evidence](../reports/csv_cleanup_2026-10-23/).

Fresh validation passed Ruff and formatting for 95 Python files, then **131 tests passed
and 1 skipped in 288.31 seconds**. Native PostgreSQL and real MCP checks were enabled;
live model calls were disabled. All 8,893 inventoried existing evidence files were unchanged,
and the managed services were stopped after testing.

## Current implementation

- Planner: actual MCP discovery, saved tool catalogue, CSV registration, Main Task,
  tool selection, subtasks, checked model-created DAG or Python, and accepted handoff.
- Executor: readiness-based parallel scheduling, conditions, explicit failure branches,
  saved attempts/results, uncertainty stops, shared D2/P2 review policy, and P1/P2 through
  Docker runners connected to the same tool runtime.
- Agents: Understanding, Cleaning, Combining, Analysis, Prediction, and Report as six
  separate official-SDK MCP services with bounded model recipes and handwritten operations.
- Storage/API: PostgreSQL records throughout the run, disk files with hashes/parent links,
  local API, and root start/stop scripts managing seven service processes.
- Evaluation: fifteen public development tasks, ten synthetic CSVs, independent checks,
  human review, native PostgreSQL grades, and explicit matched D1/D2/P1/P2 reports.

An unseen final collection, a new dashboard, broader prediction scoring, and controlled
service-failure evaluation remain unimplemented. Each installation needs its own `.env`
database connection. Live worker-model quality has not been established.

## Earlier evidence

The previous evaluation validation passed 171 tests and one live-model skip, including
tests for the now-removed pilot. It describes that earlier source, not today's test count.
See [evaluation evidence](../reports/evaluation_validation/README.md),
[agent evidence](../reports/agents_validation/README.md), and
[pre-cleanup progress](reference/pricing_pilot/progress_before_cleanup.md).
