# Implementation progress

## Repository cleanup before commit: 2026-10-27

Removed six superseded pricing-pilot guides and a report-specific Q01 wrapper from the
source tree after verifying local archive copies. The reusable batch queue, build plans,
original research guide and dated source audit remain. The README is shorter, the current
source map now includes P2, and a [public results summary](evaluation/Results.md) records
the three-question comparison without publishing private CSVs or raw run records.

Application source and the dependency lock are unchanged. All 11,597 inventoried evidence
files remained unchanged. Commit candidates contained no local password values or common
secret-key patterns; local credentials, input CSVs and generated evidence remain ignored.
Ruff and formatting passed. The normal check had 308 passes and 59 optional skips; its
service test failed because existing managed services used different ports. That test
passed unchanged on a separate run with the services stopped, giving 309 distinct passing
cases. The managed services were then restored with their prior HTTP experiment settings.
No live model, Docker or native PostgreSQL test was submitted for this cleanup.

## Q01 batch completed and current-results insights: 2026-10-27

The four current-settings Q01 attempts passed and the batch automatically refreshed
the comparison report. All twelve latest Q01/Q05/Q10 results now pass on the same
source/configuration/suite/checker. Eleven of twelve first attempts passed; Q05 D2's
failed attempt and successful retry remain counted. The main view uses thirteen
attempts and 89 calls, with 1,876,748 fully reported tokens. All 34 historical attempts
and 175 calls remain retained, including eight older calls with unavailable usage.

A direct read-only PostgreSQL check confirmed the thirteen included attempts and
the unchanged 34-run evidence hash from the automatic audit. D1/P1 differ by only
594 tokens (0.15%) across the three tasks. D2/P2 use 37.6%/34.1% more tokens than
their corresponding modes without reviews. All eight current reviews chose KEEP;
six happened after all original jobs finished and used 204,934 tokens. There were
no accepted revisions. Planning used 67.4% of current tokens, and model-spacing waits
occupied 84.5% of recorded run time. Only Analysis, Cleaning and Prediction were used.

The automatic report's 144 file-hash checks, 175 provider request/usage checks and
thirteen in-memory current-version grades passed. Findings, review snapshots and
context-size exports are linked from the [insights report](../reports/comparison_2026-10-27/Insights.md).
No application source, prompts, run limits, review placement, inputs or original grades
were changed by this analysis, and no new application model call was submitted.

## User-approved Q01 current-settings batch: 2026-10-27

The user requested four fresh Q01 attempts under current settings and replacement of
the main comparison's Q01 results whatever their outcomes. The existing 300,000-token,
32-call, 90-second-gap, 30-minute and review controls remain unchanged. Old Q01 runs
choose wait times only and will move to the report history. The Q05 D2 retry and both
of its attempts' costs remain included. No application source or grading rule changed.

The host helper now allows fresh Q01 with timing-only baselines and refreshes readable
state during a run. Thirty fixed queue checks passed. Six fixed follow-up checks covered
all-pass, all-fail and mixed report outcomes, missing token counts, unchanged Q05 D2
costs, failure-aware automatic report refresh and helper hash checks. No model was used
in those checks. The earlier comparison's 22 files were copied and hash-verified before
changing report helpers. The background workflow will audit and stage updated report
files after the batch, then replace the Markdown entry point last. Its saved state and
tracking files are under `reports/q01_current_batch_2026-10-27/`.

## Saved three-question comparison: 2026-10-27

The user approved comparing Q01, Q05 and Q10, including the separate Q05 D2 retry
with its failed attempt and combined time/token use visible. The latest Q05 and Q10
answers pass in every mode; Q05 D2 passed on attempt two with the same source/settings.
Seven of eight first attempts on this repaired source passed. Q01's four latest older
attempts calculated the correct total but did not deliver complete final answers.
Its earlier source and 120,000-token guard are kept separate from the current 300,000
settings; original grades remain retained.

A read-only audit found 30 live attempts, 149 model calls and 119 registered files.
The existing evaluator reproduced all nine latest-source grades in memory: eight passes
and the retained Q05 D2 failure. It made no application model calls or database writes.
Saved requests, available provider usage, file hashes, links, event sequences and all
saved measurements matched. PostgreSQL evidence hashes were unchanged before/after.
The main report has twelve question/mode results backed by thirteen attempts, with
seventeen older attempts in a separate history table and complete per-call exports.
See [comparison report](../reports/comparison_2026-10-27/Report.md).

