# Prediction Agent: build plan

Date: 2026-10-21. Status: first version implemented; real-MCP tests use fixed model replies.

Current public arguments are `job`, `dataset`, optional `target`, `time_column`, `rules`,
and `prediction_data`. Supported methods are linear numeric prediction, nearest-centroid
label prediction, and last-value time forecasting. Saved checks include held-back rows,
a reference score, and safe JSON settings. No confidence intervals, advanced model search,
deployment, or separate public `options` argument are included. See [running instructions](Running.md).

The design below retains broader goals for later versions; discovered tool schemas define
the current contract. Unchecked checklist items are not claims of completed coverage.

Follow the [shared agent plan](README.md). This agent is optional: explaining past data
does not automatically require a prediction, and not every CSV supports a useful model.

## 1. Job and when to use it

Build and check a prediction when the assigned question asks for one. Explain whether it
does better than a simple reference method and what its limits are.

Examples: "Predict a numeric outcome from the available past records" or "Estimate next
month's demand from the historical series and show the error on held-back past periods."

The first build will support a small published set: simple numeric prediction, label
prediction, and simple time-series reference methods. Advanced forecasting, unrestricted
model searches, deployment, and ongoing training remain later work. Advertise a method
only after its checked implementation and tests exist.

## 2. Its MCP server

| Item | Planned value |
|---|---|
| Server ID | `prediction` |
| MCP server name/version | `prediction`, initially `0.1.0` |
| Python module | `mcp_execution_lab.agents.prediction.server` |
| Public tool | `predict_data` |
| Published description | Build and check a bounded prediction from registered data, comparing it with a simple reference method and reporting errors and limitations. |

Run as its own official-SDK MCP process over stdio. Publish typed inputs, allowed methods,
and typed outputs during discovery without training or making a model call.

Implemented stdio entry point:

```powershell
.\.venv\Scripts\python.exe -m mcp_execution_lab.agents.prediction.server
```

The existing server configuration and adapter start and call this module when the planner
selects it. Use the shared environment, trusted metadata, and conservative retry hints.
Private training functions do not become extra agent servers.

## 3. Published inputs

| Argument | Rule |
|---|---|
| `job` | Required assigned prediction task, matched to the saved job. |
| `dataset` | Required registered training/history CSV reference from this run. |
| `target` | Column to predict; can be proposed by the LLM only when the job identifies it clearly. |
| `time_column` | Optional column required when the task is time-based. |
| `prediction_data` | Optional registered CSV containing rows to predict after checks; must have the required inputs. |
| `rules` | Typed allowed input columns, prediction horizon, split rules, metric choice, and seed/settings. |
| `options` | Allowed methods and limits on fitting attempts, features, rows, computation, and outputs. |

Use only the supplied data and public rules. If the target or time meaning is unclear,
request information. Do not search the file directory or fetch a dataset from the web.
If earlier evidence is accepted later, add it as an explicit versioned argument.

## 4. Published result

Use the common result fields. Typed `details` contains:

- Prediction type, target, permitted input columns, and checks for unsuitable inputs.
- Exact data split: which records trained the model and which checked its predictions.
- The simple reference method, candidate method/settings, and actual measured errors.
- Data excluded, missing-value handling, failed fitting attempts, and computation used.
- Predictions, relevant uncertainty where a supported method can calculate it, and limits.
- Whether the result supports use for the assigned purpose; poor results must remain visible.

Register `prediction_recipe.json`, `split_manifest.json`, `metrics.json`, and prediction
CSVs with source row IDs and split labels. Include actual outcomes only where known.
Do not put invented actual outcomes into future predictions.

The first build saves model settings, supported parameters, library versions, and seeds
needed to reproduce the fit. A reusable model binary is not required. Do not introduce
untrusted pickle loading; add model-file export only after a safe format is specified.

## 5. Internal work and LLM calls

1. Verify data, target, public task rules, and whether there is enough usable information.
2. Ask the LLM for a structured choice among published methods, inputs, split, and metrics.
3. Validate the proposal. Save and freeze the split before evaluating candidate methods.
4. Fit the simple reference method and the allowed candidate using handwritten routines.
   Bound all trials; save settings, failures, predictions, and metrics as they happen.
5. Compare results on held-back records. Never adjust the split to improve a displayed score.
6. Ask the LLM to explain the actual comparison, limitations, and appropriate use. Check
   numerical claims and register the result/receipt.

For time data, train on earlier records and check on later records. Prevent information
from the future, including future target-derived columns, from entering training inputs.
Fit data-preparation rules on training records only, then apply them to held-back data.

Example metrics are mean absolute error for numeric predictions and suitable label
metrics with class counts for classification. Publish the precise supported metrics,
their units, and edge-case handling. A percentage error with a zero actual value needs
an explicit rule; do not silently divide by zero or omit difficult records.

## 6. Limits and failure behavior

- Do not treat a random record identifier as useful evidence without a checked reason.
- Check for columns that reveal the answer or would be unavailable at prediction time.
- Do not evaluate on the same records used for fitting and present that as future accuracy.
- A small, single-class, sparse, or unsuitable dataset can lead to `UNSUPPORTED` with reasons.
- Ambiguous targets or split requirements return `NEEDS_INPUT`.
- Do not claim that a method is useful just because fitting completed; compare the reference.
- Do not manufacture a confidence range or a causal explanation from model prose.
- No unbounded tuning, generated training scripts, outside model downloads, or calls to other agents.
- Preserve weak scores and failed trials; a worker cannot label the whole research task successful.

## 7. Records saved during work

Save source versions, proposed/accepted recipes, split records, each fitting attempt,
reference/candidate settings, model calls, predictions, errors, metrics, and artifact
publication. All records belong to the same worker call and tool attempt.

Shared model-call reservations and separate computation limits apply throughout training.
A transport retry cannot silently start another paid model request or training attempt
when the original outcome is unknown. Known completed operations return their saved receipt.

## 8. Tests before live model work

- A known synthetic numeric task has independently checked reference and candidate errors.
- A label task handles class counts, predictions, and its stated metric correctly.
- Time-based data cannot put later records into earlier training periods.
- A deliberately answer-revealing input is excluded or rejected under the saved rule.
- Data preparation is fitted using only training data; held-back changes cannot alter it.
- Small data, missing targets, a single class, and invalid time columns give honest outcomes.
- A worse-than-reference result is retained and described accurately.
- A model requesting unsupported methods or more trials than allowed is rejected.
- Fixed input/settings/seed produce repeatable calculations within stated numerical tolerance.
- Real MCP, live PostgreSQL stages, safe files, cancellation, budgets, and receipts pass
  the common integration checks.

## 9. Implementation checklist

- [ ] Define typed tasks, method choices, split rules, metrics, predictions, and result.
- [ ] Implement the small published method set and simple reference methods.
- [ ] Check the data split, keep future answers out of training, and bound computation.
- [ ] Add the worker LLM choice/explanation loop and check its numbers against saved facts.
- [ ] Publish `predict_data` through its official-SDK MCP server.
- [ ] Connect shared records, model calls, files, and receipts; pin new library versions.
- [ ] Pass deterministic, real-MCP, and native-PostgreSQL tests before a bounded live smoke.

Complete when predictions have an honest held-back check, a simple comparison, a saved
method and data split, and limits the user can understand.
