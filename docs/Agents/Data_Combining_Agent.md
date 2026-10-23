# Data Combining Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `datasets`, and optional `rules`. This version appends
matching column sets or joins two to eight files using explicit shared column names. It checks
repeated keys, missing keys, row growth, and source-row links. Unmatched counts are saved;
separate unmatched-row CSVs, `relationship_notes`, and `options` are later extensions.
See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md). This agent creates a new dataset from supplied
files while preserving the original files and a clear record of the matching rules.

## 1. Job and when to use it

Join related files using matching columns, or append rows from files representing the
same kind of records. Select it only when the question needs multiple datasets combined.
It does not require a previous Understanding or Cleaning call if the inputs are usable.

Example job: "Match returns to orders using the documented order ID. Keep unmatched
returns in a separate output and report whether any match produced repeated order rows."

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `data_combining` |
| MCP server name/version | `data-combining`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.combining.server` |
| Public tool | `combine_data` |
| Published description | Join or append registered CSV files using checked matching rules, returning a new dataset and match-quality evidence. |

Run a separate official-SDK MCP process over stdio. Discovery publishes this tool and its
typed rules without touching data or calling an LLM. Configure it through the existing
server list; selection and ordering remain decisions of the main planner.

Implemented stdio entry point:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.combining.server
```

The server receives the same restricted shared-service environment and conservative retry
hints defined in the common plan. Internal key checks are helper functions, not calls to
other agent servers.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required assigned subtask, verified against the saved job. |
| `datasets` | At least two distinct registered CSV references from this run. |
| `relationship_notes` | Optional registered evidence about keys; verify each note's source versions. |
| `rules` | Typed known keys, desired row retention, expected match count per key, and column-name rules. |
| `options` | Bounds on input count, output rows/bytes, intermediate size, and unmatched outputs. |

The LLM may propose matching columns when evidence supports them. Two columns looking
similar does not prove they represent the same thing. An essential ambiguous relationship
requires more information. Accept no arbitrary SQL or user-supplied file path.

The shared list/object binding extension is needed to build `datasets` from several
resolved original or earlier-produced references. Do not work around this by embedding
unverified path strings in a prompt or giving the worker access to every run file.

## 4. Published result

Use the common result fields. Typed `details` contains:

- Join versus append choice and the checked reason for it.
- Exact input versions, matching columns, type rules, and column-name mapping.
- Which rows are retained: for example, all left-side rows or only matched rows.
- Expected and observed match counts: one-to-one, one-to-many, or an explicitly allowed alternative.
- Input/output row counts, unmatched counts, repeated keys, and row expansion.
- Warnings about omitted records, unsupported assumptions, or remaining uncertainty.

Register the combined CSV, `combination_recipe.json`, and `match_checks.json`. When
requested and within limits, register unmatched-row CSVs separately. Record source-row
mapping so a suspicious output row can be traced to its inputs.

## 5. Internal work and LLM calls

1. Verify references, inspect relevant columns, and save input/key checks.
2. Ask the LLM for a structured combination recipe supported by the job and evidence.
3. Validate keys, value types, row-retention rules, matching counts, and output naming.
4. Estimate output size before the full combination. Stop if bounds would be exceeded.
5. Join or append using handwritten operations. Validate actual row counts, key behavior,
   unmatched records, and source-row mapping.
6. Ask the LLM to explain the checked result. Register accepted datasets and evidence,
   then save the receipt before returning.

For more than two files, use a bounded structured recipe for the supplied files. The
agent may decide its local table operations; it cannot add another agent, fetch a file
not supplied, or alter the main execution plan.

## 6. Limits and failure behavior

- Do not silently turn a repeated-key match into many extra rows.
- Require an explicit allowed rule for many-to-many matching and enforce size limits.
- Check missing keys; do not automatically match missing values together.
- Keep distinct IDs such as `001` and `1` distinct unless a supplied rule permits conversion.
- Do not join solely because both files have a column called `id`.
- Do not silently convert currencies, time zones, units, or business meanings.
- Preserve same-named source columns using an explicit, recorded naming rule.
- Return `NEEDS_INPUT` for essential ambiguity, or `UNSUPPORTED` when the required
  relationship is outside the published operations. Do not claim completion by dropping data.
- Do not publish an oversized, incomplete, or unchecked joined file as a valid output.

## 7. Records saved during work

Save all key checks, proposed/accepted recipes, size estimates, intermediate operation
stages, actual match counts, model calls, and file registrations while they happen.
Link the output to every source version and the exact matching recipe.

All model calls use shared live reservations. A known duplicate request returns its
existing receipt and output references; an unknown model outcome is not automatically
repeated to produce a second supposedly identical dataset.

## 8. Tests before live model work

- A one-to-one join gives exact expected rows and unmatched counts.
- An allowed one-to-many relationship preserves the expected repeated rows.
- An unapproved many-to-many relationship fails before a large output is produced.
- Appending compatible monthly files preserves values and total row counts.
- Same column names with different meanings or units do not cause a guessed join.
- Missing keys, leading zeros, incompatible types, and overlapping column names are checked.
- Source-row mapping explains every output row, including unmatched records.
- A model selecting a nonexistent key or an extra unsupplied file is rejected.
- Real MCP calls accept produced datasets from earlier steps through checked references.
- Retry, cancellation, changed inputs, foreign references, and database failure preserve
  the shared storage and operation rules.

## 9. Implementation checklist

- [ ] Define typed combination rules, recipe, match checks, mappings, and result.
- [ ] Implement bounded join/append operations and output-size estimation.
- [ ] Add key/relationship validation and the bounded LLM job loop.
- [ ] Publish `combine_data` through its own official-SDK MCP server.
- [ ] Connect list bindings, produced-dataset registration, model calls, and receipts.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests.
- [ ] Run a bounded live-model smoke only after those tests pass.

Complete when combined data has justified matches, checked counts, traceable source rows,
and usable registered outputs without silently losing or multiplying records.
