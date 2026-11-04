# Data-analysis evaluation

Updated: 2026-10-26. This is a development collection, not the final unseen research test.

The ten CSVs under local `Input/` have a separate suite of 14 approved questions. See
[the approved question plan](Input_Questions_Draft.md). The commands below still select
the older development collection unless the Input suite is supplied explicitly.

## Approved local Input suite

After the original small batch, the user approved a 300,000-token per-run guard in
`configs/experiments/csv_gap90_300k.yaml`. It keeps the previous model, model-call limit,
90-second gap, run/tool time limits and reviews. It is a new configuration identity;
old attempts are not relabeled. See [repairs](Repairs_2026-10-27.md).

The questions and input hashes are versioned under `fixtures/data_analysis_evals/input_v1/`.
The CSVs remain in `C:\Learning\R-Project\Input`, ignored by Git. The suite requires an
explicit CSV directory; it does not silently copy or substitute the development files.

```powershell
.\scripts\lab.ps1 eval --suite fixtures/data_analysis_evals/input_v1 --input-directory Input list
.\scripts\lab.ps1 eval --suite fixtures/data_analysis_evals/input_v1 --input-directory Input grade --run RUN_ID --task input_q01
```

Listing makes no database/model request. Grading uses the saved run and makes no model
request. Inputs must match the frozen file hashes and the exact question; extra original
CSVs are rejected. Generated CSVs have a host-saved origin marker and do not count as
extra inputs. Older worker outputs are also recognized through their saved parent links;
unmarked older CSVs without those links are treated conservatively as originals.

Q01–Q09 cover filters, sums/counts, joins, cleaning, payments, refunds, targets and stock.
Q10 checks an 80/20 time split and a last-value forecast for seven future observations,
using source-row IDs (the user chose to leave the Prediction agent unchanged). Q11
checks notes treated as data; Q12 asks for missing profit inputs; Q13 requires three
independent totals; Q14 adds a report. Q04, Q12 and Q14 require human review.

The reference calculations use Decimal arithmetic and do not import worker operations.
Q05 checks the regional answer, actual cleaned CSV, every changed cell and every removed
source row, calculated from these inputs rather than older fixture row numbers. Counts
and stock values must match exactly; money allows 0.005 INR. Forecast predictions must
match exactly, error scores allow 0.000001, and future actuals must be blank.

The approved plan defines cleaning normalization before row removal. A change log must
include cell edits even on rows later removed. The exact query states the saved table
columns and log fields so all four modes receive the same requirements.

The first live Q01 pilot attempted all four modes once and failed before execution;
see [the findings](First_Live_Pilot_2026-10-26.md). The approved repair and second batch
reached P1's correct internal calculation, but HTTP 429 prevented final publication and
the other modes' planning. See [the restart record](Planner_Repair_and_Restart_2026-10-26.md).
No complete live worker answer has been verified.
Choose settings and a request ceiling before any further batch. Supply `--modes D1 D2
P1 P2` explicitly for all four; the CLI's older D1/D2 defaults are unchanged.

## Optional gap between model calls

For the user-approved smaller Q01/Q05/Q10 experiment, see
[the automatic queue guide](Small_Automatic_Batch.md). It preserves the original Q01
attempts and launches Q05/Q10 in all four modes sequentially. Its file-check waits and
90-second between-run gap are outside individual run timing; within-run spacing is
still provided by `model.request_gap_seconds`.

`model.request_gap_seconds` defaults to zero. A positive value spaces model calls after
the previous call finishes, across planning, selected agents and reviews within the
application instance/run. The wait is saved as `model_wait`, counts toward the existing
run/tool time limits, and does not consume the model's reply timeout or another call.
Separate app processes and other Codex chats do not share this gate.

The user approved one Q01 D1 diagnostic with 90 seconds in
`configs/diagnostics/d1_q01_gap90.yaml`; regular service configs remain unchanged.
See [the diagnostic record](../../reports/d1_q01_gap90_2026-10-26/README.md).
This is separate from a matched four-mode evaluation. Any eventual comparison needs
the same gap rule in every mode. No new automatic provider retries are included.

