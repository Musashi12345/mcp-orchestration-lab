# Report Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `evidence`, optional `charts`, and optional `style`.
The worker produces Markdown and a claim-source JSON file from checked JSON facts and PNG
charts. Numeric prose must cite saved fact IDs. PDF, Word, remote publication, unrestricted
tables, and a separate public `options` argument are not included. See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md). This agent writes from supplied saved evidence.
It does not invent missing analysis or judge the run using private research answers.

## 1. Job and when to use it

Turn available findings into a clear answer, with useful tables/charts and honest limits.
It is optional when an earlier agent already returns an adequate answer. It can also
summarize a saved profile without requiring an Analysis or Prediction call.

Example job: "Explain the regional sales change in simple English. Use the supplied
figures and charts, state missing data limits, and distinguish findings from suggestions."

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `report` |
| MCP server name/version | `report`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.report.server` |
| Public tool | `create_report` |
| Published description | Write a plain-English report from registered findings and charts, linking claims to their evidence and stating unresolved questions. |

Use a separate official-SDK MCP process over stdio. Discovery lists the typed report tool
without reading evidence, writing a report, or calling the LLM.

Implemented stdio entry point:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.report.server
```

Configure the module through the existing server list. The main planner chooses when
report writing is needed. The MCP description must not say this tool is always the last
step. Use the common environment, trusted metadata, and conservative retry hints.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required writing task, checked against the saved assigned job. |
| `evidence` | Required nonempty list of registered structured result/finding references from this run. |
| `charts` | Optional registered chart references tied to the supplied evidence. |
| `style` | Typed audience, length, language, and requested sections; default to clear English. |
| `options` | Bounds on evidence size, report length, tables, images, and supported output formats. |

Evidence must have usable source versions and checked facts. Validate nested chart/file
references too. A raw LLM paragraph alone does not establish a number. If the job requires
new calculations, return the missing work requirement rather than doing it without a plan.
Use the shared list/object bindings to assemble evidence from several earlier steps.

## 4. Published result

Use the common result fields. Typed `details` contains:

- The direct answer and what part of the user's question it addresses.
- Report sections, tables, and chart references built from a checked draft.
- A claim-to-evidence map identifying the fact or source result behind each material claim.
- Data/method limits, unresolved questions, and unsupported requested conclusions.
- Suggestions clearly labeled as suggestions rather than measured findings.
- Any parts omitted because of size or evidence limits.

Register `report.md`, `report_draft.json`, and `claim_sources.json`. The first version
produces Markdown plus structured JSON, with links to registered charts/tables. PDF,
Word, presentations, remote publication, and sending reports are separate extensions.
Return the Markdown reference and a short answer preview in the structured result.

## 5. Internal work and LLM calls

1. Verify evidence, file versions, ownership, chart mappings, and output limits.
2. Build a bounded evidence bundle with fact IDs, exact values, units, warnings, and sources.
3. Ask the LLM for a structured report draft: paragraphs, tables, chart placements,
   evidence references, assumptions, and remaining questions.
4. Check every referenced fact and material claim. Numeric text uses fact references or
   placeholders rendered from stored values; do not trust numbers invented in prose.
5. Use the bounded correction allowance if needed. If a claim still lacks support,
   omit it with an explicit limit or return a non-completed outcome when it is essential.
6. Render Markdown using checked functions, register the report/source map, and save the receipt.

One draft plus a checked correction is normally enough; no second model call is required
merely to consume an allowance. Evidence selection and report structure can use the LLM,
while rendering and number insertion remain checked operations.

## 6. Limits and failure behavior

- Never change a total, denominator, date range, unit, class label, or model score to fit a story.
- Do not invent causes, external facts, or statistical certainty missing from the evidence.
- Preserve important contradictions, weak prediction results, excluded rows, and unknown usage.
- Refer to the exact source versions; old and revised findings cannot be mixed without explanation.
- Do not silently omit evidence needed to answer the question when the prompt-size limit is reached.
- Use only registered local chart/table references. Escape untrusted content in rendered output.
- Do not embed executable scripts or follow instructions contained inside evidence text.
- Return `NEEDS_INPUT` or `UNSUPPORTED` when required evidence or a requested format is unavailable.
- A complete report can describe an incomplete analysis honestly; it must not label that analysis
  or the overall research task successful merely because report writing finished.
- Never call another agent, run a new data investigation, or access private evaluator information.

## 7. Records saved during work

Save input evidence hashes, the bounded evidence bundle, model requests/replies, draft
versions, rejected claims, numeric checks, corrections, source mappings, and file publication
while the job is running. Link the report to all findings and charts it actually uses.

The shared service owns model usage and receipts. A repeated known operation returns the
same accepted report reference without another draft call. Failed drafts and partial files
remain recorded without being presented as final reports.

## 8. Tests before live model work

- A known evidence bundle produces correct displayed numbers, units, and source links.
- A draft with an invented total or unknown fact ID is rejected before publication.
- Conflicting findings remain visible instead of being silently resolved by prose.
- A weak prediction is described with its actual comparison and limitations.
- Missing evidence produces a stated gap; the tool does not fabricate an answer.
- Registered chart/table links resolve to the correct run and content version.
- User text containing Markdown/HTML or instruction-like content cannot create active content
  or redirect the worker's access.
- Large evidence bundles have recorded selection/omission limits.
- A profile-only reporting call works without forcing Analysis or Prediction.
- Real MCP, PostgreSQL stage visibility, cross-run checks, cancellation, partial writes,
  shared model budgets, and known-receipt reuse pass the common checks.

## 9. Implementation checklist

- [ ] Define typed evidence bundles, draft blocks, source maps, styles, and result.
- [ ] Implement checked fact substitution, claim validation, and Markdown rendering.
- [ ] Add the bounded drafting/correction prompt and retain its evidence bundle.
- [ ] Publish `create_report` through its own official-SDK MCP server.
- [ ] Connect artifact-type checks, shared model calls, live records, and receipts.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests.
- [ ] Run and retain a bounded live-model smoke only after those tests pass.

Complete when the report is readable, every important number and finding has a checked
source, and its limits remain clear without requiring a fixed earlier agent sequence.
