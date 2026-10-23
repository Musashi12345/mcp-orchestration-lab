# Evaluation: check the answer separately from running the plan

There are two evaluators in this repository. This file describes the **new data-analysis
development evaluator** under `evaluation/`. The retained pricing evaluator is separate.
The new evaluator supports D1/D2 batches, not a completed D1/D2/P1/P2 data-analysis study.
Evidence: [main (cli.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/cli.py:62), [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[evaluate (benchmark.py:30)](C:/Learning/R-Project/src/mcp_execution_lab/benchmark.py:30).

## 1. Three different questions

| Question | Where the answer comes from |
|---|---|
| Did the engineering checks pass? | Pytest, Ruff, genuine MCP/native PostgreSQL/Docker checks. |
| Did this run produce the requested answer? | Post-run independent grader plus any required human review. |
| Which representation performs better? | Many controlled, matched runs with a declared study design. The current tests do not establish this. |

The executor intentionally saves `task_success: null`. The grader adds an independent
`evaluation_result` record. Batch reports keep failed and unresolved attempts visible.
Evidence: [Executor._finalize (executor.py:107)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:107),
[evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160), [report_batch (batch.py:188)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:188).

## 2. Frozen public tasks and private calculations

`Suite` loads `manifest.json` and `tasks.json`. Each public task names input files, query,
task kind, expected output-column names, numeric-column names, tolerance, required chart/
report/change-log flags, and human-review criteria. Loading checks unique task IDs, file
membership, declared numeric columns, and SHA-256 hashes. CSV paths must be direct children
of that suite directory. Evidence: [Task (suite.py:13)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/suite.py:13),
[Suite.__init__ (suite.py:29)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/suite.py:29), [Suite.path (suite.py:46)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/suite.py:46).

The default CLI suite is `fixtures/data_analysis_evals/development`. Public questions
and frozen input hashes are separate from private reference calculations in `answers.py`.
The grader computes answers using its own CSV/Decimal code, not agent operation functions.
The batch passes only the public query and specified CSV paths into `Application.plan()`.
It does not pass the `Suite`, expected answers, or the grader's output to the model.
Evidence: [main (cli.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/cli.py:62), [expected (answers.py:21)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:21),
[forecast_rows (answers.py:97)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:97), [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[test_grader_has_no_import_from_agent_operations (test_grading.py:223)](C:/Learning/R-Project/tests/evaluation/test_grading.py:223).

This separation is a code dependency boundary. It is not an OS sandbox around trusted
host processes, and it does not make these development tasks a hidden test set. I have
not copied private expected values into this walkthrough.
Evidence: [answers.py:1](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:1), [WorkerGateway.dispatch (gateway.py:162)](C:/Learning/R-Project/src/mcp_execution_lab/agents/common/gateway.py:162),
[run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40).

## 3. Admission to grading

`evaluate()` requires a terminal run. It compares the original question exactly with the
task query. Every required input filename must occur exactly once among dataset records
and match its frozen hash. The original disk files are then checked against their saved
references. Active runs or a different question are rejected.
Evidence: [TERMINAL (grading.py:16)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:16),
[evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160),
[test_active_run_and_unrelated_task_cannot_be_graded (test_grading.py:128)](C:/Learning/R-Project/tests/evaluation/test_grading.py:128),
[test_altered_output_and_original_input_fail_integrity (test_grading.py:140)](C:/Learning/R-Project/tests/evaluation/test_grading.py:140).

**Reproduced gap:** manual grading does not reject extra original input CSVs beyond the
task's required filenames. An audit-constructed run containing the required file plus an
extra file could still pass. This matters for equal information across manually graded
runs. The normal batch runner itself constructs exactly `task.files`, so the probe does
not show extra inputs leaking into that normal route.
Evidence: [evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160),
[run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40), [probe and reproduction](evidence/probes.py),
[actual probe result](evidence/probes.json).

## 4. Only declared final outputs count

The collector starts at the final execution result's declared output references, follows
nested JSON references, and validates run ownership, hashes, conflicting references,
file count, depth, and size. It reads returned CSVs and recognized JSON answer/group
tables, records PNGs after checking their signature, and reads Markdown reports. It
does not search every intermediate artifact for a convenient correct answer.
Evidence: [collect (evidence.py:19)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/evidence.py:19),
[test_unreturned_intermediate_answer_does_not_count (test_grading.py:117)](C:/Learning/R-Project/tests/evaluation/test_grading.py:117),
[test_foreign_reference_cannot_be_smuggled_after_valid_reference (test_grading.py:210)](C:/Learning/R-Project/tests/evaluation/test_grading.py:210).

The collector caps reference depth at 16, file count at 128, and individual files at
16 MiB. Original task CSV IDs are excluded as answer-table CSVs. The supported JSON
shapes include `rows`, `answer_rows`, and analysis `details.groups`; this is an explicit
output-format contract, not universal understanding of every possible answer document.
Evidence: [collect (evidence.py:19)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/evidence.py:19).

## 5. Table correctness

The grader finds nonempty candidate tables containing every requested column. Every
candidate must match; a correct table cannot hide another wrong answer-shaped table.
Row order is ignored, but row multiplicity is preserved. String IDs and blanks are
compared as text. Declared numeric columns use finite Decimal comparisons within the
task's absolute tolerance, default `0.005`. Extra columns are not compared.
Evidence: [rows_equal (grading.py:26)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:26),
[table_check (grading.py:59)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:59), [Task (suite.py:13)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/suite.py:13),
[test_row_comparison_preserves_ids_duplicates_blanks_and_tolerance (test_grading.py:79)](C:/Learning/R-Project/tests/evaluation/test_grading.py:79),
[test_wrong_table_cannot_hide_behind_a_correct_table (test_grading.py:106)](C:/Learning/R-Project/tests/evaluation/test_grading.py:106).

The current independent reference calculations cover the specific development cases:
filtered/grouped totals, stated cleaning, stated joins, small selection tasks, and an
explicit last-value forecast exercise. They dispatch on known task IDs. Adding any new
CSV to the folder does **not** create its correct-answer calculation or grading rule.
New tasks need a frozen manifest entry, a public task, independent checks, and tests.
Evidence: [expected (answers.py:21)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:21),
[forecast_rows (answers.py:97)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:97), [evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160).

An empty expected table is not a supported general success case in `table_check()`: it
requires a nonempty candidate. That is a limit to account for before adding empty-result
tasks. Evidence: [table_check (grading.py:59)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:59).

## 6. Forecast, clarification, changes, charts, and reports

| Task feature | Automatic check | Remaining limit |
|---|---|---|
| Forecast | Recompute the explicitly requested last-value output, source-row split, MAE, RMSE, and simple-reference scores. | This is not a general prediction-quality leaderboard for all three agent methods. |
| Clarification | Find a saved Main Task/worker question. | Relevance and necessity need the task's human check; any question alone is weak evidence. |
| Change log | Compare the stated development cleaning case's change rows/values. | Check is specific to this case, not a general audit of arbitrary cleaning rules. |
| Chart | A returned checked PNG exists. | Automatic presence does not prove correct axes, labels, values, or choice of plot. |
| Report | A returned Markdown file contains nonblank text. | Automatic presence does not prove factual support, clarity, or complete coverage. |

Evidence: [evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160),
[forecast_rows (answers.py:97)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/answers.py:97), [collect (evidence.py:19)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/evidence.py:19),
[test_forecast_recomputes_scores_and_checks_time_split (test_grading.py:191)](C:/Learning/R-Project/tests/evaluation/test_grading.py:191),
[test_clarification_requires_a_question_and_a_human_check (test_grading.py:177)](C:/Learning/R-Project/tests/evaluation/test_grading.py:177).

When automatic checks pass and `human_checks` are present, the result becomes
`REVIEW_NEEDED`, with `task_success: null`. `review()` requires a reviewer name and note;
it saves a new linked result rather than replacing the first one. Human review cannot
override a failed automatic check. The current interface records one overall pass/fail
decision and note, not a separate structured score for every criterion or multiple blinded
raters. Evidence: [review (grading.py:381)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:381),
[test_human_review_remains_pending_and_preserves_previous_result (test_grading.py:153)](C:/Learning/R-Project/tests/evaluation/test_grading.py:153).

## 7. Measurements saved for each run

| Measurement | Current definition |
|---|---|
| Model calls | Number of saved `model_call` records, broken down by role. |
| Tokens | Sum only when every call has valid input/output counts; otherwise null plus a known subtotal. |
| Tool attempts | Count and attempt-state breakdown, including unsuccessful attempts. |
| Reviews | Count of decisions/statuses from saved review records. |
| Planning time | Run creation to readiness, or terminal end if planning never became ready. |
| Execution time | First `EXECUTING` event to terminal end. |
| Total time | Run creation to terminal end, including a user's delay before manually executing a saved plan. |
| USD cost | Always unknown (`null`) in this evaluator. |

Evidence: [measurements (grading.py:75)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:75).

The budget's elapsed active time and the evaluator's wall-clock time are not identical:
the former restores used planning time, while the latter includes a manual gap between
planning and execution. The prompt-size accounting gap described in the findings can
also reserve a budget slot without creating a `model_call` record. Do not treat these
different measurements as interchangeable.
Evidence: [Budget.restore (budget.py:60)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/budget.py:60),
[ModelCalls.ask (model.py:48)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/model.py:48),
[measurements (grading.py:75)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:75), [probe output](evidence/probes.json).

## 8. Paired development batches

`run_batch()` builds `(task, repeat)` blocks, shuffles them with a saved seed, and shuffles
mode order inside each block. Runs execute sequentially, each with fresh planning and
without a shared response cache. It accepts D1/D2 only. Both use the same settings, limits,
input files, task question, and review rules; D1 passes the review points without model
review. Evidence: [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[Executor._review (executor.py:290)](C:/Learning/R-Project/src/mcp_execution_lab/orchestration/executor.py:290).

Before a whole block it requires remaining batch call allowance for every mode's full
per-run maximum. It stops rather than reduce a later matched run's limit. Source, lock,
grader, suite, and settings hashes are recorded; source/grader changes stop the batch.
The manifest is saved before work and updated after run creation/usage/results. Runs are
linked to their batch/task/repeat in an `evaluation_episode` record.
Evidence: [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[EpisodeStore (batch.py:25)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:25),
[test_batch_reserves_equal_allowance_for_a_whole_pair (test_integration.py:125)](C:/Learning/R-Project/tests/evaluation/test_integration.py:125).

`report_batch()` writes `summary.json`, `episodes.csv`, and `report.md`. All attempted
runs remain in the denominator. Pending human reviews/evaluation errors remain unresolved.
Paired win counts use only scored pairs and separately count missing/unresolved pairs.
The summary contains generic P-pair names, but this batch runner cannot produce P runs;
empty P-pair entries are not evidence of Python support.
Evidence: [report_batch (batch.py:188)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:188),
[test_wrong_answers_and_failed_episodes_stay_in_batch_reports (test_integration.py:189)](C:/Learning/R-Project/tests/evaluation/test_integration.py:189).

Results are explicitly marked `development`/`exploratory`. There is no automatic batch
resume, independent test-set holdout mechanism, confidence interval computation, general
service-failure injection score, or full four-mode analysis in this new evaluator.
These are study work still to do, not claims established by passing unit tests.
Evidence: [run_batch (batch.py:40)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:40),
[report_batch (batch.py:188)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/batch.py:188), [evaluate (grading.py:160)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/grading.py:160).

## 9. Commands and current verification

These CLI shapes come from the parser. `run` uses the configured real model and can spend
allowance; the audit did not run that command with a real provider.

```powershell
.\scripts\lab.ps1 eval list
.\scripts\lab.ps1 eval grade --run RUN_ID --task TASK_ID
.\scripts\lab.ps1 eval review --run RUN_ID --evaluation EVALUATION_ID --decision pass --reviewer NAME --note "Reason"
.\scripts\lab.ps1 eval run --config configs/agents.yaml --modes D1 D2 --repeats 1 --seed 0 --max-model-calls TOTAL
.\scripts\lab.ps1 eval report --directory PATH_TO_BATCH
```

Evidence: [main (cli.py:62)](C:/Learning/R-Project/src/mcp_execution_lab/evaluation/cli.py:62), [main (cli.py:206)](C:/Learning/R-Project/src/mcp_execution_lab/cli.py:206).

Fresh tests covered independent grading, altered files, output-only grading, numeric
rules, reviews, forecast splits, paired allowance, retained failures, unknown token usage,
cancellation, native PostgreSQL records, and genuine MCP calls. Model replies were fixed
fixtures, so no representation winner is claimed.
Evidence: [test_native_postgres_saves_run_linked_evaluation_and_pair_reports (test_integration.py:115)](C:/Learning/R-Project/tests/evaluation/test_integration.py:115),
[test_planning_failures_are_retained_and_tokens_stay_unknown (test_integration.py:321)](C:/Learning/R-Project/tests/evaluation/test_integration.py:321),
[test_cancellation_preserves_started_run_and_consumed_request (test_integration.py:350)](C:/Learning/R-Project/tests/evaluation/test_integration.py:350),
[fresh full-suite XML](evidence/full_checks_2026-10-23.xml).

Read next: [storage and the model route](05_Storage_And_Model_Route.md).