## CSV contents

Ten small synthetic CSVs are saved under `fixtures/data_analysis_evals/development/`.
There is one header row and one record per row. Dates use `YYYY-MM-DD`, amounts use INR,
missing values are empty fields, and IDs retain leading zeros as text.

| File | Rows | Columns | Purpose |
|---|---:|---|---|
| `orders.csv` | 24 | order_id, order_date, customer_id, product_id, region, status, amount_inr | Totals, filters, grouping, and joins. |
| `customers.csv` | 8 | customer_id, customer_name, segment | Customer matching. One order deliberately has no customer match. |
| `products.csv` | 4 | product_id, product_name, category | Product matching. |
| `returns.csv` | 5 | return_id, order_id, status, refund_inr | Approved/refused rows, repeated order IDs, and unmatched/blank IDs. |
| `payments.csv` | 6 | payment_id, order_id, status, amount_inr | Captured/pending/failed payments, including legitimate multiple payments. |
| `monthly_targets.csv` | 6 | month, region, target_inr | Grouping and adding across months. |
| `daily_sales.csv` | 40 | date, units_sold | Total units and a simple time-ordered forecast check. |
| `stock.csv` | 6 | product_id, warehouse, available_units | Strict boundary checks and a real zero. |
| `orders_messy.csv` | 10 | Same as Orders | Spaces, inconsistent labels, two exact duplicates, a missing amount, and a missing ID. |
| `orders_with_notes.csv` | 8 | Same as Orders plus notes | A note asks for an invented answer; the task requires treating it as data. |

All names and figures are invented. `manifest.json` saves file hashes, columns, and row
counts. Editing a CSV invalidates its frozen identity. Create a new version and update
its task/reference rules deliberately before using different data. Import identifier
columns as text if using a spreadsheet editor; a numeric conversion would remove zeros.

The authoring tool checked all values against the input matrices and rendered previews.
CSV contents and leading zeros were also checked with the project's parser. No extra
Excel workbook is required for these software test inputs.

## Questions and scoring

`tasks.json` contains fifteen public questions and their output requirements. It names
no required agent or agent order. The tasks cover total sales, regional sales, a chart,
a report, explicit cleaning, two joins, refunds, payments, targets, low stock, daily
units, a simple forecast, missing profit information, and misleading notes.

An ordinary numeric task must return its requested result columns in a saved CSV or
structured JSON table. Extra columns are allowed. Row order is ignored; duplicates and
text IDs matter. Most money comparisons allow an absolute difference of 0.005 INR.
Counts must match exactly. Forecast values/errors allow the stated small rounding tolerance.

The host-only grader calculates expected answers independently using standard Python
and decimal arithmetic. It imports no worker calculation functions. Expected values are
not present in the public task file or passed to models. Grading runs only after a run
ends, and reads only declared final outputs and their checked file references. A correct
intermediate result that was never returned does not earn a pass. Conflicting returned
answer tables fail the check.

The evaluator records individual checks, rather than giving a weighted overall score:

- Correct answer rows and values, including duplicates, blanks, and exact text IDs.
- Original input and returned file identity, ownership, and unchanged content.
- Required cleaned data and cell/row change log.
- Required PNG/report presence. Chart values/labels and report claims need human review.
- For the specified forecast: chronological 80/20 split, exact held-back predictions,
  blank future actuals, recalculated errors, and reference scores.
- For missing profit information: a saved clarification question followed by human
  confirmation that it asks for the actual missing information and invents no profit.

The forecast task deliberately requests a simple last-observation method. It checks
execution and scoring, not which prediction algorithm is best. Broader method-independent
prediction-quality tasks remain future work.

Results are `PASSED`, `FAILED`, or `REVIEW_NEEDED`. `task_success` is null until a required
human check is complete. A human cannot override a failed automatic check. The original
execution result remains unchanged; the separate `evaluation_result` record is the grade.
Every grade is linked to the same run, its execution/input records, task, suite version,
fixture hashes, and grader source hash. Regrading/review appends a record and preserves history.

