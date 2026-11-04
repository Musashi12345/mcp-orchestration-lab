# Small automatic CSV experiment

This describes the original 2026-10-26 queue. The user subsequently ended it after the
current evaluator exited: seven new attempts were started and the eighth was not
started. Original attempts remain retained. See
[repairs and recovered records](Repairs_2026-10-27.md). The launch claim and changed
source/settings prevent resuming or reusing that queue for a new repaired experiment.

The user selected three question/file pairs, each attempted in D1, D2, P1 and P2:

| Question | File | Work |
|---|---|---|
| Q01 | `orders.csv` | Completed-order total |
| Q05 | `orders_messy.csv` | Clean rows, record changes, calculate regional totals |
| Q10 | `daily_sales.csv` | Check a last-value forecast and save future predictions |

This is twelve attempts in total. The four finished Q01 attempts with 90-second model
spacing are retained and explicitly marked reused. Only eight new attempts are launched.
Each mode makes its own plan from the same question and declared CSV. No agent choice
or order is prescribed by this helper.

## Approved waiting and failure handling

Q01's saved launch/finish times provide these observations. They include the CLI's
execution and evaluation work; they are observations, not deadlines for other questions.

| Mode | Observed Q01 duration | First file check, rounded up |
|---|---|---|
| D1 | 521.200 seconds | 642 seconds |
| D2 | 521.471 seconds | 642 seconds |
| P1 | 518.380 seconds | 639 seconds |
| P2 | 524.290 seconds | 645 seconds |

The user approved Q01's duration plus two minutes, then a check every sixty seconds.
The helper checks both the evaluator's process exit and its saved terminal manifest.
An elapsed wait does not mean a finished run or a correct answer. A running process is
never abandoned merely because its first check time has arrived. This conservative
waiting can leave an already-finished process idle until the next check.

The user chose to record every failure and continue through all eight new attempts.
There is no automatic retry, including after a provider 429. Source changes, unavailable
storage, a competing active run, or an unfinished container prevent a new launch: the
helper cannot safely identify/account for a new attempt in those conditions. A stopped
queue must be inspected rather than silently resumed or replayed.

The existing 30-minute per-run limit, 32 model-call limit, token limit, tool timeout and
two D2/P2 review opportunities are unchanged. The eight new runs have a worst-case
ceiling of 256 application model calls. Q01 calls are retained separately from that new
allowance. No limit is increased for a slower task.

The configured 90-second model spacing remains inside each run. The helper also waits
at least ninety seconds after it observes an evaluator's exit before launching the
next evaluator. This external wait is recorded in queue status and is outside the
individual experiment's planning/execution timing. It is deliberately conservative.
Other applications and Codex chats are outside this gate.

## Implementation and evidence

`scripts/evaluation_queue.py` manages host processes and files. It calls the existing
evaluator CLI once for each new attempt, so the planner, agents, prompts, runtime,
grading and source hash are unchanged from Q01. P1/P2 generated Python still runs only
in Docker through the shared tool gate.

The helper freezes its own hash, the plan hash, implementation/lock/grader/configuration/
suite hashes, Q01 evidence hashes and seeded task/mode order. It refuses to overwrite
an existing queue. An OS lock prevents two helpers from running together; a permanent
launch claim prevents a finished or crashed queue from being relaunched accidentally.
Existing unfinished app runs and local Codex `exec` requests are checked before new
work. The desktop's persistent `exec-server` is not treated as an active model request.

The normal evaluator saves run records, model calls, waits, files and grades to native
PostgreSQL throughout execution. The helper checks run presence after completion and
adds an `evaluation_queue_episode` record linking queue, task, mode and original batch.
CSV files remain on disk. Credentials are read through the existing `.env` loader and
are never printed or passed on a command line.

Each queue directory contains:

