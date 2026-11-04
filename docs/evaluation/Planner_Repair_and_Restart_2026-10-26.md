# Planner repair and Q01 restart — 2026-10-26

The user approved “okay fix it and restart”. The planner information was repaired,
fixed verification passed, and one new Q01 batch attempted all four modes with the
same settings. **All four final grades remain failed because of Codex HTTP 429 errors.**

## What changed

`orchestration/planning_context.py` now supplies the run mode and host responsibilities
to every initial planning stage, including Main Task creation. The contract explains
scheduling, MCP connections, stored records/files, and engine-owned reviews. D1/P1
checkpoints make no main-planner review call; D2/P2 use the configured opportunities.
Review is not a separate MCP capability to select.

The shared planning instructions ground required outputs and constraints in the user
request and task rules. Real missing capabilities still stop planning. The Analysis
tool definition now describes its existing Decimal sums/means, numeric export limit,
saved JSON evidence, and CSV rows/columns. No agent preference or order was introduced.
Model, limits, fixtures, grading rules, and provider retries were unchanged.

## Verification and restart

- Ruff and formatting passed for 120 Python files.
- `scripts/check.ps1`: **269 passed, one live-test skip**, in 735.53 seconds.
- Fixed replies with real MCP, Docker and temporary native PostgreSQL were used.
- Six new checks cover all four initial planning contexts, real missing-capability
  rejection, and the discovered Analysis description matching actual filtered totals
  and saved tables. The 42 focused checks also passed.
- One existing pytest cache write-permission warning remains; the tests completed.
- The orchestrator and six agents restarted, and their health was confirmed after
  the live batch. Docker responded and no lab containers remained.

Source: `80703c9e60fbdf73b8113aa0010de9250ad1dd159dc7aff9685c861f496640a5`.
Configuration, lock, suite and Docker image identities match the first pilot.
The original failed batch's saved files remain unchanged.

## Live result

Batch: `eval_batch_65c589770f1f4c8eb3bd3016f429174e`.
Q01, all four modes once, seed 0, `gpt-6.1-sol`, low reasoning, and a 128-call ceiling.
The schedule completed; that does not mean the individual runs succeeded.

| Mode | Calls | Result | Known token subtotal |
|---|---:|---|---:|
| P1 | 6 | Planning and calculation reached; explanation call received HTTP 429 | 111,100 |
| D1 | 1 | Main Task call received HTTP 429 | 0; usage unavailable |
| D2 | 1 | Main Task call received HTTP 429 | 0; usage unavailable |
| P2 | 1 | Main Task call received HTTP 429 | 0; usage unavailable |

P1 selected Analysis with an empty missing-capability list, generated valid Python,
started one Docker container and invoked one MCP worker. The saved recipe filters
`status = completed` and sums `amount_inr` as `total_amount_inr`. Its checked internal
calculation is **314,620.81**, matching the independent reference, with 365 included rows.
The explanation call failed before final CSV publication, so no final answer table was
available and the evaluator correctly marked the episode failed. Its reached host
checkpoint was recorded without a main-planner call, as P1 requires.

All four failed calls retain `codex.events.jsonl` with
`exceeded retry limit, last status: 429 Too Many Requests`. This identifies the provider
response, not the exact account/model/request-limit cause. There was no new automatic
retry policy or further batch.

Nine application model-call records were saved: five with usage and four with unknown
usage. Known input is 110,303 tokens and known output is 797, giving **111,100 known
tokens**. The complete total remains unknown. P1 planning accounts for 100,397 known
tokens and its recipe for 10,703; the failed explanation's usage is unknown. Failed
calls are included, and cached/reasoning subsets are not added twice.

This verifies the repaired planning path live for P1 and all four contexts with fixed
tests. It does not establish a successful live four-mode comparison. Any additional
batch, provider change, request pacing/retry rule, or limit change needs the user's choice.

## Saved evidence

- [Repair and fixed-test record](../../reports/planner_repair_2026-10-26/README.md)
- [Live batch report](../../reports/evaluation_batches/eval_batch_65c589770f1f4c8eb3bd3016f429174e/report.md)
- [Per-call tokens](../../reports/evaluation_batches/eval_batch_65c589770f1f4c8eb3bd3016f429174e/model_calls.csv)
- [Saved status and identity audit](../../reports/planner_repair_2026-10-26/restart-completed.json)
- [Provider events, calculation and cleanup evidence](../../reports/planner_repair_2026-10-26/restart-diagnosis.json)
