# Current implementation and research limits

The active application is CSV data analysis with D1/D2/P1/P2.
The older pricing experiments, Python container runner, evaluator, and
dashboard have been removed. Historical databases, runs, batches, and reports remain.
P1/P2 share a CSV-only Docker runner; D1/D2 do not need Docker. PostgreSQL stays native.

## Planning and execution

- A model chooses tools and dependencies without a prescribed agent sequence. Graph and
  schema checks establish valid structure, not that the user's business meaning is correct.
- Review rules use completed-attempt thresholds, currently 1 and 2 in agent configs.
  Parallel draining can reach both at once; short plans can leave a review unreached.
- Unknown outcomes are saved and stopped, not silently retried. Durable host-crash resume
  and reconciliation of unfinished external work are not implemented.
- P1/P2 permit one limited async Python function per version for calls, conditions, and parallel work.
  It forbids imports, loops, helpers, arithmetic, and direct file/network access. Data
  calculations remain in the agents. These language checks enforce the experiment's
  scope; Docker is the execution boundary. Shell, SQL, and arbitrary formulas are absent.
- P1/P2 use the same broker, worker gateway, budgets, and attempt records as DAG runs.
  It has one call site per assigned job; conditional jobs can be skipped. A successful
  fallback explicitly names confirmed failures it handles. Unknown outcomes stop the run.
- P2 revisions start fresh containers; arbitrary Python locals are not preserved.
  Selected verified result envelopes must fit `max_result_bytes` in aggregate, a bound
  also applied to D2 revision snapshot bindings. Python startup also has a pipe-frame
  limit. Results outside that bound cannot be silently truncated or reconstructed.
  D2/P2 retain prior failures until a declared replacement step succeeds; earlier D2
  records predate this control. The broker protects exact operation identities, not all
  semantically similar work under fresh IDs.
- The Docker daemon and local service processes are trusted. The container shares the
  Docker Linux kernel; this is not a separate VM per program. Host death can leave a
  container or external operation unfinished. No automatic crash reconciliation is claimed.
- Each P1/P2 runner records its exact image ID and SDK hash. A development image label checks local
  build freshness; it is not a signed software supply-chain guarantee. Rebuild after SDK
  changes. Existing saved handoffs from older source/configurations must be replanned.
- The prompt-size check currently happens after reserving a model-call slot. An oversized
  unsent request can consume a slot without a saved provider-call record. This audit
  finding remains unfixed by the removal-only cleanup.

## Agents and data

- The six agents use bounded model choices and trusted handwritten calculations. Normal
  tests use fixed model replies with actual MCP processes. Latest live Q01/Q05/Q10 answers
  pass in all four modes, including a second attempt for Q05 D2. Only Analysis, Cleaning
  and Prediction were used; broader live worker quality outside these known tasks remains
  unverified.
- Initial CSV registration allows 100 MiB by default. Worker reads allow at most 16 MiB
  per CSV and normally 100,000 rows. Models receive bounded context, not every cell.
- Cleaning follows supplied rules, but the rules' translation from the user request is
  not independently proved. The planner checks discovered required arguments, including
  known Python argument objects, and can use its bounded correction step before execution.
  Unknown data-dependent values stay checked at dispatch; static checks do not establish
  that a model filled every field with the right meaning. Numeric conversion accepts
  three-digit comma grouping with a period decimal point; other comma formats are rejected.
  Combining checks stated keys and row growth, not business
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

- All twelve latest Q01/Q05/Q10 answers pass on the same source/settings; Q05 D2 needed
  a separate second attempt. Eleven of twelve first attempts passed. The user-approved
  comparison includes that failure and both attempts' costs. Q01's older attempts remain
  in history with their original failed delivery grades. The report retains all 34 live
  attempts and separately labels 21 older attempts outside its thirteen-attempt main
  view. The current checker reproduced all thirteen latest-source grades in memory
  without changing PostgreSQL or original grades. All eight completed current reviews
  chose KEEP; six happened after the original jobs finished. Revision, recovery and live
  parallel work remain unmeasured, so review costs do not demonstrate a benefit from
  replanning. See the [insights](../reports/comparison_2026-10-27/Insights.md),
  [comparison](../reports/comparison_2026-10-27/Report.md) and
  [Q05 repair](evaluation/Q05_Repair_2026-10-27.md).
  Main Task can ask about unavailable tools before receiving the discovered cache, and
  final numeric publication currently depends on a successful model-written explanation.
  See the [local full analysis](../reports/analysis_2026-10-27/Report.md).

