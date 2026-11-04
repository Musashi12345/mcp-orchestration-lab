"""Provider-reported counts only; cached/reasoning counts are subsets, not extras."""

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens")


def token_usage(raw):
    """Keep independently known fields when another count is missing or invalid."""
    raw = raw if isinstance(raw, dict) else {}
    counts = {
        key: value if type(value := raw.get(key)) is int and value >= 0 else None
        for key in TOKEN_FIELDS
    }
    for subset, parent in (
        ("cached_input_tokens", "input_tokens"),
        ("reasoning_output_tokens", "output_tokens"),
    ):
        if (
            counts[subset] is not None
            and counts[parent] is not None
            and counts[subset] > counts[parent]
        ):
            counts[subset] = None
    complete = all(counts[key] is not None for key in TOKEN_FIELDS[:2])
    return {
        **counts,
        "tokens": counts["input_tokens"] + counts["output_tokens"] if complete else None,
        "known_tokens": sum(counts[key] or 0 for key in TOKEN_FIELDS[:2]),
        "usage_complete": complete,
    }


def call_phase(role):
    return {
        "initial_planner": "planning",
        "planner": "planning",  # Older saved calls used this role.
        "worker": "agent",
        "replanner": "review",
    }.get(role, "unclassified")


def summarize_tokens(calls):
    """Every call contributes, including failed, interrupted, and active attempts."""
    result = {
        "model_calls": len(calls),
        "calls_by_status": {},
        "unknown_usage_calls": sum(not call["usage_complete"] for call in calls),
        "known_tokens": sum(call["known_tokens"] for call in calls),
    }
    for call in calls:
        status = call.get("status", "UNKNOWN")
        result["calls_by_status"][status] = result["calls_by_status"].get(status, 0) + 1
    for key in TOKEN_FIELDS:
        missing = sum(call[key] is None for call in calls)
        known = sum(call[key] or 0 for call in calls)
        result[key] = None if missing else known
        result["known_" + key] = known
        result["unknown_" + key + "_calls"] = missing
    result["usage_complete"] = result["unknown_usage_calls"] == 0
    result["tokens"] = result["known_tokens"] if result["usage_complete"] else None
    return result