- `plan.json`: fixed selection, old attempt links, settings identities and schedule.
- `status.json`: automatic state, child PID, next check/start time and per-run links.
- `progress.md`: readable twelve-attempt progress, with Q01 labeled reused.
- `collection.json`: run links and saved token totals by mode, phase and agent.
- `model_calls.csv`: saved call metadata/counts, including failures and unknown use.
- `episode_XX/`: each new attempt's CLI log and original evaluation batch reports.
- `launch.claim` and launcher logs/PID record: duplicate prevention and process identity.

This is an exploratory collection of separate batches. It is not represented as one
new randomized batch containing the earlier Q01 attempts. All original reports and
unsuccessful historical pilots remain retained. `FINISHED` means the queue ended, not
that any answer passed. The helper does not contact a model to monitor progress.

## Commands

Use the project's Python to prepare a fresh directory. Preparation reads frozen files
without contacting PostgreSQL or a model. The four baseline arguments point to the
specific retained Q01 status files; task IDs and waits are explicit.

```powershell
.\.venv\Scripts\python.exe scripts/evaluation_queue.py prepare `
  --directory reports/small_input_queue_2026-10-26 `
  --config configs/diagnostics/d1_q01_gap90.yaml `
  --suite fixtures/data_analysis_evals/input_v1 --input-directory Input `
  --baseline D1=reports/d1_q01_gap90_2026-10-26/status.json `
  --baseline D2=reports/d2_q01_gap90_2026-10-26/status.json `
  --baseline P1=reports/p1_q01_gap90_2026-10-26/status.json `
  --baseline P2=reports/p2_q01_gap90_2026-10-26/status.json `
  --task input_q05 --task input_q10 `
  --margin-seconds 120 --poll-seconds 60 --max-model-calls 256 --seed 0

# This launches real work and consumes the configured model allowance.
.\start_evaluation.ps1 -Directory reports/small_input_queue_2026-10-26

# Read saved state only; no model request.
.\.venv\Scripts\python.exe scripts/evaluation_queue.py status `
  --directory reports/small_input_queue_2026-10-26
```

The background helper waits sixty seconds at startup before model work so the launch
chat can end. The computer, Docker and native PostgreSQL must stay running. Host-crash
resume is not implemented. Detailed token/answer interpretation can be done later from
the retained records without more provider requests.

## Fresh batches after repairs

Use `--timing-baseline MODE=status.json` four times instead of `--baseline` when all
new results should come from the repaired source and settings. The earlier Q01 durations
then choose only the first check time (duration plus the selected margin); Q01 runs are
excluded from the new result collection and token totals. Their source/settings can
differ because they supply no comparison result. Their files are still hash-checked.

The new queue freezes current application, grader, helper, configuration and fixture
hashes. It keeps the same sequential launching, saved progress, per-minute follow-up
checks, request gap, full per-run allowances and record-and-continue failure rule.
It never overwrites, retries or combines old attempts with fresh ones. Both baseline
forms cannot be supplied together, and comparison reuse retains its strict identity check.
# Fresh Q01 on current settings

Timing-only baselines can now schedule Q01 itself: old Q01 runs choose check times,
while four fresh D1/D2/P1/P2 attempts use the current source and configuration. Q01
cannot be both reused as a result and scheduled again in the same queue.

The user approved one Q01 attempt per mode with 300,000 observed tokens, 32 model
calls per run, 90-second spacing, 30-minute run limits and unchanged review rules.
The four-run ceiling is 128 model calls. Seed 0 chooses mode order; execution remains
sequential, failed attempts are retained, and there is no automatic whole-run retry.

The readable queue view now updates with saved state transitions and scheduled checks.
For the completed Q01 batch, a one-off helper added a file-only tracking view every
15 seconds and ran the read-only comparison update after all four attempts finished.
It is retained in the local cleanup archive, rather than shipped as a reusable command;
its report scripts depend on the retained local evidence. The reusable queue remains
in `scripts/evaluation_queue.py` with `start_evaluation.ps1` as its launcher.
Monitoring does not contact a model. Source, settings, inputs and follow-up helper hashes
are frozen before launch. The previous comparison is copied before any report change;
fresh report files are staged and checked, and its Markdown entry point is replaced last.
Passes, failures and unavailable usage counts are all rendered from saved records.

