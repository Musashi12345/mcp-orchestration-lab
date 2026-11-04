# First live Q01 pilot — 2026-10-26

The approved first live batch finished. **All four modes failed before execution.**
No data-analysis tool or Docker runner was invoked, so this batch does not compare
the execution engines or establish an answer-quality winner.

## Approved setup

- Q01, the completed-order total, using the frozen local `Input/orders.csv`.
- D1, D2, P1 and P2, one fresh run each; shuffle seed 0.
- `configs/agents_stdio.yaml`, `gpt-6.1-sol`, low reasoning.
- Per run: 32 model calls, 120,000 observed tokens, 30 minutes, existing shared limits.
- Batch ceiling: 128 model calls. Actual application call records: **7**.
- Native PostgreSQL database `mcp_execution_lab`, created with the user's approval.
  The verified connection is stored in ignored `.env`; no credentials are in this doc.

Batch ID: `eval_batch_fbc3ded9f2f242ec997148a93ab27934`.
Source, configuration and input hashes match the approved proposal throughout the batch.
These are real model calls, recorded with `is_model=true`.

## Results

| Mode | Stop point | Calls | Input tokens | Output tokens | Total tokens |
|---|---|---:|---:|---:|---:|
| D1 | Tool selection requested clarification | 2 | 39,041 | 421 | 39,462 |
| D2 | Codex rejected tool-selection call with HTTP 429 | 2 | Unknown | Unknown | Unknown |
| P1 | Tool selection requested clarification | 2 | 39,025 | 410 | 39,435 |
| P2 | Codex rejected main-task call with HTTP 429 | 1 | Unknown | Unknown | Unknown |

The known subtotal is **89,352 tokens** across five calls with reported usage.
D2 contributes 10,455 known tokens from its first call. Its second call and P2's call
have unavailable usage; they remain unknown. The complete batch total is therefore
unknown. Failed requests and their records are retained. No dollar estimate is made.

All seven calls belong to initial planning. There are zero agent model calls, review
model calls, worker tool attempts and program containers in this batch.

## What stopped planning

D1 and P1 selected `data_analysis/analyze_data`, with the correct reason: filter
completed orders and sum `amount_inr`. They then listed missing capabilities:

- A guarantee that money calculations use Decimal arithmetic.
- A review tool for the configured review points.
- P1 also questioned whether a matching saved answer table would be produced.

The selection validator treats any `missing_capabilities` entry as a stop. It does not
ignore these concerns or silently choose another tool. This behavior is visible in
`orchestration/planner.py`, and the saved candidates explain the run states.

The code provides the relevant capabilities:

- `agents/analysis/operations.py` uses Decimal internally for sums and means. Exported
  non-integral values may be JSON floating-point numbers; it is not exact Decimal JSON.
- `agents/analysis/worker.py` saves the named measures as CSV columns and saves structured
  grouped results as calculation evidence.
- `orchestration/reviews.py` supplies reviews inside the host runtime. A review MCP tool
  is not required. D1/P1 do not make main-planner review calls; D2/P2 use the host rules.

The current planning context includes review thresholds without clearly describing
these host responsibilities. The Analysis tool description also omits details of its
calculation and saved-table contract. **The proposed explanation is a gap between the
capabilities implemented in code and the information shown to the planner.** The saved
responses support this diagnosis; a successful fixed pilot after a change would still
be needed to verify the repair.

## Provider failures

D2 and P2 retained `codex.events.jsonl` containing `429 Too Many Requests` and
`turn.failed`. This confirms provider rejection but does not establish whether the
cause was a short-term request limit, a model-specific limit, or an exhausted allowance.
No unapproved retry batch was started.

A Code Mode host-disabled warning appears in both successful and failed model calls.
It does not by itself explain the two HTTP 429 failures. Host execution stays disabled.

## Repair proposed after this pilot

1. Give every initial planning stage a clear, neutral description of the run mode and
   host-supplied scheduling, storage and review behavior.
2. Explain that host reviews are not MCP tools to discover or select.
3. Describe the Analysis agent's real Decimal calculation and saved CSV/JSON contract
   in its MCP tool definition. Do not claim stronger precision than the code provides.
4. Tell planning to preserve the user's requested requirements rather than add new
   mandatory capabilities without a basis in the request.
5. Keep agent choice and task order model-decided. Keep strict missing-capability checks,
   shared limits, fixtures, grading rules and retained failed attempts.
6. Verify the repair with fixed replies and real MCP checks before proposing another live
   batch. Additional live calls and any new rate-limit retry policy need the user's choice.

No planner, agent, runtime or provider source was changed during this first pilot or
before this initial diagnosis was presented. The user subsequently approved the repair
and one restart with “okay fix it and restart”. The original batch remains retained;
the repair and new batch are recorded separately in
[`reports/planner_repair_2026-10-26/`](../../reports/planner_repair_2026-10-26/).

## Evidence

- [Batch report](../../reports/evaluation_batches/eval_batch_fbc3ded9f2f242ec997148a93ab27934/report.md)
- [Per-call token records](../../reports/evaluation_batches/eval_batch_fbc3ded9f2f242ec997148a93ab27934/model_calls.csv)
- [Saved diagnosis](../../reports/evaluation_batches/eval_batch_fbc3ded9f2f242ec997148a93ab27934/diagnosis.json)
- `reports/live_evaluation_preflight_2026-10-26/` contains readiness and approval records.
- PostgreSQL and the run file root retain requests, candidates, failures and separate grades.
