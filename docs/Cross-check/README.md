# Current CSV implementation

Updated: 2026-10-23. The application now has one active domain: CSV data analysis.

P1 now generates Python directly and executes it only in a separate CSV Docker image.
It shares the tool broker, worker gateway, budget, and run evidence with D1/D2. P2 remains
unimplemented. See [the P1 source walkthrough](../Planner%20and%20Executor/P1.md).

## Active modules

| Component | Current source |
|---|---|
| CLI | `src/mcp_execution_lab/cli.py`: `analysis`, `eval`, `models` only. |
| Planner | `orchestration/planner.py`, `graph.py`, `programs.py`, `models.py`: shared task/tool stages, then checked DAG or direct Python. |
| Executor | `orchestration/runtime.py`, `executor.py`, `program_executor.py`, `broker.py`, `mcp.py`: shared checked calls and records; DAG scheduling or P1 pipe requests. |
| Python boundary | `orchestration/program_container.py`, `program_sdk/`, `containers/csv_python/Dockerfile`: pinned image, approved limits, framed messages, source checks, cleanup. |
| Model bridge | `orchestration/model_clients.py`, `model.py`, `budget.py`: Codex/command routes, request records, shared allowance. |
| Storage | `orchestration/storage.py`, `files.py`: PostgreSQL records and disk files linked to each run. |
| Agents | `agents/understanding`, `cleaning`, `combining`, `analysis`, `prediction`, `report` and `agents/common`. |
| Evaluation | `evaluation/`: frozen CSV suites, independent checks, human review, matched D1/D2/P1 batches. |
| Services | `orchestration/server.py`, `start_agents.ps1`, `stop_agents.ps1`. |

Paths below `orchestration`, `agents`, and `evaluation` are inside `src/mcp_execution_lab`.
Read [current setup](../../README.md), [planner/executor behavior](../Planner%20and%20Executor/Running.md),
[agent methods](../Agents/Running.md), and [evaluation](../evaluation/Running.md).

## Removed code

The pricing world/catalogue/contracts, old DAG and broker, old journal, old planner
session/reference plans, episode/experiment harness, old grader, plotting/export code,
dashboard, generated-Python runner and SDK, Dockerfile, pricing fixtures/configs, and
their tests were removed. The old CLI commands no longer exist. Docker/async-SQLite
dependencies used only by that implementation are no longer required.

The useful provider bridge was moved into the CSV orchestration package. It now uses
current errors and requires a supplied response schema, with no pricing fallback types.
The live CSV smoke reads agent settings instead of the removed pricing config.

The removal did not bring back the older pricing runner. P1 was subsequently implemented
with a new CSV-only runner. P2 and unrelated documented audit findings remain open.

## Validation

P1 verification uses fixed model replies and real Docker, official-SDK MCP processes,
and isolated native PostgreSQL. See [P1 validation evidence](../../reports/p1_validation_2026-10-23/README.md)
for the final counts, hashes, sandbox evidence, and evidence-preservation result.

The final P1 suite passed Ruff/formatting for 107 Python files and **180 tests passed,
1 live-model test skipped in 547.46 seconds**. All 8,902 prior evidence files were unchanged.
No P1 containers, owned managed services, or test PostgreSQL processes remained.

The following counts describe the earlier cleanup source:

`scripts/check.ps1` passed Ruff and formatting for 95 Python files, then **131 tests passed,
1 skipped in 288.31 seconds**. Real MCP and temporary native PostgreSQL checks were enabled.
The skipped case requires live Codex calls; no live provider test was run. All 66 current
modules import, and all 19 removed module names are unavailable. Final managed service
state is `STOPPED`, with zero owned processes running.

## Preserved evidence and earlier deep dive

Saved files under `runs/`, `batches/`, and `reports/`, plus the old dashboard database,
were retained. The cleanup records a before/after hash check of existing evidence:

- [Removal manifest](../../reports/csv_cleanup_2026-10-23/removal_manifest.json)
- [Cleanup validation](../../reports/csv_cleanup_2026-10-23/validation.json)
- [Fresh full-suite results](../../reports/csv_cleanup_2026-10-23/full_checks.xml)

The [full earlier walkthrough](2026-10-23-before-cleanup/README.md) and all its evidence
were moved intact into the dated folder. It describes the pre-cleanup source and contains
references to files that are now removed or moved. Use it as history, not as today's
module inventory or test result. Historical documentation is also retained under
[reference/pricing_pilot](../reference/pricing_pilot/README.md).
