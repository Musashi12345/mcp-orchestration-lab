# CSV model bridge

The current implementation is `orchestration/model_clients.py`. Main planning, D2
reviews, and worker requests all pass through `ModelCalls.ask()` and the shared run
allowance. The bridge no longer imports pricing-world errors or old plan/program types.

```text
Planner / reviewer / worker support
  -> ModelCalls: save request and start record
  -> CodexPlanner or CommandPlanner
  <- structured content and reported usage
  -> validate current record type and save outcome
```

The request protocol is `orchestration.v1`. Fields include `role`, `stage`, instructions,
`response_schema`, the inner `record_schema`, reference rules, context, limits, and
remaining allowance. The provider's outer structured response contains `content_json`;
that string is checked against the inner record type. It is a plan, recipe, review, or
explanation record, not executable analysis code.

## Codex route

Use `model.provider: codex` and an exact `model.model_id` in the agent settings. The bridge
checks CLI login status, requires a supplied response schema, starts a fresh ephemeral
read-only invocation, supplies JSON output rules, and disables tool features. Emitted
tool activity outside the bridge contract is flagged. Authentication stays with the CLI;
the application does not read authentication files or extract an API key.

The app's `models` command retains local model discovery:

```powershell
.\scripts\lab.ps1 models
```

Model IDs in checked-in settings are configuration values, not a guarantee of availability.
Live requests consume subscription allowance. Cost in USD stays unknown. Usage is observed
after replies; the application does not claim a provider-enforced output-token maximum.
CLI event logs, request schemas, and stderr are retained in the run's model-call folder.

## Command route

Set `model.provider: command` and an explicit `model.command` argument list. The host starts
that trusted command without a shell, sends one request JSON on stdin, and closes stdin.
The command returns one JSON object on stdout:

```json
{
  "content": {"content_json": "{...the requested record...}"},
  "usage": {"input_tokens": 120, "output_tokens": 80},
  "request_id": "router-request-id",
  "cost_usd": null
}
```

The adapter requires `content`, `usage`, and `request_id`; missing/unknown usage remains
unknown in accounting rather than being treated as zero. It bounds stdout/stderr, checks
return codes, and applies timeouts. The current subprocess cleanup kills the direct
child; it is not the managed service script's Windows process-tree cleanup.

A custom router is trusted host code and must keep credentials in its own local storage,
not model context, YAML arguments, or stdout diagnostics. A separate custom routing
application is not supplied by this adapter. It cannot enable executing generated Python
inside the CSV app: that execution path has been removed.
