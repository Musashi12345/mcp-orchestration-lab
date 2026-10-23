# Implementation and research boundaries

The new data-analysis path is documented in
[Running.md](Agents/Running.md). It implements planner and DAG executor modules for D1/D2
and six separate LLM-backed MCP agents. A first independent evaluator now grades fifteen
public development tasks; see [evaluation instructions](evaluation/Running.md).
Data-analysis P1/P2, a final unseen evaluation collection, and a data-analysis dashboard
remain future work. Execution completion in this path is not labeled research task success;
a separate run-linked evaluation record provides the grade for a supported task.
It uses local PostgreSQL for records and disk files for data, while retaining old SQLite
evidence. The user's production database cannot be initialized until its `.env` connection
is supplied. Temporary native PostgreSQL tests do not modify that existing service.

The 2026-10-19 [planner/executor audit](../reports/orchestration_audit_2026-10-19/README.md)
reproduced gaps in failure-driven fallbacks, error details sent to D2, early type checks
for linked outputs, scheduling after skips, and final summaries on early stops. These
were fixed on 2026-10-21 with acceptance tests in `tests/orchestration/test_audit_fixes.py`.
The original audit remains a record of the earlier implementation.

Current agent limits:

- The first evaluator covers ten small synthetic CSVs in one sales domain. It grades
  only the exact published questions and frozen inputs. Charts and reports need human
  review for meaning/readability. It does not claim to grade arbitrary user questions,
  every natural-language claim, or prediction methods beyond the specified simple exercise.
  Controlled service-failure recovery scores, blinded review UI, statistical inference,
  and new Python execution remain future work. Public development fixtures cannot serve
  as an unseen final study set.

- Verification uses fixed model replies and real MCP processes. Live worker-model behavior
  and quality have not been tested. These checks are development evidence, not a model benchmark.
- Workers choose among checked, handwritten operations. They do not execute generated
  Python, shell, SQL, or arbitrary formulas. No remote data fetching is supported.
- A worker CSV is limited to 16 MiB and 100,000 rows by default, even though initial
  file registration permits larger files. Larger worker inputs are refused rather than sampled
  silently. Model context is bounded; it does not contain every cell in a large file.
- Cleaning requires explicit rules for changes. Combining uses explicit matching keys and
  bounded row expansion; matching business meanings and units is not independently proved.
  It saves unmatched counts and source-row links, not separate unmatched-row CSVs.
- Analysis supports one CSV per call, checked filters, totals, grouping, simple comparisons,
  correlation, and PNG charts. Combining several files requires a separate planned call.
  Causal findings, general statistics, and unrestricted chart methods are not included.
- Prediction supports linear numeric prediction, nearest-centroid label prediction, and
  last-value forecasting. It checks held-back data and a simple reference method, but has
  no advanced model search, confidence intervals, deployment, or automatic retraining.
- Report produces Markdown and structured evidence links from saved facts. Checked numbers
  do not establish that every natural-language claim or suggested business meaning is correct.
  PDF, Word, and remote publication are not included.
- Worker access is scoped to a running call through a local support service. Services are
  trusted local processes, not isolated hostile-code containers. The local admin token file
  relies on the Windows user's file access. This is not a multi-user hosted service.
- Main planning, reviews, and worker calls share the allowance of one claimed run. Observed
  token limits are checked after responses; unknown usage and subscription cost remain unknown.
  Worker tools advertise conservative retry hints. A lost or uncertain model result is not
  automatically replayed, and automatic recovery after a host crash is not implemented.
- Start-up health confirms service identity and readiness, not PostgreSQL connectivity or
  model login. Database checks occur when a run or inspection is requested. Restart services
  after changing code; discovery rejects an older loaded worker source version.

The following limits describe the original four-mode pricing pilot unless stated otherwise.

The four-mode application is functional. These limits define what its evidence can support.

- Workers operate on a declarative pricing-policy simulation. They do not run arbitrary
  repository code or use LLMs. Six fixtures cover healthy repair and verification/revision
  challenges, but belong to one closely related domain. General code-repair fixtures,
  LLM-worker transfer and an independent held-out study are future research work.
- Python's controlled lane forbids imports, loops, arbitrary functions and private access.
  DAG bindings support registered artifacts, guards, conditional choices and finite shared
  read/select/filter/merge/compare expressions. This is a controlled expressiveness study,
  not a comparison with unrestricted Python algorithms.
- Docker is the Python security boundary; AST validation is a conformance check. The runner
  has no host mounts, credentials, Docker socket or network, runs as UID 65532 with dropped
  capabilities, a read-only root filesystem and CPU/memory/process limits. Docker Desktop
  remains a trusted prerequisite. Trusted host MCP workers are scoped services, not OS-sandboxed
  hostile processes. The private evaluator runs only on the host after execution.
- Current validity is conservatively tied to workspace revision. Issue artifacts remain valid.
  Immutable content, exact input provenance and receipts are retained. Finer resource-level
  invalidation and arbitrary additional worker reads are not part of this fixture world.
- Every catalogue tool is idempotent. Semantic keys bind run, tool and exact inputs; service
  receipts prevent repeating committed effects. `results.record` also has one final intent
  slot. Non-idempotent effects and repeated identical effects with occurrence scopes need
  separate contracts before being added.
- `record_ack_lost` simulates a lost successful response, matched by logical tool identity.
  It is not a real network fault. Recovery repeats the exact operation identity. Unreached
  faults stay recorded as such. Cancellation is journaled; hard host termination can leave
  an incomplete journal. Automatic crash reconciliation/resumption is not implemented.
  Queued/running dashboard jobs are marked interrupted and never silently replayed.
- Codex uses supported non-interactive CLI authentication and structured output. It is an
  agent wrapper with its own prompt overhead, not a bare model API. Tools are disabled where
  supported; emitted tool activity causes rejection. Diagnostic error items are retained
  separately. CLI versions/features, raw usage classes and configuration remain auditable.
- Per-episode model-call/time caps and batch/dashboard call ceilings are enforced. CLI token
  usage is checked after a response; a call may exceed the observed cap. No hard per-turn
  token reservation is claimed. The output token hint is advisory. CLI requests without
  usage leave aggregate tokens null. ChatGPT subscription dollar costs are unavailable.
- The dashboard uses one local worker queue and SQLite persisted jobs. The model-call ceiling
  is per server invocation; restarting begins a new explicitly configured session. It is a
  localhost research tool, without enterprise authentication or multi-process coordination.
  Configuration changes require a new run/server and cannot mutate an active episode.
- The journal uses serialized transactions and default rollback journaling. No WAL,
  distributed exactly-once or universal restart-durability claim is made.
- Failed and incomplete experimental blocks remain visible. Descriptive paired contrasts
  require all four retained modes. Task-cluster bootstrap intervals are exploratory and
  weak with few related tasks; they are not evidence of generalization. Development smoke
  tests used changing source/configurations and are not a controlled model benchmark.
- Exports redact credential fields/common token patterns and private grading diagnostics,
  retain a manifest of exported file hashes, and preserve raw local evidence. They are not
  an infallible detector of sensitive data. Redacted artifacts can differ from registered
  original hashes; the export manifest records the copied content hashes.
- No repository remote, commits or publication were created. Initial Git setup was rolled
  back after an ownership mismatch. Initialize Git from your normal terminal before committing.
