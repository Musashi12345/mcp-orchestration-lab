"""A shared allowance for planning and execution, without tool preferences."""

import time

from .models import Limits, OrchestrationError


class Budget:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.started = time.monotonic()
        self.model_calls = 0
        self.tool_attempts = 0
        self.tokens = 0
        self.usage_complete = True

    @property
    def remaining(self):
        return max(0, self.limits.run_seconds - (time.monotonic() - self.started))

    def check(self):
        if not self.remaining or self.tokens > self.limits.max_observed_tokens:
            raise OrchestrationError("BUDGET_EXHAUSTED", "Run allowance exhausted.")

    def model(self):
        self.check()
        if self.tokens >= self.limits.max_observed_tokens:
            raise OrchestrationError("BUDGET_EXHAUSTED", "Observed token allowance exhausted.")
        if self.model_calls >= self.limits.max_model_calls:
            raise OrchestrationError("BUDGET_EXHAUSTED", "Model-call allowance exhausted.")
        self.model_calls += 1

    def tool(self):
        self.check()
        if self.tool_attempts >= self.limits.max_tool_attempts:
            raise OrchestrationError("BUDGET_EXHAUSTED", "Tool-attempt allowance exhausted.")
        self.tool_attempts += 1

    def observe(self, usage):
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0
            for key in ("input_tokens", "output_tokens")
        ):
            self.usage_complete = False
            return
        self.tokens += usage["input_tokens"] + usage["output_tokens"]
        self.check()

    def summary(self):
        return {
            "model_calls": self.model_calls,
            "tool_attempts": self.tool_attempts,
            "observed_tokens": self.tokens if self.usage_complete else None,
            "known_observed_tokens": self.tokens,
            "usage_complete": self.usage_complete,
            "elapsed_seconds": time.monotonic() - self.started,
            "remaining_seconds": self.remaining,
        }

    def restore(self, summary):
        self.model_calls = summary["model_calls"]
        self.tool_attempts = summary["tool_attempts"]
        self.tokens = summary["known_observed_tokens"]
        self.usage_complete = summary["usage_complete"]
        self.started = time.monotonic() - summary["elapsed_seconds"]

    def allowance(self):
        return {
            "model_calls": max(0, self.limits.max_model_calls - self.model_calls),
            "tool_attempts": max(0, self.limits.max_tool_attempts - self.tool_attempts),
            "observed_tokens": max(0, self.limits.max_observed_tokens - self.tokens),
            "seconds": self.remaining,
            "token_usage_complete": self.usage_complete,
        }