D1/P1 used similar tokens on the current two questions. D2/P2 added review calls; all
six completed current-path reviews chose KEEP, so this comparison does not demonstrate
revision or recovery benefits. Most elapsed time was saved model-spacing waits. No
application source, settings, original inputs, grades or retained attempts were changed.

## User-approved fresh Q05/Q10 batch: 2026-10-27

The user authorized eight fresh attempts: Q05 and Q10 each in D1/D2/P1/P2, once, on the
tested Q05 source `bf965b2f11eb8f662a6a2839d7a936f2c27c48b41abfce747ac4deecfa881c3b`.
The shared configuration keeps 300,000 observed tokens, 32 calls, 90-second spacing,
30 minutes and the existing review points, with a 256-call ceiling over the new runs.
Earlier attempts remain separate; Q01 timings choose checks only, with no Q01 results or
tokens included. The known Main Task missing-tool context remains a limitation of this
source and is not silently repaired during the experiment.

The host helper now supports explicit timing-only baselines while retaining strict
identity checks for actual result reuse. All 28 helper tests passed, including complete
eight-run failure continuation, unchanged spacing, no overlap and unknown token counts.
Application source, grader and run settings were not changed for this helper adjustment.
Native PostgreSQL, Docker, CLI login and competing-run checks passed. Frozen plans,
automatic progress and original per-run reports are under
[fresh batch](../reports/q05_q10_retest_2026-10-27/README.md).

## Q05 rule-passing and amount parsing fix: 2026-10-27

The user approved keeping Q05 and fixing missing cleaning arguments and comma amounts.
Shared planning instructions now distinguish written jobs from required tool arguments.
DAG errors name missing fields. Python planning checks statically known arguments against
the discovered tool schema before acceptance, using the existing bounded correction step.
Generated code is inspected as syntax, never executed on the host. Data-dependent values
remain checked by the shared broker; no tool preferences or agent order were added.

Explicit Cleaning numeric conversion and the independent Q05 reference both accept
three-digit comma groups with a period decimal point, using separate implementations.
Malformed grouping is rejected. Original inputs, question text, suite manifest and old
grades remain retained. The Docker SDK and shared limits are unchanged.

Focused verification passed **107 tests in 233.28 seconds**, including deliberate omitted
rules corrected before execution in all four modes. The actual local Q05 CSV passed all
five grading checks in D1/D2/P1/P2 using fixed replies, real MCP, temporary native
PostgreSQL and real Docker for Python. This is engineering evidence, not live model
success. Full-project validation then passed Ruff/formatting for 128 files and **360
tests passed, one live-model test skipped in 1007.03 seconds**, with real Docker, MCP,
native PostgreSQL and local Input checks enabled. All 8,408 inventoried prior evidence
files and all twelve prior PostgreSQL runs were unchanged. Final results are retained under
[Q05 verification](../reports/q05_fix_2026-10-27/README.md). See
[implementation details](evaluation/Q05_Repair_2026-10-27.md).
The managed services were restarted on the prior HTTP experiment configuration; a
separate readiness/discovery check confirmed all seven services READY and all six tools
running the new source. No live model call was submitted.

## Finished Q10 P2 and results audit: 2026-10-27

The separately approved repaired `input_q10` P2 attempt completed and passed all five
saved checks. Independent CSV/date/Decimal calculations also matched all 44 output rows,
the 144/37 training/test split, and both error scores. Native PostgreSQL records, saved
requests and provider usage, file hashes, parent links and Docker cleanup evidence agree.
The run used seven model calls and 157,164 reported tokens in 619.36 seconds; recorded
waiting occupied 86.18% of that time. Its single review chose KEEP, so this result does
not demonstrate live program revision or recovery.

The selected collection now contains twelve attempts: eleven earlier failures and this
one pass. Source, token guard and grader identities differ for the repaired attempt, so
there is no fair mode ranking. All failed attempts remain retained. Analysis also found
the current Q05 reference cannot parse three comma-grouped amounts, Main Task receives
no discovered tool cache before it can ask for clarification, and explanation failures
can prevent publication of already checked numeric results. No runtime or grading change
was made during this audit, and no new application model call was submitted.

The detailed local report, per-call and per-run tables, independent calculations, raw
database export and file audit are under
[results analysis](../reports/analysis_2026-10-27/Report.md). Detailed input-derived values
remain in the ignored reports directory.

## User-approved stop and repairs: 2026-10-27

