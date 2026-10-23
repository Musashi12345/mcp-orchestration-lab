# Experiment contract — development version

Working title: **DAG Plans or Generated Programs? A Controlled Study of Adaptive MCP Orchestration**.
The project is independent of employer code and separate from MS admissions work.

| Treatment | Initial plan | Orchestrator LLM replanning |
|---|---|---|
| D1 | DAG | Disabled |
| D2 | DAG | Two public checkpoint opportunities |
| P1 | Python | Disabled |
| P2 | Python | The same two public checkpoint opportunities |

All four measured treatments require an LLM for initial planning. Handwritten development
plans have `research_treatment: null` and `exploratory: true`. They cannot establish a
representation winner or the benefit of adaptation.

Hold model/settings, initial information, tool contracts, worker implementations, artifact
access, budgets, concurrency, recovery and checkpoint observations constant. Every episode
gets a fresh world. No model response caches cross episode boundaries. Keep attempted
episodes and report infrastructure failures separately. Freeze prompts/config/fixtures
before held-out evaluation. Choose a specific model and an explicit spend ceiling before
paid pilot batches.

For the repair family, barriers occur after inspection and after both test/static checks,
before final verification and recording. Fixed executors make no model calls there.
Adaptive executors receive the same legitimate facts, valid/stale bindings, receipts,
diagnostics and remaining budgets. Hidden grading cases and fault schedules stay on the host.

Primary grading uses independent executable acceptance assertions plus committed effects
and current-revision evidence. Published checks and executor success are insufficient.
The deliberately wrong rounding control demonstrates that published checks can pass while
hidden acceptance fails.

Later measure task success, adaptation effects and interaction, unsafe reuse, duplicate
effects, cost, latency and failure classes. Pair task/condition blocks, randomize treatment
order and cluster uncertainty by base task. Small development fixtures do not establish
generalization. Equal runtime support cannot measure the runtime's causal benefit; that
requires a separate ablation.

## Context and decisions

Source blueprint: `docs/reference/Execution_Engine_Research_App_Build_Guide.md`, originally
provided at `C:/Users/Samarthya/Documents/Codex/2026-09-30/i-x20/outputs/`.
The related Topic 2 literature assessment was read for the experimental motivation.

2026-10-08: Retain Python 3.12, official MCP v2, Pydantic 2, asyncio, SQLite/SQLAlchemy,
uv lockfile, CLI-first delivery, deterministic workers, immutable artifacts and independent
grading. SDK documentation and the installed package agree on v2; resolution locked MCP
2.3.0. Use `sqlalchemy[asyncio]` to include its required greenlet dependency.
[Official MCP SDK](https://github.com/modelcontextprotocol/python-sdk),
[uv project workflow](https://docs.astral.sh/uv/guides/projects/).

The first fixture uses a declarative policy simulation instead of executing fixture source
code. This enables independently graded runtime development before a container worker is
available. Add real isolated repository fixtures before generalizing to code repair.


## Implemented planner route and pilot scope

2026-10-08: Added all four executors, shared finite expressions, normalized replanning,
Codex subscription planning, external command-router support, six policy simulations,
randomized batch manifests, selected exports and exploratory clustered analysis.
The dashboard uses the same controller and persists jobs before execution.

Fixed modes may use predeclared guards and fallback repair after the shared initial-check
checkpoint. The broker enforces entry to that checkpoint before another worker call once
both current reports are available. Revisions keep historical effects and reject stale
verification; replacement executors preserve run/world/receipt identity.

Codex is invoked afresh through saved CLI authentication. Tools are disabled and observed
tool activity is rejected. The CLI has its own prompt overhead; raw usage classes remain
recorded. `configs/codex.yaml` selects gpt-6.1-sol/low and bounded calls. Subscription
USD cost is unavailable; observed token ceilings are checked after responses and may be
exceeded by one call. No paid API client or extracted subscription token is used.

The final offline smoke batch has four complete task/condition blocks and 16 episodes.
It demonstrates engineering behavior, including expected naive fixed failures and bounded
adaptive/fixed recovery controls. Reports include all failed attempts and distinguish
unreached faults from fired faults. Descriptive task-cluster bootstrap intervals with only
two closely related tasks do not establish statistical generalization. Model smoke episodes
were not paired/randomized and have changing source/settings; do not pool their latency or
success into comparative findings. See `reports/codex-smoke-notes.md`.
