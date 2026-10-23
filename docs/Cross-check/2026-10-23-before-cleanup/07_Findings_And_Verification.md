# Exact state, findings, and fresh verification

This is a code audit with targeted reproduction, not a claim that arbitrary runs are
bug-free. The report describes the checked snapshot. Production code was left unchanged;
new files are audit documents and evidence under `docs/Cross-check`, plus retained scratch
data created by the probes/tests.

## 1. Current state by pillar

| Pillar | Implemented and checked | Still missing or unverified |
|---|---|---|
| Planner | Real MCP discovery; saved catalogue; CSV registration; four structured stages; graph checks; handoff and traces. | Live worker-era plan quality; conversational clarification resume; semantic proof that the goal was correctly translated. |
| Executor | Readiness scheduling, parallel jobs, conditions, known-failure branches, uncertainty stop, D2 replacement plans, saved progress. | Durable interrupted-run resume; hard-kill reconciliation; a guarantee of two distinct review observations for short/parallel graphs. |
| Six agents | Six real MCP tools, typed recipes, handwritten calculations, model-call route, source-linked files/facts. | Live model choices/explanation quality; broader operation sets; semantic fact checking of every written sentence. |
| Evaluation | Independent case-specific answers, returned-output checks, human review, PostgreSQL grades, matched D1/D2 batches and reports. | New-domain P1/P2; unseen study collection; broad prediction scoring; general injected-service-failure study; statistical winner claim. |
| Storage | PostgreSQL schema and live records; disk copies/hashes/links; native DB integration tests. | User `.env`/DB connection setup; full migrations; atomic disk-plus-DB crash recovery. |
| Services | Start/stop seven processes, retained PID/log records, identity checks, local API. | New CSV dashboard; durable queued-job service; hosted multi-user product. |
| Original pilot | Four modes, old shared broker, restricted container Python, old grader/dashboard retained and tested. | Connection of that Python representation to the new data-analysis broker contract. |

Evidence: [planner](01_Planner.md), [executor](02_Executor.md), [agents](03_Agents.md),
[evaluation](04_Evaluation.md), [storage/model route](05_Storage_And_Model_Route.md),
[entry points](06_Entry_Points_And_Legacy.md). Those files link each behavior to source.

## 2. Reproduced gaps

### F1. Manual grading accepts extra input files

The grader verifies every required original filename/hash but does not require the set
of registered original inputs to equal the task's input set. A fixed audit-constructed
run with the required CSV plus an additional CSV received `task_success: true` after a
correct declared output was attached. It was explicitly marked non-model/audit data.
Evidence: [evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160),
[probe source](evidence/probes.py), [actual output](evidence/probes.json).

