import asyncio
import json
import os
from pathlib import Path

import pytest
from agents.workers import AgentModel
from orchestration.postgres import LocalPostgres

from mcp_execution_lab.evaluation.batch import report_batch, run_batch
from mcp_execution_lab.evaluation.grading import evaluate
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.orchestration.config import ModelConfig, Settings
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.models import Limits, ReviewRule, ServerConfig, TaskRules
from mcp_execution_lab.orchestration.service import Application
from mcp_execution_lab.orchestration.storage import Store

SUITE = Path(__file__).resolve().parents[2] / "fixtures/data_analysis_evals/development"


class EvalModel(AgentModel):
    def __init__(self, store):
        super().__init__(
            store,
            "data_analysis",
            "analyze_data",
            {
                "filters": [{"column": "status", "operation": "eq", "value": "completed"}],
                "measures": [{"name": "total_amount", "operation": "sum", "column": "amount_inr"}],
            },
        )

    async def generate(self, request, directory):
        text = json.dumps(request)
        assert not any(
            key in text for key in ("expected_rows", "grader_sha256", "evaluation_result")
        )
        return await super().generate(request, directory)


def settings():
    return Settings(
        servers=[
            ServerConfig(
                id="worker",
                command="{python}",
                args=["-m", "mcp_execution_lab.agents.analysis.server"],
            )
        ],
        model=ModelConfig(provider="command", model_id="deterministic-eval-test"),
        limits=Limits(max_model_calls=8),
        task_rules=TaskRules(
            reviews=[
                ReviewRule(id="first", after_completed_steps=1),
                ReviewRule(id="second", after_completed_steps=2),
            ]
        ),
    )


async def paired_check(store, tmp_path):
    await store.initialize()
    client = EvalModel(store)
    result = await run_batch(
        store,
        tmp_path / "files",
        settings(),
        Suite(SUITE),
        tmp_path / "reports",
        task_ids=["sales_total"],
        modes=["D1", "D2"],
        repeats=1,
        seed=7,
        max_model_calls=16,
        client=client,
    )
    manifest = result["manifest"]
    assert manifest["status"] == "COMPLETED"
    assert len({e["run_id"] for e in manifest["episodes"]}) == 2
    summary = await report_batch(store, result["directory"])
    assert summary["modes"]["D1"]["passed"] == summary["modes"]["D2"]["passed"] == 1
    assert summary["comparisons"]["D1_to_D2"]["scored_pairs"] == 1
    assert manifest["used_model_calls"] == len(client.requests)
    audits = []
    for episode in manifest["episodes"]:
        run_id = episode["run_id"]
        records = await store.list_records(run_id)
        assert len([r for r in records if r["kind"] == "evaluation_episode"]) == 1
        audits.append(
            {
                "run": await store.run(run_id),
                "records": records,
                "events": await store.history(run_id),
            }
        )
    (tmp_path / "audit.json").write_text(
        json.dumps({"manifest": manifest, "summary": summary, "runs": audits}, indent=2),
        encoding="utf-8",
    )
    return result


async def test_paired_batch_uses_real_mcp_and_independent_grading(tmp_path):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await paired_check(store, tmp_path)
    finally:
        await store.close()


@pytest.mark.skipif(
    os.environ.get("MCP_LAB_POSTGRES_TEST") != "1", reason="Native PostgreSQL opt-in required."
)
async def test_native_postgres_saves_run_linked_evaluation_and_pair_reports(tmp_path):
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres").start)
    store = Store(cluster.url)
    try:
        await paired_check(store, tmp_path)
    finally:
        await store.close()
        await asyncio.to_thread(cluster.close)


async def test_batch_reserves_equal_allowance_for_a_whole_pair(tmp_path):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        client = EvalModel(store)
        result = await run_batch(
            store,
            tmp_path / "files",
            settings(),
            Suite(SUITE),
            tmp_path / "reports",
            task_ids=["sales_total"],
            max_model_calls=15,
            client=client,
        )
        assert result["manifest"]["status"] == "BUDGET_STOPPED" and not client.requests
        assert all(e["status"] == "QUEUED" for e in result["manifest"]["episodes"])
    finally:
        await store.close()


async def test_forecast_is_independently_graded_after_real_mcp_worker(tmp_path):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        suite = Suite(SUITE)
        task = suite.task("last_value_forecast")
        config = Settings(
            servers=[
                ServerConfig(
                    id="worker",
                    command="{python}",
                    args=["-m", "mcp_execution_lab.agents.prediction.server"],
                )
            ],
            model=ModelConfig(provider="command", model_id="deterministic-eval-test"),
        )

        def arguments(context, job):
            return {
                "job": {"kind": "literal", "value": job},
                "dataset": {"kind": "dataset", "key": context["datasets"][0]["ref"]["id"]},
                "target": {"kind": "literal", "value": "units_sold"},
                "time_column": {"kind": "literal", "value": "date"},
            }

        client = AgentModel(
            store,
            "prediction",
            "predict_data",
            {"method": "last_value", "target": "units_sold", "time_column": "date", "horizon": 3},
            arguments,
        )
        app = Application(store, tmp_path / "files", config, client=client)
        handoff = await app.plan(task.query, [suite.path("daily_sales.csv")])
        await app.execute(handoff.run_id)
        result = await evaluate(
            store, Files(tmp_path / "files", store, config.limits), suite, task.id, handoff.run_id
        )
        assert result["task_success"] is True, result["checks"]
    finally:
        await store.close()


