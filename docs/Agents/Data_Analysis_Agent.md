# Data Analysis Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `datasets` containing exactly one CSV, and optional
`definitions`. Checked methods include filters, basic totals/averages, groups, time groups,
one before/after comparison, correlation, and PNG bar/line charts. `evidence`, public
`options`, multiple-file analysis in one call, and unrestricted statistics are not included.
See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md). This agent turns an assigned question into
checked calculations and findings. An LLM-written explanation is not evidence by itself.

## 1. Job and when to use it

Answer questions using filters, totals, grouped comparisons, changes over time, patterns,
and suitable charts. It can work directly from a registered original CSV when no cleaning
or combining is needed. It does not always require a Report Agent afterwards.

Example job: "Compare sales by month and region. Show which regions contributed to the
drop, while distinguishing a lower order count from a lower average order value."

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `data_analysis` |
| MCP server name/version | `data-analysis`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.analysis.server` |
| Public tool | `analyze_data` |
| Published description | Answer an assigned question with checked calculations, comparisons, and charts from registered datasets, retaining the method and evidence. |

Use the official SDK and stdio in a separate process, with complete typed arguments and
structured results. Discovery must not calculate findings or consume a model call.
Its implemented stdio entry point is:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.analysis.server
```

Configure this server through the existing MCP server list. It exposes its real supported
methods; its description does not require a specific earlier or later agent. Use the
common restricted environment, trusted call metadata, and conservative retry hints.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required assigned question/subtask, checked against the saved job. |
| `datasets` | Required nonempty list of registered CSV references belonging to this run. |
| `evidence` | Optional registered earlier findings or data explanations, with checked source versions. |
| `definitions` | Typed metric meanings, units, date rules, known filters, and other public task constraints. |
| `options` | Allowed methods and bounds on groups, chart count, time, input size, and outputs. |

If several files require a join, do not silently perform the Combining Agent's job or call
it internally. Analyze supplied files independently when that answers the question;
otherwise return the missing input requirement to the main orchestration path.

## 4. Published result

Use the shared result fields. Typed `details` contains the question addressed, calculation
recipe, filtering/missing-value rules, result tables, chart descriptions, checked findings,
and questions that the supplied data cannot answer.

Each finding includes a fact ID, exact calculated value, units, input versions, calculation
ID, filters, and relevant counts. A percentage includes its numerator, denominator, and
zero-denominator behavior. A relationship found in data is not proof of a cause.

Register `analysis_recipe.json`, `findings.json`, result-table CSVs, and useful chart files
within limits. Start with trusted PNG/SVG chart output produced by checked plotting code.
The LLM supplies a checked chart description, not executable plotting code or raw SVG.
Do not create a changed input dataset as a side effect of analysis.

## 5. Internal work and LLM calls

1. Validate the job, source files, relevant definitions, and optional evidence.
2. Build bounded input facts and ask the LLM for a structured analysis recipe.
3. Check columns, methods, filters, calculations, grouping, units, and output-size limits.
4. Run handwritten operations and save calculation records/result tables as they finish.
5. Build charts only from checked tables and save their source mappings.
6. Ask the LLM to explain the saved facts, referencing fact IDs. Check all numeric claims
   and publish the findings/result receipt.

Initial supported operations: explicit filtering, counting, sums, averages, grouped
comparisons, time grouping, percentage changes, and clearly labeled correlations when
valid for the data. Publish exact capabilities and assumptions. Statistical tests or other
methods require their own checked implementations before being advertised.

Use bounded method choices, not generated Python, a general expression evaluator, or free
SQL. The agent may choose its calculations; it cannot revise the main DAG or invoke another role.

## 6. Limits and failure behavior

- Require or report unclear definitions such as whether "sales" means gross or net sales.
- Preserve units and time boundaries; avoid comparisons between different periods or currencies.
- Report excluded/missing records and their effect on denominators.
- Protect against zero denominators, invalid dates, nonfinite values, and unsuitable data types.
- A filtered or sampled result must not be described as covering all source rows.
- Avoid hiding poor, weak, or contradictory results by selecting only favorable comparisons.
- Explain that a measured association cannot establish why something happened.
- Return `NEEDS_INPUT` or `UNSUPPORTED` when the job cannot be answered honestly with the
  supplied files and supported methods. Do not invent a business explanation.
- No figure in the final text may come only from an unchecked LLM calculation.

## 7. Records saved during work

Save proposed/accepted recipes, column/definition checks, filtered row counts, calculation
settings, actual table values, chart specifications, model calls, warnings, and output
registrations during the call. Preserve the link from every chart/finding to its source
table, input hashes, and producing step.

The shared service owns usage and receipts. A valid earlier result can be cited, but a
model-generated paragraph without checked facts must not become a new numeric source.

## 8. Tests before live model work

- Known synthetic totals, averages, groups, and month comparisons match independent expectations.
- Percentages record the correct denominator and handle zero/empty groups explicitly.
- Missing values, mixed types, and time boundaries follow the accepted recipe.
- Two equivalent groupings cannot silently count the same row twice.
- A model-proposed nonexistent column, invalid metric, or unsupplied file is rejected.
- A model explanation with changed totals fails the numeric-evidence check.
- Chart values and labels match the registered source table, including units and ordering.
- A question requiring unavailable causal evidence produces a stated limit.
- A direct analysis-only plan works without forcing Understanding, Cleaning, or Report.
- Real MCP, concurrent calls, owned output refs, live records, cancellation, and retries
  pass the common runtime tests.

## 9. Implementation checklist

- [ ] Define typed definitions, recipes, calculations, findings, charts, and result.
- [ ] Implement checked calculations and chart generation with pinned dependencies.
- [ ] Add checks that reported numbers match saved facts, and the bounded worker LLM loop.
- [ ] Publish `analyze_data` through its separate official-SDK MCP server.
- [ ] Connect shared model calls, result tables, artifacts, and operation receipts.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests.
- [ ] Run a bounded live-model smoke after those checks pass.

Complete when a user question receives useful findings whose numbers and charts can be
checked against the exact saved calculations and input versions.
