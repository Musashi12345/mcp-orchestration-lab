# CSV research controls

This independent project studies how a model chooses and runs data-analysis work.
The current application implements CSV D1/D2/P1. P2 remains planned. The older
pricing-domain implementation has been removed.

| Planned treatment | Representation | Main-planner execution review |
|---|---|---|
| D1, implemented | DAG | None |
| D2, implemented | DAG | Two configured opportunities |
| P1, implemented | Limited Python in Docker | None |
| P2, future | Python | The same task review rule |

Worker agents may make model calls in every treatment. The distinction is execution
review by the main planner. P1 uses the same CSV broker/runtime controls and a separate
Docker image; generated code never runs in the host process. Its initial source is
generated directly, without a DAG intermediate. Pre-execution correction follows the
same bounded rule as DAG planning. Data calculations remain in the shared agents.

The current Python treatment has no imports, loops, helper functions, or arithmetic.
Each assigned job has one call site; conditions may skip calls. Parallel work uses the
same shared capacity limit and review barriers. A successful prewritten fallback names
the confirmed failures it handles; unknown outcomes stop the run. Freeze this language
subset and report it as a research limit. P2 has no implementation or measured score.

Compare runs using the same public question, original CSVs, tool definitions, agent
implementations, model/settings, budgets, concurrency, and review rules. Keep fresh run
IDs and file copies; do not share model response caches between runs. Preserve source,
lock, settings, suite, and fixture hashes, and keep failures and unresolved attempts.
P1 also saves the exact image ID, SDK hash, configured limits, actual container settings,
and cleanup outcome. Its elapsed execution time includes Docker startup/cleanup; the
current report does not subtract that cost. Fixed-reply tests establish software behavior,
not a conclusion about model quality or which representation is better.

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