## List tasks without model calls

From the project directory:

```powershell
.\scripts\lab.ps1 eval list
```

This needs neither PostgreSQL credentials nor model access. Read the exact public query
from the selected task. An existing run can be graded only if it received that exact
query and the frozen CSVs for that task.

```powershell
.\scripts\lab.ps1 eval grade --run RUN_ID --task sales_total
```

Grading requires the existing native PostgreSQL connection and file root in `.env`,
but makes no model call. It refuses active runs or mismatched questions/data.

## Run a fresh comparison

The following command **uses the configured model**. No live evaluation was run during
this implementation. Review the model/settings and ceiling before running it:

```powershell
.\scripts\lab.ps1 eval run --config configs/agents_stdio.yaml --task sales_total --modes D1 D2 --repeats 1 --seed 7 --max-model-calls 64
```

It creates two fresh runs with the same question, data, settings, worker versions, and
per-run limits. Their order is shuffled with the saved seed. Each task/repeat is one
matched block. Repeating `--task` selects several tasks; omitting it selects all fifteen.
`--repeats` controls fresh repetitions. Two task review opportunities must be configured
for D2; the same configuration is used for D1, where no main review model request occurs.

The batch checks that its remaining request ceiling can cover the full worst-case
allowance of the next block before starting it. For two modes with 32 requests per run,
that means room for 64 requests. Actual requests spent count toward the batch total,
including worker, correction, failed, and review requests. Later runs do not receive
smaller per-run limits merely because the batch ceiling is nearly exhausted.

Each run and its batch/task/repeat identity are saved before model work. Queued entries,
failures, uncertain work, and evaluation errors remain visible. Source/lock changes stop
new work. There is no automatic resume or cross-run model-response cache. If a process
is killed, inspect the retained records; incomplete runs are not silently replayed.

The CSV execution path supports D1/D2/P1/P2 through the same tool runtime. To include Python,
build the CSV image first with `analysis runner-build --config configs/agents_stdio.yaml`
and pass `--modes D1 D2 P1 P2` explicitly. P1/P2 run saved Python in Docker;
the same independent checks grade their declared outputs. P2 uses D2's review rules
and starts a fresh runner for accepted revisions, reusing checked saved results.
For the configured ceiling of 32 model requests per run, one four-mode block requires
room for 128 requests:

```powershell
.\scripts\lab.ps1 eval run --config configs/agents_stdio.yaml --task sales_total --modes D1 D2 P1 P2 --repeats 1 --seed 7 --max-model-calls 128
```

D2/P2 require the same two configured review rules. Both preserve unresolved failures
across revisions until a declared recovery step succeeds. Defaults still select D1/D2.
No Python score is manufactured from a DAG run. Fixed-reply integration batches are
exploratory software checks, including the native PostgreSQL four-mode test.

## Review and reports

The batch returns its new directory under `reports/evaluation_batches/`:

- `manifest.json`: frozen settings, hashes, seed, schedule, run IDs, allowance, and states.
- `episodes.csv`: one row per scheduled episode, including failed or unresolved work.
- `summary.json`: per-mode counts, resource totals, and matched pass/fail counts.
- `model_calls.csv`: one row per saved model call, with run/task/repeat/mode IDs, provider,
  model, role, stage, agent, status, parent record, times, and reported token counts.
- `tokens_by_mode.csv`: total and planning/agent/review token use for each started mode.
- `report.md`: a short readable summary.

Run-linked evaluation records and detailed calls remain in PostgreSQL; data/output files
remain under the configured file root. Back up both with the batch report directory.

For a result needing review, inspect the saved question, final files, and calculation
evidence, then record your decision and explanation:

```powershell
.\scripts\lab.ps1 eval review --run RUN_ID --evaluation EVALUATION_ID --decision pass --reviewer "Samarthya" --note "Checked the displayed values, labels, units, and source links."
.\scripts\lab.ps1 eval report --directory reports/evaluation_batches/EVAL_BATCH_ID
```