- The original small queue was ended at the user's request after seven new attempts;
  the last Q10 P2 attempt was not started. Two missing run links were recovered, and
  all 34 calls from attempted new runs are now in the collection. Old manifests remain
  unchanged. Subsequent repairs use a new source identity and an approved 300,000-token
  experiment configuration. Fixed replies establish the repairs' engineering behavior;
  later live Q01/Q05/Q10 results are described above. See
  [repair details](evaluation/Repairs_2026-10-27.md).

- The small Q01/Q05/Q10 experiment is an exploratory twelve-attempt collection: four
  retained Q01 attempts plus eight new automatic attempts. Original batch identities
  remain distinct. A host queue checks after Q01's observed mode time plus two minutes,
  then every minute; this timing is not a completion guarantee. It continues after
  saved failed attempts without retrying them, but refuses a new launch if source,
  inputs, storage or an unfinished process/container prevents safe identification.
  No host-crash resume is implemented. See [queue behavior](evaluation/Small_Automatic_Batch.md).

- Records use local PostgreSQL and files use disk. The user's database needs a configured
  `.env`; isolated native PostgreSQL tests do not establish user-database readiness.
- SQL and disk writes are not one atomic power-loss transaction. Schema initialization
  supports version 1, not a complete future migration framework. Back up both stores.
- Services are trusted local processes, with loopback/token access checks. They are not
  hostile-code OS sandboxes or a hosted multi-user product. Health does not verify a DB
  connection or model login. Restart loaded workers after source changes.
- Main/worker/review calls share a run allowance. Token usage is observed after responses;
  missing usage and subscription USD cost remain unknown. Input/output, optional
  cached/reasoning fields, and known partial totals are saved and reported per call,
  phase, agent, and mode. Failed/correction calls remain included. A provider failure
  without counts cannot be measured, and no text-based estimate fills that gap.
  No hard USD cap is claimed.
- Optional `model.request_gap_seconds` defaults to zero. Configured waiting is shared
  across model calls within an application instance and saved calls in the same run;
  separate processes and Codex chats do not share the gate. Waits count toward run/tool
  deadlines and are saved separately from model calls. The 90-second D1 diagnostic is
  a user-chosen test setting; it does not identify or guarantee compliance with an
  unknown provider limit. The Codex CLI's internal retries are unchanged.
- The evaluator grades fifteen public questions over ten small sales-domain CSVs. New
  questions need independent checks. Reports/charts/clarification need stated human review.
  The collection is not an unseen final study set.
- The ten local `Input/` CSVs have 14 approved questions and frozen hashes in a separate
  suite. Their independent checks are implemented. The first live Q01 pilot attempted
  four modes and all stopped before execution: D1/P1 raised missing-capability concerns,
  and D2/P2 received HTTP 429. After the approved planner-information repair, the second
  Q01 batch reached P1's correct internal calculation in Docker/MCP, but its explanation
  call received HTTP 429 before final table publication. D1/D2/P2 received HTTP 429
  during Main Task creation. Those earlier pilots established no successful live worker
  answer; later repaired Q05/Q10 results now provide live evidence in all four modes.
  Q05 required a D2 retry, while Q10 passed first attempts across all modes. An unseen,
  repeated four-mode study remains absent. Further batches and provider/retry/limit changes
  require the user's choice. See [restart findings](evaluation/Planner_Repair_and_Restart_2026-10-26.md).
- Manual grading now rejects extra original CSVs. New CSV records distinguish inputs
  and generated files; older worker outputs can be recognized through parent links.
  Unmarked older CSVs without generation links are conservatively treated as originals.
- Controlled service-failure recovery scoring, blinded review UI, statistical inference,
  and an unseen four-mode study remain future work. Explicit four-mode development
  batches are supported. No research winner is established.

The [dated pre-cleanup audit](Cross-check/2026-10-23-before-cleanup/README.md) describes the
earlier source. Its removed-file links are historical. Current cleanup/test evidence is
listed in [Cross-check](Cross-check/README.md).
