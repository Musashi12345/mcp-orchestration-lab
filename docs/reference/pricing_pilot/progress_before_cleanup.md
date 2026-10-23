# Implementation progress

## Data-analysis evaluation: 2026-10-21

Added ten synthetic CSVs and fifteen public questions for development evaluation. A
separate host-only evaluator calculates expected answers without importing worker
calculations. It checks declared final outputs, input/file identity, exact text IDs,
duplicates, numeric tolerances, change logs, and the requested forecast's held-back
split and recalculated errors. Expected answers are never supplied to model requests.

Native PostgreSQL retains immutable `evaluation_result` records linked to each run and
its execution/input records. Chart/report quality and appropriate clarification require
a named human review; pending results keep unknown task success. A separate evaluation
does not rewrite the executor's completion record.

The new `eval` commands list tasks, grade ended runs, record reviews, execute fresh
paired D1/D2 batches, and export CSV/JSON/Markdown reports. Batches shuffle order with
a saved seed, preserve failed/incomplete attempts, enforce a shared request ceiling,
and reserve equal per-run limits before starting each matched block. No live model
evaluation has been run. See [the guide](evaluation/Running.md) and
[validation evidence](../reports/evaluation_validation/README.md).

These public tasks are a development collection, not unseen research evidence. New
P1/P2 execution, controlled service-failure evaluation, broader prediction-quality
tasks, and a final unseen collection remain separate work.

Final verification passed Ruff and formatting, then **171 tests passed and 1 skipped**
with native PostgreSQL and Docker enabled. The successful native paired example, its
run-linked grades, copied files, and thirteen fixed model requests are retained in
`reports/evaluation_validation/native_pair/`. Source, lock, and fixture hashes match.

## Six agents implemented: 2026-10-21

Built Understanding, Cleaning, Combining, Analysis, Prediction, and Report as six separate
official-SDK MCP servers. Each has separate models, worker logic, calculations, and server
entry points. Both stdio and loopback streamable HTTP use the existing connection adapter.
The planner still selects tools and dependencies without a fixed agent order.

The executor's shared worker service provides checked file access, bounded model calls,
live stages, output registration, and saved results. Calls from the main planner and workers
share the same allowance. CSVs, charts, and Markdown stay on disk with versions and source
links in PostgreSQL. No generated worker code runs in the host.

Root `start_agents.ps1` and `stop_agents.ps1` manage the orchestrator and all six agents.
They save PIDs, creation times, launch identities, and logs; stopping checks process identity
before terminating a process. The local orchestrator API supports discovery, planning,
execution, and reading live records. See [the running guide](Agents/Running.md).

The five findings from the 2026-10-19 audit now have fixes and acceptance tests: explicit
known-failure backups, public failure details in D2, checks for definite linked type
mismatches, scheduling after skips, and final records on early stops. Original audit evidence
is retained as a historical account of the earlier code.

Full validation passed Ruff and formatting, then **142 tests passed and 1 skipped** with
native PostgreSQL and Docker enabled. A separate native PostgreSQL API test also passed.
Tests cover each agent through real MCP, actual HTTP MCP execution, live worker records
read by a second PostgreSQL connection, shared allowances, cancellation, and start/stop
PID safety. Model replies were deterministic fixtures; no live worker-model call was made.
See [saved validation](../reports/agents_validation/README.md).

The user's production PostgreSQL connection remains to be supplied in `.env`. New
data-analysis P1/P2, independent grading, and a new dashboard remain separate work.

## Six agent build plans: 2026-10-21

Created [one plan per agent](Agents/README.md): Understanding, Cleaning, Combining,
Analysis, Prediction, and Report. Each plan defines an independent stdio MCP server,
its first public tool, inputs/outputs, bounded LLM work, saved records, and test cases.
The shared plan covers worker model-call accounting, file versions, actual job delivery,
and a proposed local support service for shared records and allowances.

This earlier step added documentation only. The implementation above now supersedes its
unbuilt status and resolves the five 2026-10-19 audit findings.
The main planner still chooses the required subset and order without a fixed agent chain.

## Planner and executor audit: 2026-10-19

The main data-analysis flow matches the agreed design, but five gaps were reproduced:
failure-driven fallbacks, missing error details in D2 reviews, type checks for linked
outputs, readiness after skipped steps, and final summaries on early-stop paths.
No production code was changed during this audit. See the
[audit report](../reports/orchestration_audit_2026-10-19/README.md) for examples and evidence.

Fresh validation passed Ruff and formatting, with **111 tests passed and 6 skipped**.
The native PostgreSQL integration test passed separately. No live model or Docker test
was run in this audit. The six workers were deferred at that time; their implementation
is recorded above. Data-analysis P1/P2 remain deferred.

## Data-analysis planner and executor: 2026-10-15

The new `orchestration/` package implements MCP discovery, a saved tool cache, strict CSV
registration, Main Task creation, tool selection, subtask refinement, LLM-created DAGs,
validation/correction, and a separate saved handoff. Its system prompt specifies no agent
names, preferred tools, or required analysis sequence.

The DAG executor schedules newly ready work as individual calls finish. It manages reusable
MCP connections by configured server, saves attempts and outputs during execution, supports
conditional paths, and records task-defined D1/D2 reviews and replacement plan versions.
The production store is local PostgreSQL; files remain on disk. Source/configuration/tool
identities and same-run record links are checked. The redundant `controller.py` re-export
was removed; the retained pricing pilot imports its controller directly from `episodes.py`.

