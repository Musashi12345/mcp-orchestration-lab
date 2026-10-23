# Project context

This is an independent research harness for a controlled D1/D2/P1/P2 comparison, not an
admissions application. Read README.md, docs/progress.md and docs/limitations.md first.
The original guide is preserved under docs/reference/.

Keep one broker/runtime for both representations. Do not expose hidden evaluator fixtures,
private fault schedules or the effect ledger to a planner or generated runner. Never run
generated code in the host process. Use the official MCP SDK through its adapter.

Handwritten reference episodes are exploratory and never labeled as model-generated D1.
Preserve scientific controls, attempts, source/configuration/fixture hashes and limitations.
No employer source or proprietary data belongs here.

Use the project .venv Python and Ruff; scripts/check.ps1 runs validation. Exercise runtime
invariants and genuine MCP integration with deterministic fixtures before paid provider work.
Do not remove retained run evidence during routine development.
