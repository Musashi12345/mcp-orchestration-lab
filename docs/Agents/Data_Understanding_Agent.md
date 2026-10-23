# Data Understanding Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `datasets`, and optional `questions`. Checks include
full-file row/missing/distinct/duplicate counts, observed types and numeric ranges, and
requested key checks. A separate public `options` argument and automatic proof of business
meaning are not implemented. See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md) for run ownership, MCP messages, model routing,
live PostgreSQL records, files, budgets, and tests.

## 1. Job and when to use it

Explain the supplied data and identify problems relevant to the assigned question.
The planner already has basic CSV metadata; this agent is for deeper checks when needed.
It is not a compulsory first step and does not automatically call Cleaning or Analysis.

Example job: "Explain the order and return files. Check whether their order IDs look
suitable for matching, and flag anything that may affect a return-rate calculation."

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `data_understanding` |
| MCP server name/version | `data-understanding`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.understanding.server` |
| Public tool | `understand_data` |
| Published description | Explain registered CSV files, calculate column checks, and identify relevant data issues without changing the files. |

Use the official SDK, typed input/output records, and stdio as described in the shared
plan. Discovery publishes this tool's actual abilities and limits without running it.
The stdio entry point is:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.understanding.server
```

The module is implemented. Configure its server ID and module in
the existing `servers` list. The executor discovers it and calls only this exact tool
when the accepted plan selects it. Conservative retry hints follow the shared plan.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required assigned subtask; must match the saved job. |
| `datasets` | Required nonempty list of registered CSV references from this run. |
| `questions` | Optional list of specific checks, such as uniqueness of an ID column. |
| `options` | Typed limits on samples, distinct-value examples, and expensive checks. Runtime limits remain the upper bound. |

The server receives trusted run/step/attempt metadata separately. It resolves references
through the shared service, verifies hashes, and reads only the supplied files. It cannot
scan the run directory for extra inputs. Record encoding and delimiter from registration.

## 4. Published result

Use the shared result fields. Its typed `details` will contain:

- A per-file summary: row count, columns, observed types, missing counts, and checked ranges.
- A column guide: likely meaning, supporting evidence, and uncertainty where meaning is unclear.
- Relevant quality issues, affected counts, and examples within the sample limit.
- Checked key candidates: uniqueness, missing values, and type/format compatibility.
- Possible relationships between files, clearly separated from verified matches.
- Unanswered questions and limits of the checks performed.

Register `profile.json` and `column_guide.json`. These names describe artifact roles;
actual owned paths use unique IDs. Return no new dataset because this agent does not
change values. Facts used by later agents have stable IDs and source references.

## 5. Internal work and LLM calls

1. Save the worker call and input versions before reading.
2. Calculate a basic full-file profile with checked functions. Bound memory use and work.
3. Ask the LLM which further supported checks address the assigned job. Supply metadata
   and bounded examples, not an unlimited copy of the files.
4. Validate its proposed column names and checks; save the accepted recipe.
5. Calculate the requested checks. Examples include duplicate counts, ID uniqueness,
   date parsing rates, mixed value types, and possible matching-key overlap.
6. Ask the LLM to explain the checked results in plain English. Verify every reported
   count/range against saved facts, then register the result and finish the receipt.

The LLM may describe a column as a possible customer ID; it cannot turn that guess into a
verified business definition. Ambiguous date strings, units, currencies, and time zones
remain stated uncertainties. A bounded sample cannot establish uniqueness for a full file.

## 6. Limits and failure behavior

- Do not clean, remove, join, or replace data while inspecting it.
- Do not infer a missing value is zero or assume a date format without evidence.
- Use full-file counts where claimed; label sampled estimates and skipped checks.
- Cap expensive pairwise comparisons and report checks omitted because of the allowance.
- Return `NEEDS_INPUT` for a business meaning essential to the job that cannot be established.
- Return a public error for unavailable, changed, unsupported, or incorrectly owned files.
- Never call another agent or suggest an agent order as a requirement in the tool description.

## 7. Records saved during work

Save profile stages, model requests/replies, the proposed/accepted checks, full-versus-sample
scope, each calculation's input versions, warnings, and registered outputs. Link everything
to this worker call and its owning tool attempt. Save failures and partial work too.

The live model-call allowance comes from the shared service. Discovery consumes no model
calls. An MCP retry of a known completed operation returns its saved receipt.

## 8. Tests before live model work

- A clean synthetic CSV gives exact row, missing, duplicate, and unique-value counts.
- Mixed types, empty files with headers, non-ASCII text, quoted commas, and missing values
  are handled using the saved CSV reading rules.
- A small preview cannot hide a duplicate later in the full file.
- Ambiguous dates and units produce uncertainty rather than invented definitions.
- A model reply naming an absent column is rejected and its correction attempt is saved.
- Instructions inside a cell cannot change the job, read another file, or invoke another tool.
- Two files produce checked relationship evidence without silently joining them.
- A real MCP call saves its worker stages before returning; separate calls stay isolated.
- Hash changes, cross-run references, cancellation, and database loss follow shared rules.

## 9. Implementation checklist

- [ ] Define typed request, profile, column-guide, recipe, and result records.
- [ ] Implement bounded full-file checks as handwritten functions.
- [ ] Add the worker prompt and checked recipe/explanation loop.
- [ ] Publish `understand_data` through its official-SDK MCP server.
- [ ] Connect shared file access, model calls, stages, and receipts.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests.
- [ ] Run a bounded live-model smoke only after those tests pass.

Complete when the agent explains verified facts clearly, preserves uncertainty, leaves
the input unchanged, and can be used independently of the other five agents.
