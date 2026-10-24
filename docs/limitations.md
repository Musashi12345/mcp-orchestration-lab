# Current implementation and research limits

The active application is CSV data analysis with D1/D2/P1. P2 is not implemented.
The older pricing experiments, Python container runner, evaluator, and
dashboard have been removed. Historical databases, runs, batches, and reports remain.
P1 uses a new CSV-only Docker runner; D1/D2 do not need Docker. PostgreSQL stays native.

## Planning and execution

- A model chooses tools and dependencies without a prescribed agent sequence. Graph and
  schema checks establish valid structure, not that the user's business meaning is correct.
- Review rules use completed-attempt thresholds, currently 1 and 2 in agent configs.
  Parallel draining can reach both at once; short plans can leave a review unreached.
- Unknown outcomes are saved and stopped, not silently retried. Durable host-crash resume
  and reconciliation of unfinished external work are not implemented.
- P1 permits one limited async Python function for calls, conditions, and parallel work.
  It forbids imports, loops, helpers, arithmetic, and direct file/network access. Data
  calculations remain in the agents. These language checks enforce the experiment's
  scope; Docker is the execution boundary. Shell, SQL, and arbitrary formulas are absent.
- P1 uses the same broker, worker gateway, budgets, and attempt records as DAG runs.
  It has one call site per assigned job; conditional jobs can be skipped. A successful
  fallback explicitly names confirmed failures it handles. Unknown outcomes stop the run.
- The Docker daemon and local service processes are trusted. The container shares the
  Docker Linux kernel; this is not a separate VM per program. Host death can leave a
  container or external operation unfinished. No automatic crash reconciliation is claimed.
- P1 records its exact image ID and SDK hash. A development image label checks local
  build freshness; it is not a signed software supply-chain guarantee. Rebuild after SDK
  changes. Existing saved handoffs from older source/configurations must be replanned.
- The prompt-size check currently happens after reserving a model-call slot. An oversized
  unsent request can consume a slot without a saved provider-call record. This audit
  finding remains unfixed by the removal-only cleanup.

## Agents and data

- The six agents use bounded model choices and trusted handwritten calculations. Tests
  use fixed model replies with actual MCP processes; live worker quality remains unverified.
- Initial CSV registration allows 100 MiB by default. Worker reads allow at most 16 MiB
  per CSV and normally 100,000 rows. Models receive bounded context, not every cell.
- Cleaning follows supplied rules, but the rules' translation from the user request is
  not independently proved. Combining checks stated keys and row growth, not business
  equivalence of every column/unit. One join call can combine two to eight files using
  the same key/type/relationship rule at each stage.
- Analysis handles one CSV per call, supported filters, groups, measures, comparisons,
  correlation, and PNG charts. Arbitrary derived formulas and causal proof are absent.
- Prediction offers least-squares regression, nearest-centroid classification, and
  last-value forecasting, with held-back checks and simple references. There is no broad
  model search, confidence interval, deployment, or automatic retraining.
- Reports are Markdown with saved fact/source links. The text guard rejects bare digits,
  not every unsupported numeric claim: numbers written in words can pass. Fact references
  also do not prove all causal/business sentences. Word/PDF/publication are not included.

## Storage, access, and evaluation

- Records use local PostgreSQL and files use disk. The user's database needs a configured
  `.env`; isolated native PostgreSQL tests do not establish user-database readiness.
- SQL and disk writes are not one atomic power-loss transaction. Schema initialization
  supports version 1, not a complete future migration framework. Back up both stores.
- Services are trusted local processes, with loopback/token access checks. They are not
  hostile-code OS sandboxes or a hosted multi-user product. Health does not verify a DB
  connection or model login. Restart loaded workers after source changes.
- Main/worker/review calls share a run allowance. Token usage is observed after responses;
  missing usage and subscription USD cost remain unknown. No hard USD cap is claimed.
- The evaluator grades fifteen public questions over ten small sales-domain CSVs. New
  questions need independent checks. Reports/charts/clarification need stated human review.
  The collection is not an unseen final study set.
- Manual grading verifies required original CSVs but does not yet reject extra originals.
  The paired batch runner supplies exactly the declared files. Fix this gap before treating
  arbitrary manually graded runs as equal-information research evidence.
- Controlled service-failure recovery scoring, blinded review UI, statistical inference,
  and a full four-mode comparison remain future work. No research winner is established.

The [dated pre-cleanup audit](Cross-check/2026-10-23-before-cleanup/README.md) describes the
earlier source. Its removed-file links are historical. Current cleanup/test evidence is
listed in [Cross-check](Cross-check/README.md).