The user chose to end the automatic batch after its current evaluator exited and raise
the shared future-run token guard from 120,000 to 300,000. The verified helper was
stopped before the last Q10 P2 attempt. Seven new attempts and all original evidence
remain retained. Two unindexed runs were recovered from native PostgreSQL/manifests;
all 34 model calls from started new attempts are now included in the collection.

Cleaning now requires explicit rules in its MCP schema, rejects empty rules before a
worker model call, and supports case-insensitive matching to supplied permitted labels
with unexpected-label rejection. No column, agent preference or sequence is fixed in
production. Python generation/review explains JSON escaping while retaining strict
validation and the existing single correction allowance. Mutable status JSON uses
unique temporary names and bounded Windows file-sharing retries; permanent failures
retain evidence. The queue accounts for run IDs and tokens even when a final manifest
save fails. Budget errors now distinguish token exhaustion from elapsed time.

New stdio and managed-HTTP configurations under `configs/experiments/` provide the same
300,000-token guard, 90-second gap, model and existing call/time/review limits. Earlier
configs and results remain unchanged. Application source is
`5ce9fd361877fa607dd1f14b30c060db424ef274eca61249101f122b98c74ecf`; the lock and
Docker SDK identities are unchanged. See [repairs](evaluation/Repairs_2026-10-27.md).

Fixed-reply Q05 cleaning/analysis passed independent grading through real MCP in all
four modes, including actual Docker for P1/P2. Validation logs are retained under
`reports/repair_2026-10-27/`. The full check and service-readiness completion are
reported there. No repaired live run has been submitted.

The complete check subsequently verified **324 distinct non-live cases**: 323 passed
in the full run, one service-port setup failure passed unchanged on rerun, and one
live-model test stayed skipped. The service processes were restarted on the new HTTP
configuration. The user then separately authorized one fresh `input_q10` P2 attempt
on the repaired source/configuration, using the owned-stdio MCP configuration. Its
approval, automatic status and original reports are under
`reports/q10_p2_repaired_2026-10-27/`. It is not merged into the old comparison cohort.

## Approved small automatic queue: 2026-10-26

The user selected Q01/orders, Q05/messy orders and Q10/daily sales, each in D1/D2/P1/P2.
The four finished 90-second Q01 attempts are retained and verified in native PostgreSQL;
only eight new attempts are scheduled. No answer/grade interpretation was requested.

Added `scripts/evaluation_queue.py` and `start_evaluation.ps1`. The helper launches the
existing evaluator CLI sequentially, waits Q01's observed mode duration plus 120 seconds,
then checks process exit and saved terminal status every 60 seconds. It records each
failure and continues without retries, as chosen by the user. The 90-second gap also
applies between evaluator processes. Existing per-run limits and application source
hash `6999605becfbe6c0196ca451a18de08140ad142385fdad0a888753ce5722ac25` are unchanged.

All **37 focused checks passed**, including real child-process waiting, all-eight-fail
queue continuation, lock/hash/identity controls, unknown token accounting, real MCP,
Docker and temporary native PostgreSQL. Ruff and formatting passed for 124 Python
files. One existing pytest-cache permission warning remains. An older timing assertion
was corrected to measure the full between-call gap rather than sleep duration alone;
no model pacing implementation changed. Initial failed test attempts remain retained.

The queue freezes selection/order, helper and evidence hashes. It labels Q01 reused
and links separate original batches rather than claiming a new matched twelve-run
batch. The approved new-call ceiling is the eight unchanged per-run allowances,
8 x 32 = 256 calls. Progress and original child reports are saved under
`reports/small_input_queue_2026-10-26/`. See
[the queue guide](evaluation/Small_Automatic_Batch.md) for controls and commands.

## P1 storage confirmed; user-approved P2 next: 2026-10-26

P1 finished, and read-only PostgreSQL queries confirmed run
`run_359c4e528ccb46b7831edbf923cd406f`: its program, Docker/runtime records, six model
calls with token fields, five waits, execution/evaluation records, 78 events and 34
record links are saved. Its answers, grade and token use were not analyzed.

The user approved one new Q01 P2 episode using the exact same source, configuration,
model, CSVs, 90-second spacing, limits and Docker image. P2 makes a fresh program and
uses the existing review rules. Readiness and launcher syntax checks passed, and prior
D1/D2/P1 evidence hashes are retained. No application source or run limit was changed.
The background helper lets this chat become idle and saves its own automatic status.
See [P2 setup and status](../reports/p2_q01_gap90_2026-10-26/README.md).