Use a note that describes the checks you actually performed. The example is not a
pre-approved verdict. Review preserves earlier records and the report refresh uses the
latest grade matching that batch's task, suite, and grader version. Review is currently
manual through the CLI; a blinded review interface is not built.

Measurements include main/worker model request counts, known/unknown tokens, tool
attempts and their states, review decisions, planning time, execution time, and total
wall time. Subscription dollar cost stays unknown. Total wall time includes any gap
between separately requested planning and execution; automated batches avoid that gap.

### Token accounting

`ModelCalls` saves a `RUNNING` call record before invoking the provider and saves the
outcome, finish time, raw usage, and checked counts when it ends. These fields live in the
existing run-linked PostgreSQL records; no new table migration is needed. Normal counts
are non-negative integers. A missing, negative, boolean, or non-integer count is unknown.
No count is estimated from text length. Timeout, cancellation, or service failure without
reported usage remains unknown. A format failure with reported usage still counts those
tokens. Every correction request is its own saved call and contributes separately.

Each mode makes a fresh plan, so reports compare the whole system: initial planning,
agent recipe/explanation calls, and D2/P2 reviews. Optional agent choices can change the
number of worker calls. No selected job list is shared between the modes. The manifest
saves this comparison scope and the fresh-plan policy.

Total tokens are input plus output. Optional `cached_input_tokens` and
`reasoning_output_tokens` are subset counts, not extra tokens. The Codex bridge keeps
the raw `turn.completed.usage` fields described in the
[official JSON output documentation](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable).
Trusted command routers must return the same flat field names; provider-specific nested
fields are retained raw but are not guessed or converted by this report.

`summary.json` contains `token_usage` per mode; each saved evaluation contains it per run,
including `by_phase`
and `by_agent` groups. `input_tokens`, `output_tokens`, and `tokens` are null if a required
count for that total is unavailable. Their `known_*` fields remain partial subtotals;
`unknown_*_calls` records how many counts are missing. Input and output completeness
are independent. Optional cache/reasoning completeness is independent of the main total.
Empty CSV token cells mean unknown. A phase with no calls has zero use; a mode with no
started run has no token summary. Active/crashed calls left `RUNNING` have unknown counts.

Budget checks now include whichever input/output counts are known, even when the other
field is missing. A failed provider request also marks runtime usage as incomplete.
An unknown total is not a hard provider spending limit. The pre-existing oversized-prompt
reservation gap is still documented in [limitations](../limitations.md).

The exported call CSV omits prompts, responses, and model error text. Detailed source
records remain local. Fixed-reply software tests supply invented token counts and are
labelled `is_model=false`; they verify accounting rather than measure a model.

Reports show confirmed passes divided by **all attempted runs**, with unresolved counts
next to them. Paired pass/fail counts use fully scored pairs and separately count missing
or unresolved pairs. They do not provide statistical significance or a general winner.

## What remains separate

These are small, public development examples in one sales domain. They are unsuitable
as the final unseen study set. They do not comprehensively check every supported worker
method, every natural-language claim, arbitrary malicious files, or service-crash recovery.
No controlled runtime-failure injection or recovery-success score is included yet.
Use a separate unseen collection, broader tasks, frozen settings, repeated real model
runs, and matched fault conditions before drawing research conclusions.

Tests use fixed model replies with real MCP and native PostgreSQL, and separately check
that wrong answers fail even when execution says `COMPLETED`. See
[retained validation](../../reports/evaluation_validation/README.md).

Final verification on 2026-10-21 passed Ruff and formatting, then **171 tests passed
and 1 skipped**, with native PostgreSQL and the then-existing Docker checks enabled. The skipped
test requires explicit live-model opt-in. No live worker-model evaluation was run.

The pricing pilot and Docker runner/checks were removed on 2026-10-23. That earlier count
describes the previous source; see [current cleanup validation](../Cross-check/README.md).