async def test_wrong_answers_and_failed_episodes_stay_in_batch_reports(tmp_path):
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        client = EvalModel(store)
        client.recipe = {
            "measures": [{"name": "total_amount", "operation": "sum", "column": "amount_inr"}]
        }
        result = await run_batch(
            store,
            tmp_path / "files",
            settings(),
            Suite(SUITE),
            tmp_path / "reports",
            task_ids=["sales_total"],
            max_model_calls=16,
            client=client,
        )
        summary = await report_batch(store, result["directory"])
        assert summary["modes"]["D1"]["failed"] == summary["modes"]["D2"]["failed"] == 1
        assert summary["modes"]["D1"]["confirmed_pass_fraction_of_attempts"] == 0
        assert all(e["status"] == "FAILED" for e in result["manifest"]["episodes"])
    finally:
        await store.close()


@pytest.mark.parametrize(
    "task_id,role,tool,recipe",
    [
        (
            "clean_orders",
            "cleaning",
            "clean_data",
            {
                "operations": [
                    {"action": "trim", "column": "region", "reason": "Requested rule"},
                    {"action": "replace", "column": "region", "reason": "Requested rule"},
                    {"action": "remove_exact_duplicates", "reason": "Exact duplicate"},
                ]
            },
        ),
        (
            "customer_orders",
            "combining",
            "combine_data",
            {
                "operation": "join",
                "keys": ["customer_id"],
                "join_type": "left",
                "relationship": "many_to_one",
            },
        ),
        (
            "low_stock",
            "analysis",
            "analyze_data",
            {
                "filters": [{"column": "available_units", "operation": "lt", "value": "5"}],
                "group_by": ["product_id", "warehouse", "available_units"],
            },
        ),
        (
            "sales_chart",
            "analysis",
            "analyze_data",
            {
                "filters": [{"column": "status", "operation": "eq", "value": "completed"}],
                "group_by": ["region"],
                "measures": [{"name": "total_amount", "operation": "sum", "column": "amount_inr"}],
                "chart_metric": "total_amount",
            },
        ),
    ],
)
async def test_case_outputs_from_real_mcp_match_private_checks(
    tmp_path, task_id, role, tool, recipe
):
    suite = Suite(SUITE)
    task = suite.task(task_id)
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        config = Settings(
            servers=[
                ServerConfig(
                    id="worker",
                    command="{python}",
                    args=["-m", f"mcp_execution_lab.agents.{role}.server"],
                )
            ],
            model=ModelConfig(provider="command", model_id="deterministic-eval-test"),
        )

        def arguments(context, job):
            refs = [{"kind": "dataset", "key": d["ref"]["id"]} for d in context["datasets"]]
            result = {"job": {"kind": "literal", "value": job}}
            if role == "cleaning":
                result["dataset"] = refs[0]
                result["rules"] = {
                    "kind": "literal",
                    "value": {
                        "trim_columns": ["region"],
                        "replacements": {"region": {"west": "West", "NORTH": "North"}},
                        "remove_exact_duplicates": True,
                    },
                }
            else:
                result["datasets"] = {"kind": "list", "items": refs}
            if role == "combining":
                result["rules"] = {
                    "kind": "literal",
                    "value": {
                        "keys": ["customer_id"],
                        "join_type": "left",
                        "relationship": "many_to_one",
                    },
                }
            return result

        client = AgentModel(store, "data_" + role, tool, recipe, arguments)
        app = Application(store, tmp_path / "files", config, client=client)
        handoff = await app.plan(task.query, [suite.path(name) for name in task.files])
        await app.execute(handoff.run_id)
        result = await evaluate(
            store, Files(tmp_path / "files", store, config.limits), suite, task.id, handoff.run_id
        )
        assert all(c["passed"] for c in result["checks"]), result["checks"]
        assert result["status"] == ("REVIEW_NEEDED" if task.human_checks else "PASSED")
    finally:
        await store.close()


async def test_planning_failures_are_retained_and_tokens_stay_unknown(tmp_path):
    class FailingModel(EvalModel):
        async def generate(self, request, directory):
            raise RuntimeError("Deterministic provider failure")

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        result = await run_batch(
            store,
            tmp_path / "files",
            settings(),
            Suite(SUITE),
            tmp_path / "reports",
            task_ids=["sales_total"],
            max_model_calls=16,
            client=FailingModel(store),
        )
        summary = await report_batch(store, result["directory"])
        for mode in ("D1", "D2"):
            assert summary["modes"][mode]["attempted"] == summary["modes"][mode]["failed"] == 1
        for episode in result["manifest"]["episodes"]:
            grades = await store.list_records(episode["run_id"], "evaluation_result")
            assert grades[-1]["payload"]["measurements"]["tokens"] is None
            assert grades[-1]["payload"]["execution_status"] == "PLANNING_FAILED"
    finally:
        await store.close()


async def test_cancellation_preserves_started_run_and_consumed_request(tmp_path):
    entered = asyncio.Event()

    class WaitingModel(EvalModel):
        async def generate(self, request, directory):
            entered.set()
            await asyncio.Future()

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    pending = asyncio.create_task(
        run_batch(
            store,
            tmp_path / "files",
            settings(),
            Suite(SUITE),
            tmp_path / "reports",
            task_ids=["sales_total"],
            max_model_calls=16,
            client=WaitingModel(store),
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 15)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        path = next((tmp_path / "reports").glob("*/manifest.json"))
        manifest = json.loads(path.read_text())
        assert manifest["status"] == "INTERRUPTED" and manifest["used_model_calls"] == 1
        started = [e for e in manifest["episodes"] if e.get("run_id")]
        assert len(started) == 1
        calls = await store.list_records(started[0]["run_id"], "model_call")
        assert calls[0]["payload"]["status"] == "INTERRUPTED"
        summary = await report_batch(store, path.parent)
        assert sum(v["attempted"] for v in summary["modes"].values()) == 1
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await store.close()
