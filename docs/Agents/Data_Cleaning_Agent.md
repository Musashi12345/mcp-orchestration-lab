# Data Cleaning Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `dataset`, optional `rules`, and optional `profile`.
Only explicitly allowed cleaning rules may change cells or remove rows. The worker saves
a cleaned copy, per-change CSV, before/after facts, and source-row links. There is no
separate public `options` argument. See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md). Original files remain unchanged; every accepted
cleaned CSV becomes a new registered dataset with a record of where it came from.

## 1. Job and when to use it

Make the changes needed for the assigned question, explain them, and check their effect.
Use this agent only when cleaning is needed. A Data Understanding result is helpful but
optional; the agent can inspect its own input enough to carry out the assigned job.

Example job: "Standardize the explicitly documented date format and remove exact repeated
rows. Preserve rows with missing amounts and explain how many there are."

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `data_cleaning` |
| MCP server name/version | `data-cleaning`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.cleaning.server` |
| Public tool | `clean_data` |
| Published description | Create a checked cleaned copy of a registered CSV under explicit task rules, retaining the original and a change record. |

Run as a separate process using the official SDK and stdio. Publish complete typed inputs
and outputs through discovery, without cleaning or making model calls at startup.

Implemented stdio entry point:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.cleaning.server
```

Use the common configuration pattern with this server ID/module and shared-service
environment. The executor invokes `clean_data` only when selected in the accepted plan.
Use the shared conservative retry hints until complete receipt handling is proven.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required assigned subtask; checked against the saved job. |
| `dataset` | Required registered CSV reference belonging to this run. |
| `profile` | Optional registered JSON result from a relevant earlier check. Verify its input hash matches this dataset. |
| `rules` | Typed task rules for missing values, duplicate handling, formats, allowed changes, and columns that must be preserved. |
| `options` | Limits on output size, detailed change records, and supported operations. |

An empty rule set does not authorize every possible change. When an important rule cannot
be inferred from the user's instruction, request information or leave that value unchanged
and explain the limit. Do not ask the LLM to decide an unstated business fact.

## 4. Published result

Use the shared result fields, including the new CSV reference in `datasets`. Typed
`details` contains the accepted cleaning recipe, before/after checks, row counts,
per-column change counts, unchanged unresolved issues, and source-row mapping.

Register:

- The cleaned CSV, with updated metadata, encoding, delimiter, and content hash.
- `cleaning_recipe.json`, including the exact rules and reasons applied.
- `cleaning_changes.csv` or another explicitly checked change-record format.
- `cleaning_checks.json`, comparing the input and output.

The change record identifies affected source rows and columns, old/new values where
applicable, operation, and reason. Preserve enough mapping to explain removed rows and
renamed columns. Apply file-size limits before work; do not silently truncate this record
and claim it is complete. Original data plus the recipe must remain available.

## 5. Internal work and LLM calls

1. Validate input versions and rules; save the worker start and baseline checks.
2. Ask the LLM for a structured cleaning recipe using only supported operations.
3. Check every operation against the job, allowed columns, and task rules. Save both
   rejected proposals and the accepted recipe.
4. Apply the accepted recipe through handwritten functions, producing staged new files.
5. Check preserved columns, row counts, types, and required values. Compare changes with
   the recipe; a change outside it fails validation.
6. Ask the LLM to explain the actual changes using saved counts. Register the checked
   dataset and change records, then save the completed receipt.

First operations may include explicit type conversion, stated date parsing, documented
category replacements, selected whitespace handling, and explicitly defined duplicate or
missing-value rules. These are available actions, not a cleaning sequence to always apply.
No generated Python, shell text, or arbitrary expression runs in the worker process.

## 6. Limits and failure behavior

- Missing is not automatically zero; a repeated customer is not automatically a duplicate row.
- Preserve identifiers, leading zeros, units, and category meaning unless a rule permits change.
- Do not remove outliers, fill values, or drop rows merely to make data appear cleaner.
- Do not reinterpret ambiguous dates or change currencies/units without a stated rule.
- A request requiring an unsupported or unclear destructive change returns `NEEDS_INPUT`
  or `UNSUPPORTED`; it does not publish a supposedly completed cleaned dataset.
- If no change is needed, return the existing dataset reference and verified no-change
  explanation rather than creating a misleading new version.
- A partially written output is not returned as a valid dataset after an error or cancellation.

## 7. Records saved during work

Save the input profile, model calls, candidate recipes, validation errors, operation
stages, before/after checks, and each output registration as work happens. Link every
new dataset to its source version, accepted recipe, and producing attempt.

The shared service owns model usage and the stable operation receipt. Repeated delivery
of a known completed operation must not create another cleaned file or model call.

## 8. Tests before live model work

- Exact duplicates are removed only under the requested rule; legitimate repeated IDs remain.
- Leading-zero identifiers, missing amounts, and empty strings preserve their intended meaning.
- Ambiguous dates require information; an explicit format produces checked conversions.
- Unchanged inputs keep the same hash; changed outputs have new IDs and correct counts.
- The change record reconciles every modification and removed row with the source data.
- A model-proposed forbidden column drop is rejected before any output is accepted.
- Output files preserve quoted fields, supported text, and declared reading rules.
- An old profile for another data version is rejected.
- Real MCP retries reuse receipts; foreign references, interrupted writes, and database
  failures do not publish valid-looking partial outputs.

## 9. Implementation checklist

- [ ] Define typed cleaning rules, recipe, change records, checks, and result.
- [ ] Implement supported transformations and source-row mapping.
- [ ] Add recipe validation and the bounded worker LLM loop.
- [ ] Publish `clean_data` as an independent official-SDK MCP server.
- [ ] Register produced CSVs and preserve their input/recipe links through the shared service.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests.
- [ ] Run and retain a bounded live-model smoke after those checks.

Complete when every change is allowed, explained, reproducible from retained inputs and
rules, and delivered as a usable registered dataset without changing the original.
