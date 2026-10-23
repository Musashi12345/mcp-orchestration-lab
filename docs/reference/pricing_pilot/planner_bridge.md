# Local Codex planner bridge

The implemented route is:

```text
CLI / dashboard -> PlanningSession -> Codex CLI (saved ChatGPT login)
                <- structured Candidate / ReplanDecision + reported usage
                 -> validated DAG / isolated Python -> shared broker -> MCP workers
```

Codex supplies plans. The research application executes them and controls artifacts,
checkpoint barriers, tool recovery and grading. At a checkpoint, the request includes the
active source, observed receipts/diagnostics and remaining budgets so KEEP can assess the
work still scheduled. A planner never receives evaluator cases,
fault schedules, the private effect ledger or arbitrary fixture paths. Python containers
receive only source, public artifact handles and a normalized checkpoint snapshot over
length-prefixed JSON frames.

## Supported local route

Sign in with `codex login`, check `codex login status`, and inspect available models using
`lab.ps1 models`. The adapter requires an exact model ID. `configs/codex.yaml` uses the
account's discovered `gpt-6.1-sol`, low reasoning, at most four requests per episode, a
90-second call timeout and an observed 60,000-token episode ceiling. A batch/dashboard
invocation has a separate 16-call ceiling in that example configuration. These values are
configuration, not a request to automatically start a model benchmark.

Every request uses a fresh ephemeral `codex exec` with JSON events, a strict output schema,
read-only sandbox, ignored user configuration and disabled shell, browser, app/plugin,
subagent and code-host capabilities. Actual emitted tool items fail the episode. The
CLI's disabled-code-host diagnostic is retained and is not itself a tool action.

The app uses login status text; it never opens authentication files, copies a bearer token,
or injects a subscription credential into an API client. Follow the installed CLI's login
flow if authentication expires. The app does not host a public Codex proxy.

CLI event logs and provider usage stay under each run's `model_calls/`. Input/output totals
come from reported usage; cached/reasoning classes are kept without inventing a billing
formula. Subscription USD cost is null. An observed token cap can halt later calls and
reject the current candidate, but cannot reserve or hard-limit a CLI generation. The
response token hint asks for brevity and is not a provider-enforced ceiling.

[Official authentication documentation](https://learn.chatgpt.com/docs/auth),
[non-interactive structured output](https://learn.chatgpt.com/docs/non-interactive-mode),
[app-server model discovery](https://learn.chatgpt.com/docs/app-server).

## Bring your own router

Set `planner.provider: command` and an explicit `planner.command` argv list in a local YAML
configuration. The host launches that trusted command without a shell, sends one
`planner.v1` request JSON on stdin and closes stdin. The command returns exactly one JSON
object on stdout:

```json
{
  "content": {"representation": "dag", "source": "...validated DAG JSON..."},
  "usage": {"input_tokens": 120, "output_tokens": 80, "cached_input_tokens": 0},
  "request_id": "router-request-id",
  "cost_usd": null
}
```

For a replanning request, `content` is `{decision,reason,replacement}` with a KEEP, REVISE
or STOP decision; `replacement` is null or a Candidate with the same representation.
The request includes public task intent/constraints, tool contracts, snapshot/observations,
representation and format-error feedback. No hidden grading data is sent.

The command has a deadline, bounded stdout/stderr and a return-code check. Auditable
non-negative input/output token counts are mandatory. Logs, attempted calls and failures
are retained. The configured command itself is trusted host code: keep secrets in its
own credential storage, not argv/YAML. A router may invoke Codex, but generated programs
still run through the isolated executor and common runtime.
