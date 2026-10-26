"""Continuation scopes, byte bounds, and review schemas without executing Python."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mcp_execution_lab.orchestration.models import OrchestrationError, ProgramReviewDecision
from mcp_execution_lab.orchestration.reviews import checked_snapshot


async def setup_snapshot(lab):
    run_id = await lab.store.create_run({"request": "Snapshot checks", "exploratory": True})
    ref = await lab.files.put_json(run_id, {"checked": True})
    runtime = SimpleNamespace(
        active=SimpleNamespace(run_id=run_id),
        snapshots={ref.id: ref},
        files=lab.files,
        budget=lab.budget,
    )
    return runtime, ref


async def test_continuation_contains_checked_envelopes_and_no_host_paths(lab):
    runtime, ref = await setup_snapshot(lab)
    assert await checked_snapshot(runtime, [ref.id]) == {
        ref.id: {
            "state": "SUCCEEDED",
            "value": {"checked": True},
            "output": ref.model_dump(),
            "error": None,
        }
    }
    assert await checked_snapshot(runtime, []) == {}


async def test_same_run_unreceived_artifacts_are_not_snapshot_candidates(lab):
    runtime, ref = await setup_snapshot(lab)
    private = await lab.files.put_json(ref.run_id, {"undisclosed": True})
    for selected in ([private.id], [ref.id, ref.id], ["guessed"]):
        with pytest.raises(OrchestrationError) as error:
            await checked_snapshot(runtime, selected)
        assert error.value.code == "PLAN_INVALID"


@pytest.mark.parametrize("case", ["cross_run", "changed", "nested"])
async def test_invalid_snapshot_content_and_nested_references_fail(lab, case):
    runtime, ref = await setup_snapshot(lab)
    if case == "cross_run":
        other_run = await lab.store.create_run({"request": "Other"})
        ref = await lab.files.put_json(other_run, {})
        runtime.snapshots[ref.id] = ref
    elif case == "changed":
        path = await lab.files.checked_path(ref.run_id, ref)
        path.write_text('{"changed": true}', encoding="utf-8")
    else:
        nested = ref.model_dump() | {"sha256": "a" * 64}
        ref = await lab.files.put_json(ref.run_id, {"nested": nested})
        runtime.snapshots[ref.id] = ref
    with pytest.raises(OrchestrationError) as error:
        await checked_snapshot(runtime, [ref.id])
    assert error.value.code in {"FILE_OWNERSHIP", "FILE_CHANGED", "FILE_REFERENCE"}


async def test_aggregate_continuation_bytes_are_bounded(lab):
    runtime, ref = await setup_snapshot(lab)
    refs = [await lab.files.put_json(ref.run_id, {"data": "x" * 600}) for _ in range(2)]
    runtime.snapshots = {item.id: item for item in refs}
    lab.budget.limits = lab.budget.limits.model_copy(update={"max_result_bytes": 1024})
    assert await checked_snapshot(runtime, [refs[0].id])
    with pytest.raises(OrchestrationError, match="shared byte allowance"):
        await checked_snapshot(runtime, [item.id for item in refs])


@pytest.mark.parametrize(
    "extra",
    [
        {"preserve": ["saved"]},
        {"recoveries": {"new": ["failed"]}},
        {"replacement": {"source": "x", "outputs": ["answer"]}},
    ],
)
def test_keep_cannot_smuggle_replacement_work(extra):
    with pytest.raises(ValidationError):
        ProgramReviewDecision(decision="KEEP", reason="Continue", **extra)


def test_python_review_rejects_a_dag_replacement():
    with pytest.raises(ValidationError):
        ProgramReviewDecision.model_validate(
            {
                "decision": "REVISE",
                "reason": "Wrong representation",
                "breakdown": {"selection": {"tool_keys": [], "reasons": []}, "subtasks": []},
                "replacement": {
                    "steps": [],
                    "outputs": {"answer": {"kind": "literal", "value": 1}},
                },
            }
        )
