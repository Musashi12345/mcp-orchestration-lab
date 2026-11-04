import asyncio

import pytest

from mcp_execution_lab.orchestration.budget import Budget
from mcp_execution_lab.orchestration.models import Limits, OrchestrationError, Record
from mcp_execution_lab.orchestration.tokens import token_usage


class Answer(Record):
    value: int


@pytest.mark.parametrize("invalid", [None, -1, True, "12", 1.5])
def test_missing_or_invalid_counts_keep_the_known_field(invalid):
    counts = token_usage({"input_tokens": 12, "output_tokens": invalid})
    assert counts["input_tokens"] == counts["known_tokens"] == 12
    assert counts["output_tokens"] is counts["tokens"] is None
    assert not counts["usage_complete"]


def test_optional_counts_are_subsets_and_never_added_to_total():
    counts = token_usage(
        {
            "input_tokens": 12,
            "output_tokens": 4,
            "cached_input_tokens": 10,
            "reasoning_output_tokens": 3,
        }
    )
    assert counts["tokens"] == counts["known_tokens"] == 16
    assert counts["cached_input_tokens"] == 10 and counts["reasoning_output_tokens"] == 3
    counts = token_usage(
        {
            "input_tokens": 12,
            "output_tokens": 4,
            "cached_input_tokens": 13,
            "reasoning_output_tokens": 5,
        }
    )
    assert counts["tokens"] == 16
    assert counts["cached_input_tokens"] is counts["reasoning_output_tokens"] is None


def test_partial_usage_survives_budget_restore_and_still_limits_spending():
    budget = Budget(Limits(max_observed_tokens=12))
    budget.observe({"input_tokens": 12})
    assert budget.summary()["observed_tokens"] is None
    assert budget.summary()["known_observed_tokens"] == 12
    restored = Budget(budget.limits)
    restored.restore(budget.summary())
    with pytest.raises(OrchestrationError, match="token allowance"):
        restored.model()


@pytest.mark.parametrize("outcome", ["success", "format", "service", "timeout", "cancel"])
async def test_call_records_preserve_usage_on_failure_and_cancellation(lab, outcome):
    run_id = await lab.store.create_run({"mode": "D2"})
    raw = {
        "input_tokens": 12,
        "output_tokens": 4,
        "cached_input_tokens": 10,
        "reasoning_output_tokens": 3,
    }

    async def generate(request, directory):
        active = (await lab.store.list_records(run_id, "model_call"))[0]["payload"]
        assert active["status"] == "RUNNING"
        assert active["token_usage"]["tokens"] is None
        if outcome == "timeout":
            raise TimeoutError("Provider timed out")
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return {
            "content": {"value": "bad" if outcome == "format" else 1},
            "usage": raw,
            "failure": "Provider failure" if outcome == "service" else None,
        }

    lab.client.generate = generate
    if outcome == "success":
        assert (await lab.model.ask(run_id, "review", Answer, {})).value == 1
    else:
        error = {
            "format": OrchestrationError,
            "service": OrchestrationError,
            "timeout": TimeoutError,
            "cancel": asyncio.CancelledError,
        }[outcome]
        with pytest.raises(error):
            await lab.model.ask(run_id, "review", Answer, {})
    call = (await lab.store.list_records(run_id, "model_call"))[0]["payload"]
    assert call["phase"] == "review" and call["finished_at"]
    if outcome in {"timeout", "cancel"}:
        assert call["token_usage"]["tokens"] is None
        assert lab.budget.summary()["observed_tokens"] is None
    else:
        assert call["result"]["usage"] == raw
        assert call["token_usage"]["tokens"] == lab.budget.tokens == 16
    assert (
        call["status"]
        == {
            "success": "SUCCEEDED",
            "format": "FAILED",
            "service": "FAILED",
            "timeout": "FAILED",
            "cancel": "INTERRUPTED",
        }[outcome]
    )
