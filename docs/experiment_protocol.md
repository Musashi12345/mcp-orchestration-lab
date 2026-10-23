# CSV research controls

This independent project studies how a model chooses and runs data-analysis work.
The current application implements D1/D2 only. P1/P2 remain planned treatments; their
older pricing-domain implementation has been removed.

| Planned treatment | Representation | Main-planner execution review |
|---|---|---|
| D1, implemented | DAG | None |
| D2, implemented | DAG | Two configured opportunities |
| P1, future | Python | None |
| P2, future | Python | The same task review rule |

Worker agents may make model calls in every treatment. The distinction is execution
review by the main planner. Future Python must use the same CSV broker/runtime controls
and an isolated execution design; generated code must never run in the host process.
There is currently no generated-code executor in this application.

Compare runs using the same public question, original CSVs, tool definitions, agent
implementations, model/settings, budgets, concurrency, and review rules. Keep fresh run
IDs and file copies; do not share model response caches between runs. Preserve source,
lock, settings, suite, and fixture hashes, and keep failures and unresolved attempts.

Current reviews use increasing completed-attempt counts. Active work settles at a review
boundary, so both thresholds can be reached with the same observations. A short graph
can leave a review unreached. Freeze and report these rules before measured comparisons;
do not silently turn them into named agent-order rules.

Use a separate evaluator after execution. It reads declared final outputs and computes
answers independently from agent calculations. Human review remains required for stated
chart/report/clarification criteria. Execution `COMPLETED` alone is not task success.
Never send private grading calculations or expected answers into planning/worker context.

The present fifteen tasks over ten synthetic CSVs are public development examples. They
are not the unseen research set. New tasks need independent answer checks before scoring.
Freeze a broader unseen collection, model/configuration, repeated-run design, and budget
before drawing conclusions. The current new evaluator has no controlled service-failure
recovery score or statistical proof of a representation winner.

The earlier pricing protocol is retained only as
[historical documentation](reference/pricing_pilot/experiment_protocol.md).
