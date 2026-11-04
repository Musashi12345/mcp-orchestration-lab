import csv
import json

from mcp_execution_lab.evaluation.batch import report_batch
from mcp_execution_lab.evaluation.tokens import model_call_rows, token_report
from mcp_execution_lab.orchestration.storage import Store


async def test_four_mode_reports_keep_corrections_failures_partial_and_unstarted_runs(tmp_path):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    episodes = []
    try:
        for mode in ("D1", "D2", "P1", "P2"):
            episode = {"task_id": "example", "repeat": 1, "mode": mode, "status": "QUEUED"}
            episodes.append(episode)
            if mode == "P2":
                continue
            run_id = await store.create_run({"mode": mode, "is_model": False})
            episode.update(run_id=run_id, status="FAILED")
            definitions = {
                "D1": [("initial_planner", "main_task", "SUCCEEDED", 10, 4)],
                "D2": [
                    ("initial_planner", "dag", "FAILED", 10, 2),
                    ("initial_planner", "dag", "SUCCEEDED", 6, 2),
                    ("replanner", "review", "INTERRUPTED", None, None),
                ],
                "P1": [("worker", "worker.analysis.recipe", "FAILED", 5, None)],
            }
            for role, stage, status, input_count, output_count in definitions[mode]:
                await store.put(
                    run_id,
                    "model_call",
                    {
                        "role": role,
                        "stage": stage,
                        "status": status,
                        "provider": "fixed",
                        "model_id": "fixture",
                        "is_model": False,
                        "request": {"secret_context": "DO-NOT-EXPORT"},
                        "result": {
                            "content": "DO-NOT-EXPORT",
                            "usage": {
                                "input_tokens": input_count,
                                "output_tokens": output_count,
                                "cached_input_tokens": 3 if input_count is not None else None,
                                "reasoning_output_tokens": 1 if output_count is not None else None,
                            },
                        },
                    },
                )
        (tmp_path / "manifest.json").write_text(
            json.dumps(
                {
                    "batch_id": "fixture",
                    "suite_sha256": "suite",
                    "grader_sha256": "grader",
                    "episodes": episodes,
                }
            )
        )
        summary = await report_batch(store, tmp_path)
        assert summary["modes"]["P2"]["token_usage"] is None
        d1 = summary["modes"]["D1"]["token_usage"]
        assert d1["tokens"] == 14 and d1["cached_input_tokens"] == 3
        d2 = summary["modes"]["D2"]["token_usage"]
        assert d2["tokens"] is None and d2["known_tokens"] == 20
        assert d2["model_calls"] == 3 and d2["unknown_usage_calls"] == 1
        assert d2["by_phase"]["planning"]["tokens"] == 20
        assert d2["by_phase"]["review"]["tokens"] is None
        p1 = summary["modes"]["P1"]["token_usage"]
        assert p1["input_tokens"] == p1["known_tokens"] == 5
        assert p1["output_tokens"] is p1["tokens"] is None
        assert p1["by_agent"]["analysis"]["model_calls"] == 1
        for name in (
            "model_calls.csv",
            "tokens_by_mode.csv",
            "episodes.csv",
            "summary.json",
            "report.md",
        ):
            assert "DO-NOT-EXPORT" not in (tmp_path / name).read_text()
        with (tmp_path / "model_calls.csv").open(newline="") as stream:
            calls = list(csv.DictReader(stream))
        assert len(calls) == 5
        assert sum(call["status"] == "FAILED" for call in calls) == 2
        assert {call["mode"] for call in calls} == {"D1", "D2", "P1"}
        with (tmp_path / "tokens_by_mode.csv").open(newline="") as stream:
            totals = list(csv.DictReader(stream))
        assert (
            next(row for row in totals if row["mode"] == "D2" and row["phase"] == "all")["tokens"]
            == ""
        )
        # Reports rebuild from raw saved records, including pre-feature records.
        assert await report_batch(store, tmp_path) == summary
    finally:
        await store.close()


def test_unknown_roles_are_visible_and_no_calls_has_no_spend():
    calls = model_call_rows(
        {"id": "run", "payload": {"mode": "P2"}},
        [
            {
                "id": "call",
                "kind": "model_call",
                "created_at": "time",
                "payload": {
                    "role": "new_role",
                    "stage": "new_stage",
                    "status": "RUNNING",
                },
            }
        ],
    )
    usage = token_report(calls)
    assert usage["by_phase"]["unclassified"]["unknown_usage_calls"] == 1
    assert usage["tokens"] is None
    assert token_report([])["tokens"] == 0