Impact: manually graded comparisons could differ in information supplied to the planner.
The batch runner itself supplies exactly `task.files`, so its ordinary input construction
is not shown to have this gap. Before accepting arbitrary manual runs as controlled
evidence, add an explicit original-input set check that distinguishes original inputs
from later produced datasets. This is proposed follow-up work, not an implemented fix.
Evidence: [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[Files.register_csv (files.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/files.py:160).

### F2. Oversized prompts reserve an unsent model-call slot

`ModelCalls.ask()` increments the shared call counter, then serializes/checks prompt
length, then creates the saved request record. A request rejected for `PROMPT_SIZE`
showed budget calls 1, saved call records 0, provider requests 0.
Evidence: [ModelCalls.ask (model.py:48)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/model.py:48),
[Budget.model (budget.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/budget.py:25), [actual probe](evidence/probes.json).

Impact: allowance summaries and record-based measurements can differ, and a run can
stop conservatively early. This is not evidence of an unrecorded paid request. A future
fix should define whether these are reservations or actual requests and make accounting
consistent without weakening parallel-call limits.
Evidence: [measurements (grading.py:75)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:75),
[Budget.summary (budget.py:49)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/budget.py:49).

### F3. Number-word claims bypass the digit guard

`render_text()` rejects a bare digit in model prose and inserts checked fact placeholders.
The probe confirmed that a digit claim was rejected and a placeholder rendered its saved
value, but the sentence “Total: twenty dollars.” was accepted as plain text.
Evidence: [render_text (operations.py:44)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/operations.py:44),
[probe output](evidence/probes.json).

Impact: “rejects bare digit characters” is accurate; “prevents invented numbers/facts”
would be too strong. Source-linked facts and human review remain useful, but the present
renderer does not establish full semantic truth. This is a demonstrated boundary of the
current check, not proof that every real report will contain unsupported claims.
Evidence: [render (operations.py:33)](C:/Learning/R-Project/src/mcp_execution_lab/agents/report/operations.py:33),
[review (grading.py:381)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:381).

## 3. Controls and limits that matter to research

| Issue | Exact evidence and implication |
|---|---|
| New runtime has only D1/D2 | Planner and batch reject P1/P2. Build one shared new runtime contract before treating this as the final four-way comparison. |
| Reviews are count thresholds | Current config uses 1 and 2 attempted completed steps; parallel draining can make both reviews see the same observations, and short graphs can leave one unreached. Save/review reached opportunities in any study. |
| Tool order is model-chosen within structural rules | No named domain sequence in the main system prompt; scheduler dispatch still follows the plan's listing when ready tasks compete. |
| Structural validity differs from goal correctness | Graph/schema checks cannot independently prove the selected filters, units, or business meaning match the question. |
| Registration and worker limits differ | Registration default is 100 MiB; worker read cap is 16 MiB and normally 100,000 rows. Acceptance at planning does not prove worker support. |
| Not every receipt means completed work | `worker_call: SUCCEEDED` can save a `NEEDS_INPUT` result; inspect `outcome`, tool attempt, step, and final run status. |
| No automatic uncertain-call replay | Current agent annotations disable safe retry; unknown outcomes stop. This protects against duplicate model spending but is not a recovery success score. |
| Trusted local processes | Narrow worker protocol and read-only Codex settings are not a hostile-worker OS sandbox for the entire application. |

Evidence: [Planner.plan (planner.py:88)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/planner.py:88),
[run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40), [Executor._schedule (executor.py:213)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:213),
[Executor._review (executor.py:290)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:290), [agents.yaml:1](C:/Learning/R-Project/configs/agents.yaml:1),
[SYSTEM_PROMPT (model.py:12)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/model.py:12), [validate_plan (graph.py:77)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/graph.py:77),
[WorkerGateway.dispatch (gateway.py:162)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/gateway.py:162),
[serve (server.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/server.py:25), [ToolBroker._perform (broker.py:76)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/broker.py:76),
[start_agents.ps1:1](C:/Learning/R-Project/start_agents.ps1:1).

## 4. Documentation differences found

- The Combining running table and its introductory plan say “join two files.” Current
  code accepts two to eight and sequentially joins all supplied tables under one shared
  key/type/relationship recipe. A three-file probe confirmed this. The later planning
  paragraph already discusses more than two files; the introductory wording is narrower
  than the implementation.
- README's agent validation paragraph still reports its earlier 142-test checkpoint.
  `docs/progress.md` records the later 171-test evaluation checkpoint. Both are historical
  entries; today's fresh result is 171 passed and 1 skipped.
- Some agent-plan text still describes independent evaluation as later work, while the
  development evaluator now exists. The latest evaluation code and progress entry define
  the current state.
- `CommandPlanner`'s docstring says `planner.v1`; the new caller constructs
  `orchestration.v1`. The actual JSON payload is the integration contract to inspect.

Evidence: [Running.md:15](C:/Learning/R-Project/docs/Agents/Running.md:15),
[Data_Combining_Agent.md:6](C:/Learning/R-Project/docs/Agents/Data_Combining_Agent.md:6),
[Data_Combining_Agent.md:94](C:/Learning/R-Project/docs/Agents/Data_Combining_Agent.md:94),
[combine (operations.py:8)](C:/Learning/R-Project/src/mcp_execution_lab/agents/combining/operations.py:8), [probe output](evidence/probes.json),
[README.md:43](C:/Learning/R-Project/README.md:43), [progress.md:3](C:/Learning/R-Project/docs/progress.md:3),
[README.md:290](C:/Learning/R-Project/docs/Agents/README.md:290), [CommandPlanner (planner_clients.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/planner_clients.py:62),
[ModelCalls.ask (model.py:48)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/model.py:48).

This audit adds a current description in this folder. It does not rewrite the historical
design/status documents or quietly change production behavior.

## 5. Fresh validation performed for this audit

The full project check was run from the project `.venv`, with native PostgreSQL and Docker
checks enabled and live Codex checks disabled. Ruff lint and format checks passed for
120 Python files. The test console reported **171 passed, 1 skipped in 368.27 seconds**.
The JUnit suite stores **172 total, 0 failures, 0 errors, 1 skipped**, with its own elapsed
time of **367.050 seconds**. Those elapsed numbers come from different reporting layers.
Evidence: [check.ps1:1](C:/Learning/R-Project/scripts/check.ps1:1),
[fresh raw JUnit XML](evidence/full_checks_2026-10-23.xml),
[verification record](evidence/verification.json).

The skipped case was the explicitly enabled live Codex planner smoke. Test model replies
for workers/evaluation came from deterministic fixtures. Real MCP transports, real worker
processes, native PostgreSQL transactions, handwritten calculations, and Docker controls
were still exercised. No live provider request was made by the new audit probes.
Evidence: [test_bounded_live_codex_planner_with_native_postgres_and_real_mcp (test_postgres.py:77)](C:/Learning/R-Project/tests/orchestration/test_postgres.py:77),
[AgentModel (workers.py:51)](C:/Learning/R-Project/tests/agents/workers.py:51),
[EvalModel (test_integration.py:22)](C:/Learning/R-Project/tests/evaluation/test_integration.py:22),
[audit probes](evidence/probes.py).

Four additional targeted checks ran against actual current functions:

| Probe | Observed result |
|---|---|
| Three-file combining | One joined row retained columns from all three inputs; two join checks. |
| Numeric prose | Bare digits refused; saved fact placeholder accepted; a number in words accepted. |
| Oversized prompt | `PROMPT_SIZE`; one reserved budget call, no saved request, no provider request. |
| Manual grader input set | Required plus extra CSV still allowed a passing constructed answer. |

Evidence: [reproducible script](evidence/probes.py), [saved actual results](evidence/probes.json).
The probe store is explicitly in-memory SQLite for tests, not the user's database.
Its CSV/file scratch evidence remains under `.runtime/cross_check/files`.

## 6. Evidence files and rerun instructions

| File | What it records |
|---|---|
| `evidence/full_checks_2026-10-23.xml` | Fresh test cases, pass/skip/error counts, timings. |
| `evidence/probes.py` and `probes.json` | Small deterministic reproductions and their observed output. |
| `evidence/source_manifest.json` | Source/lock identity, per-file SHA-256, symbol/line map, resolved source citations. |
| `evidence/verification.json` | Check settings, package versions, workspace readiness, final owned-process count, evidence hashes. |
| `evidence/build_evidence.py` | Resolve/check the report's code references and rebuild the source manifest. |

From the project root, these two commands use no real model:

```powershell
.\.venv\Scripts\python.exe docs/Cross-check/evidence/probes.py
.\.venv\Scripts\python.exe docs/Cross-check/evidence/build_evidence.py
```

For a complete check, `scripts/check.ps1` invokes Ruff and Pytest. The audit enabled
`MCP_LAB_POSTGRES_TEST=1`, `MCP_LAB_DOCKER=1`, and disabled `MCP_LAB_CODEX_TEST=0`.
Optional test environment gates are part of the test source. Do not interpret a default
run that skips optional integrations as the same evidence as this enabled run.
Evidence: [check.ps1:1](C:/Learning/R-Project/scripts/check.ps1:1), [test_postgres.py:1](C:/Learning/R-Project/tests/orchestration/test_postgres.py:1),
[test_native_postgres.py:1](C:/Learning/R-Project/tests/agents/test_native_postgres.py:1),
[verification record](evidence/verification.json).

## 7. Present operational state and sensible next work

The final ownership check found **zero owned managed services running**, with saved
service state `STOPPED`. `.env` and a process database URL were absent. A Codex executable
was found, but no live login/model/allowance check was claimed. The production source
and lock hashes still match the snapshot tested by the fresh suite.
Evidence: [verification record](evidence/verification.json),
[probe output](evidence/probes.json), [agent_processes.ps1:32](C:/Learning/R-Project/scripts/agent_processes.ps1:32),
[source_identity (provenance.py:9)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/provenance.py:9).

For the next discussion, the highest-value choices are: define the final four-mode
runtime contract and review semantics, fix the two accounting/input-control gaps before
controlled runs, configure the user's local DB, then make a small bounded live-model
check before collecting research results. Broader datasets and report-quality criteria
should be frozen before comparing modes. These are recommendations from this audit;
none were silently implemented here.