The scope agreed for this phase excludes the six new LLM workers. The new path is D1/D2;
data-analysis P1/P2, independent analysis grading, and a new dashboard are future work.
Original pilot code, fixtures, SQLite records, and run evidence remain available.

See [the running guide](Planner%20and%20Executor/Running.md) for configuration, commands,
review-rule semantics, database tables, test options, and current boundaries. The user's
production PostgreSQL connection remains to be supplied in `.env`; `.env.example` is ready.

The original pilot progress below describes the earlier pricing-task lane.

Verified on 2026-10-15: `scripts/check.ps1` passed Ruff and formatting, then **116 tests
passed, 1 skipped** with native PostgreSQL and Docker checks enabled. The skipped test
was the subscription-consuming live smoke, which passed separately. Its retained run,
`run_7ae8b8a0167f4de689e2d2512b5350ec`, completed through four actual Codex planning calls
and one real MCP tool attempt. The audit's source hash matches the final implementation.
The failed development attempts and full-suite XML are retained under
`reports/orchestration_validation/`. These are development checks, not a model benchmark.

Started 2026-10-08 from the supplied execution-engine build guide. The local four-mode
pilot is implemented and runnable; the full scientific study remains a separate phase.

| Guide milestone | Status |
|---|---|
| 0 â€” contracts and fixture | Six public policy fixtures, fresh worlds, private independent acceptance and wrong-policy controls |
| 1 â€” common runtime | Immutable artifacts/provenance, journal, current-revision validity, semantic keys, receipts, bounded retry and budgets |
| 2 â€” MCP workers | Two official MCP v2 stdio servers, nine typed tools including bounded public-test refinement |
| 3 â€” DAG mode | Validation, bounded concurrent scheduler, guards, conditional bindings, finite common expressions, fixed recovery control |
| 4 â€” Python mode | Standard-library SDK, framed bridge and restricted Docker runner; no generated host execution |
| 5 â€” initial planner | Codex using saved ChatGPT login, command-router protocol, structured generation, initial format repair and usage logs |
| 6 â€” adaptation | Common enforced barriers and normalized snapshots; KEEP/REVISE/STOP, persisted source versions and fresh executor replacement |
| 7 â€” pilot harness | Challenge fixtures, controlled lost acknowledgments, randomized complete blocks, CSV/export/analysis/plots |
| 8 â€” transfer/presentation | Local dashboard and persisted jobs implemented; LLM workers/general code-repair transfer and held-out study remain |

## Verified on 2026-10-08

- Ruff lint and format checks pass. **62 tests pass with real Docker tests enabled**.
  Without Docker opt-in, four container tests are skipped.
- Real MCP discovery reports all nine tools, protocol 2025-11-25, Python 3.12.14,
  MCP 2.3.0, SQLite 3.53.1 and Docker engine 29.2.1.
- Runner base image is pinned by digest. Real probes confirm non-root UID 65532,
  read-only root filesystem, loopback-only networking and no host-secret environment.
  Both adaptive representations and predeclared fixed fallbacks are exercised.
- Real Codex initial generation and execution completed in all four modes. Structured
  replanning completed at both checkpoints in adaptive modes. These are development
  smokes with changing source/settings, not a randomized model benchmark.
- Selected frozen-source offline batch: `batch_425d082ee21f4c83964eab973311a4f5`,
  16 episodes, 148 broker requests, 154 attempts, 20 committed patches and 12 records.
  Six lost-acknowledgment faults fired; the other two fault-assigned runs never reached
  recording and remain failed episodes. Four naive fixed-plan challenge failures were
  expected and retained. Stub results do not imply a model representation winner.
- Source digest for that batch: `e078ee305a64a35e5b10287c7ef0400b62f3da1346d96f52fa831b13ecab30bd`.
  All 16 summaries match the manifest's source and lock hashes. Attempts and event counts
  reconcile with journals. All 357 selected export file hashes verify.
- Exported batch evidence, CSVs, JSON analysis, Markdown report and PNG/SVG figures:
  `reports/final-four-mode-smoke/`. Selected Codex adaptive Python evidence:
  `reports/codex-adaptive-python/`.
- Dashboard jobs were queued through the browser and completed using the shared controller,
  including adaptive Python with a lost acknowledgement. Tokenless POSTs are rejected.
  Job persistence marks interrupted work without replaying it. Preview:
  `reports/dashboard-preview-final.png`.

## Remaining research work

Choose a broader task corpus, real isolated repository fixtures and the worker-transfer
question; freeze models/prompts/configurations; run a properly sized held-out study and
interpret uncertainty. Automatic host-crash reconciliation, non-idempotent capabilities
and finer invalidation are optional runtime extensions, explicitly listed in limitations.
The 96-episode offline configuration is provided; only the selected 16-episode final smoke
batch was executed as a frozen-source development batch.

No remote, commit or publication was created. Initialize Git from the user's normal
terminal before committing; source and earlier run evidence have been preserved.

Checkpoint requests include active source, observed receipts/diagnostics and remaining budgets.
Dashboard job settings are persisted with the request. Queued and running jobs are marked
interrupted on restart, preventing a new configuration from silently changing queued work.
