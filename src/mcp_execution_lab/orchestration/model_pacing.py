"""Optional shared spacing between model calls; waiting uses the run's time allowance."""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from .models import OrchestrationError
from .storage import now


class ModelPacer:
    def __init__(self, gap_seconds=0):
        self.gap_seconds = gap_seconds
        self.lock = asyncio.Lock()
        self.finished = None

    @asynccontextmanager
    async def slot(self, run_id, stage, store, budget):
        if not self.gap_seconds:
            yield
            return
        budget.check()
        try:
            await asyncio.wait_for(self.lock.acquire(), timeout=budget.remaining)
        except TimeoutError as exc:
            raise OrchestrationError(
                "BUDGET_EXHAUSTED", "Run ended while waiting for a model."
            ) from exc
        try:
            budget.check()
            # Saved completion times preserve spacing when plan/execute use new components.
            calls = await store.list_records(run_id, "model_call")
            saved = [
                row["payload"]["finished_at"] for row in calls if row["payload"].get("finished_at")
            ]
            delay = (
                max(0, self.gap_seconds - (time.perf_counter() - self.finished))
                if self.finished is not None
                else 0
            )
            if saved:
                age = (
                    datetime.now(UTC) - max(datetime.fromisoformat(value) for value in saved)
                ).total_seconds()
                delay = max(delay, self.gap_seconds - age)
            if delay:
                if delay >= budget.remaining:
                    raise OrchestrationError(
                        "BUDGET_EXHAUSTED", "Model spacing exceeds the remaining run time."
                    )
                record = {
                    "stage": stage,
                    "gap_seconds": self.gap_seconds,
                    "planned_seconds": delay,
                    "status": "WAITING",
                    "started_at": now(),
                }
                wait_id = await store.put(run_id, "model_wait", record)
                started = time.perf_counter()
                try:
                    deadline = started + delay
                    while (remaining := deadline - time.perf_counter()) > 0:
                        await asyncio.sleep(remaining)
                    budget.check()
                    record["status"] = "SUCCEEDED"
                except BaseException as exc:
                    record["status"] = (
                        "INTERRUPTED" if isinstance(exc, asyncio.CancelledError) else "FAILED"
                    )
                    raise
                finally:
                    await store.finish(
                        run_id,
                        wait_id,
                        record
                        | {"waited_seconds": time.perf_counter() - started, "finished_at": now()},
                    )
            budget.check()
            try:
                yield
            finally:
                self.finished = time.perf_counter()
        finally:
            self.lock.release()
