"""Read-only token reports from saved calls; no model prompts or answers are exported."""

from collections import defaultdict

from ..orchestration.tokens import call_phase, summarize_tokens, token_usage


def model_call_rows(run, records):
    rows = []
    for record in records:
        if record["kind"] != "model_call":
            continue
        payload = record["payload"]
        result = payload.get("result")
        result = result if isinstance(result, dict) else {}
        role = payload.get("role", "unknown")
        stage = payload.get("stage", "unknown")
        parts = stage.split(".")
        rows.append(
            {
                "run_id": run["id"],
                "mode": run["payload"].get("mode"),
                "call_id": record["id"],
                "parent_id": payload.get("parent_id"),
                "status": payload.get("status", "UNKNOWN"),
                "role": role,
                "stage": stage,
                "phase": call_phase(role),
                "agent": parts[1] if role == "worker" and len(parts) == 3 else None,
                "provider": result.get("provider") or payload.get("provider"),
                "model_id": result.get("model_id") or payload.get("model_id"),
                "is_model": payload.get("is_model"),
                "request_id": result.get("request_id"),
                "started_at": record["created_at"],
                "finished_at": payload.get("finished_at"),
                **token_usage(result.get("usage")),
            }
        )
    return rows


def token_report(calls):
    phases = {phase: [] for phase in ("planning", "agent", "review", "unclassified")}
    agents = defaultdict(list)
    for call in calls:
        phases[call["phase"]].append(call)
        if call["phase"] == "agent":
            agents[call["agent"] or "unknown"].append(call)
    return {
        **summarize_tokens(calls),
        "by_phase": {phase: summarize_tokens(values) for phase, values in phases.items()},
        "by_agent": {agent: summarize_tokens(values) for agent, values in agents.items()},
    }