## D2 storage confirmed; user-approved P1 next: 2026-10-26

Read-only PostgreSQL queries confirmed D2 run
`run_7cf36892885342b6903ef64d1737b869`: one run row, its plan, six model calls with
token fields, five wait records, execution/evaluation records, 71 events and 28 record
links. Its answer, grade and token use were not analyzed.

The user approved one new Q01 P1 episode with D1/D2's exact source, configuration,
frozen files, model, 90-second gap and existing budgets. Docker and the unchanged SDK
image passed readiness checks; no application code or limit was changed. The background
helper delays launch so this chat can become idle and saves its automatic state in
`status.json`. Prior D1/D2 evidence remains retained. See
[P1 setup and status](../reports/p1_q01_gap90_2026-10-26/README.md).

## User-approved D2 with the same 90-second spacing: 2026-10-26

After confirming D1's PostgreSQL records without analyzing its results, the user
approved one new Q01 D2 episode in the same way. It reuses D1's exact configuration,
verified source and frozen inputs: `gpt-6.1-sol`, low reasoning, 90-second model gap,
32-call ceiling, 120,000 observed tokens and 30 minutes. D2 makes its own fresh DAG
and uses the two existing review opportunities. No application source or run limit
was changed for this step, and no D1 result analysis was performed.

The background launcher waits one minute so this chat can become idle, then saves
normal run/evaluation/token records to PostgreSQL and disk. Its automatic status is
the authority for launch/completion state. D1's saved batch/status hashes are retained
for an unchanged-evidence check. See
[D2 setup and status](../reports/d2_q01_gap90_2026-10-26/README.md).

## User-approved 90-second model spacing: 2026-10-26

Added optional `model.request_gap_seconds`, default zero, and a separate diagnostic
configuration setting it to 90 seconds for one fresh Q01 D1 run. The host shares a
spacing gate across initial planning, worker and review calls; saved finish times
also preserve the gap when components are recreated for the same run. Waits are saved
as `model_wait`, use existing run/tool time limits, and are outside the reply timeout.
Model prompts, tool choice/order, calculations, grading and provider retries are unchanged.

Ruff/formatting passed for 122 Python files. **76 distinct focused checks were verified**
with fixed replies, real MCP and native PostgreSQL. The final check passed 75 cases;
one existing paired-case manifest replacement hit Windows access denied, then passed
unchanged in a fresh directory. All final pacing cases passed, including 90-second
virtual timing, concurrent calls, failed calls, cancellation, saved finish times,
run limits, reply timeout separation and real MCP worker/review spacing. Earlier test
attempts and the existing pytest cache permission warning are retained. A full suite
was not rerun for this change.

The approved single live diagnostic uses the background helper so this chat can be
idle. It does not introduce a new retry batch or change the regular service configs.
Read its automatically updated `status.json` for launch/outcome state. See
[the test record](../reports/d1_q01_gap90_2026-10-26/README.md).

## Single D1 diagnostic with this chat idle: 2026-10-26

The user approved one unchanged Q01 D1 run without active assistant monitoring. A
background helper delayed launch by one minute so the launch turn could end. Batch
`eval_batch_ff8f1e961d1c476f9f4900192c53d36e` finished with a failed episode: all four
planning calls succeeded, then the Analysis recipe call received HTTP 429. Docker
was unused. Five call records include 100,601 known planning tokens and one failed
call with unknown usage. Source/config/input identities matched the verified repair;
earlier batch files are unchanged. No further live run or pacing change was made.

The result shows active assistant monitoring and Docker are not required for the
error to occur. The exact provider limit is still unknown; earlier shared account
usage and other activity are not ruled out. See
[the diagnostic and evidence](../reports/idle_d1_q01_2026-10-26/README.md).

## Planner information repair and approved restart: 2026-10-26

The user approved the proposed repair and restart. Every initial planning stage now
receives a neutral host contract describing the mode, scheduling, MCP access, storage
and engine-owned reviews. Planning instructions keep mandatory constraints grounded in
the request/task rules. The Analysis MCP definition now states its implemented Decimal
internal arithmetic, numeric export limit, and saved table/evidence behavior. Actual
missing-capability stops and model-decided agent choice/order remain in place.

