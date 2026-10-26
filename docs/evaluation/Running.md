# Data-analysis evaluation

Updated: 2026-10-25. This is a development collection, not the final unseen research test.

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