`scripts/check.ps1` passed Ruff/formatting and **269 tests with one live-test skip** in
735.53 seconds, using fixed replies, real Docker/MCP and temporary native PostgreSQL.
One existing pytest cache permission warning remains. The orchestrator and all six
agents restarted on the repaired source. The approved Q01 four-mode batch
`eval_batch_65c589770f1f4c8eb3bd3016f429174e` finished with four failed grades. P1
passed planning, ran Python in Docker, and saved the correct internal calculation;
its explanation call received HTTP 429 before final table publication. D1/D2/P2
received HTTP 429 on Main Task creation. Nine calls saved 111,100 known tokens with
four unknown-usage calls, so the complete total is unknown. The model/limits/suite
and 128-call ceiling were unchanged. The earlier failed batch's files are unchanged,
all seven services remain healthy, and no lab containers remain. No provider retry
policy or additional batch was introduced. See
[repair and live findings](evaluation/Planner_Repair_and_Restart_2026-10-26.md).

## First live Q01 pilot: 2026-10-26

The user approved Q01 once in all four modes, with current settings and a total ceiling
of 128 calls. The local PostgreSQL login was verified, the dedicated `mcp_execution_lab`
database was created with approval, and the connection was saved in ignored `.env`.

Batch `eval_batch_fbc3ded9f2f242ec997148a93ab27934` completed with **four failed runs,
seven real model-call records and no tool execution**. D1/P1 found the Analysis agent
but stopped on missing-capability claims about host reviews and calculation guarantees.
D2/P2 received HTTP 429 from Codex. Five calls reported 89,352 known tokens; two calls
have unavailable usage, so the complete total stays unknown. All attempts are retained.

Source/configuration/input hashes match approval. No source was changed to affect these
results, and no additional live batch was submitted. A neutral planner-context and MCP
description repair is proposed for the user's choice. See
[pilot findings and proposal](evaluation/First_Live_Pilot_2026-10-26.md).

## Docker verification completed: 2026-10-26

After the user started Docker, the existing CSV image passed its SDK hash check. The
previously skipped execution/review/evaluation checks passed **43 tests**, and P1/P2
API checks passed **2 tests**. Real Docker, official MCP processes, and temporary native
PostgreSQL were used with fixed replies. The matched four-mode case verified token
records and phase totals, plus P2 saved-result reuse across two containers.

Source/lock hashes match the earlier 218-test full check: **263 non-live cases verified
across the initial full check and Docker completion**. The live-model case remains
unrun. Docker was responding afterwards and zero lab containers remained. All Input
hashes still match. No actual Input comparison or live provider call was started.
See [Docker results](../reports/evaluation_docker_2026-10-26/README.md).

## Approved Input evaluation and token records: 2026-10-26

Added a separate suite for the ten local `Input/` CSVs, with the user's 14 approved
questions and frozen hashes. The suite accepts an explicit CSV directory; raw files
remain local and ignored by Git. All modes make fresh plans from the same question
and declared files. No actual Input comparison or live provider request was started.

Independent checks now cover the approved filters, totals, exact counts/IDs, joins,
cleaned CSV and complete change log, seven-observation held-back forecast, and three
independent totals. Q04/Q12/Q14 retain human review. The user chose source-row IDs for
Q10, so the Prediction agent is unchanged. Manual grading rejects extra original CSVs;
generated CSV origins and older parent links keep generated files separate from inputs.

Every saved model call now retains raw usage, checked input/output and optional
cached/reasoning counts, phase, and finish time. Failed/correction attempts remain
included. Missing counts stay unknown; known partial counts still limit the shared
budget. Reports add per-call and per-mode/phase CSVs plus agent groups in JSON.
No dollar estimate is introduced. The older oversized-prompt reservation behavior is
unchanged pending the user's separate counting decision.

`scripts/check.ps1` passed Ruff and formatting for 119 Python files, then **218 tests
passed, 46 skipped in 316.64 seconds**. Fixed replies, real MCP processes, and separate
temporary native PostgreSQL were enabled. Docker was unavailable on this VM, so Docker
checks were disabled; live model checks were explicitly disabled. Pytest reported one
cache-write permission warning. All ten local CSV hashes were checked after the build.
See [retained validation](../reports/evaluation_input_2026-10-26/README.md) and
[evaluation use](evaluation/Running.md).

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
[agent evidence](../reports/agents_validation/README.md), and the
[dated pre-cleanup audit](Cross-check/2026-10-23-before-cleanup/README.md).
Superseded pricing-pilot guides are archived locally with the 2026-10-27 repository cleanup.
