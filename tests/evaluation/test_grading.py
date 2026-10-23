import csv
import io
import json
import math
import shutil
from pathlib import Path

import pytest

from mcp_execution_lab.evaluation.answers import expected, forecast_rows
from mcp_execution_lab.evaluation.grading import evaluate, review, rows_equal
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.models import Limits, OrchestrationError
from mcp_execution_lab.orchestration.provenance import source_identity
from mcp_execution_lab.orchestration.storage import Store

SUITE = Path(__file__).resolve().parents[2] / "fixtures/data_analysis_evals/development"


def csv_bytes(rows, columns=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


async def prepare(tmp_path, task_id, store=None):
    suite = Suite(SUITE)
    task = suite.task(task_id)
    store = store or Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    run_id = await store.create_run(
        {"request": task.query, "mode": "D1", "is_model": False, **source_identity()}
    )
    files = Files(tmp_path / "files", store, Limits())
    inputs = [await files.register_csv(run_id, suite.path(name)) for name in task.files]
    return suite, task, store, run_id, files, inputs


async def finish(store, files, run_id, roots, status="COMPLETED"):
    await store.transition(run_id, "EXECUTING")
    await store.put(
        run_id,
        "execution_result",
        {"status": status, "outputs": {str(i): ref.model_dump() for i, ref in enumerate(roots)}},
    )
    await store.transition(run_id, status)


def test_frozen_csvs_and_independent_reference_totals():
    suite = Suite(SUITE)
    assert len(suite.manifest["files"]) == 10 and len(suite.tasks) == 15
    totals = {
        "sales_total": "6357.50",
        "approved_refunds": "94.75",
        "captured_payments": "226.50",
        "daily_sales_total": "2388",
    }
    for key, total in totals.items():
        task = suite.task(key)
        rows = expected(task, {name: suite.path(name) for name in task.files})
        assert float(next(iter(rows[0].values()))) == float(total)
    rows, train, test = forecast_rows(suite.path("daily_sales.csv"))
    assert train == list(range(2, 34)) and test == list(range(34, 42))
    assert [row["predicted"] for row in rows[:8]] == ["71"] * 8
    assert [row["predicted"] for row in rows[8:]] == ["78"] * 3
    assert all(row["actual"] == "" for row in rows[8:])


def test_changed_fixture_is_rejected(tmp_path):
    shutil.copytree(SUITE, tmp_path / "suite")
    (tmp_path / "suite/orders.csv").write_text("id,value\na,1\n")
    with pytest.raises(OrchestrationError, match="manifest"):
        Suite(tmp_path / "suite")


def test_row_comparison_preserves_ids_duplicates_blanks_and_tolerance():
    task = Suite(SUITE).task("customer_orders")
    row = {"order_id": "0001", "customer_id": "001", "segment": ""}
    assert rows_equal([row, row], [row, row], task)
    assert not rows_equal([row], [row, row], task)
    assert not rows_equal([row | {"customer_id": "1"}], [row], task)
    numeric = Suite(SUITE).task("sales_total")
    assert rows_equal([{"total_amount": "10.004"}], [{"total_amount": "10"}], numeric)
    for value in ("10.006", "NaN", "Infinity", "", "wrong"):
        assert not rows_equal([{"total_amount": value}], [{"total_amount": "10"}], numeric)


@pytest.mark.parametrize("value,passed", [(6357.5, True), (6357.51, False), (999999, False)])
async def test_completed_execution_is_graded_independently(tmp_path, value, passed):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_total")
    try:
        ref = await files.put_json(run_id, {"rows": [{"total_amount": value}]})
        await finish(store, files, run_id, [ref])
        result = await evaluate(store, files, suite, task.id, run_id)
        assert result["task_success"] is passed
        assert (await store.run(run_id))["status"] == "COMPLETED"
        assert result["measurements"]["usd_cost"] is None
        assert (await store.get(run_id, result["evaluation_id"]))["run_id"] == run_id
    finally:
        await store.close()


async def test_wrong_table_cannot_hide_behind_a_correct_table(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_total")
    try:
        good = await files.put_json(run_id, {"rows": [{"total_amount": 6357.5}]})
        bad = await files.put_json(run_id, {"rows": [{"total_amount": 0}]})
        await finish(store, files, run_id, [good, bad])
        assert (await evaluate(store, files, suite, task.id, run_id))["task_success"] is False
    finally:
        await store.close()


async def test_unreturned_intermediate_answer_does_not_count(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_total")
    try:
        await files.put_json(run_id, {"rows": [{"total_amount": 6357.5}]})
        wrong = await files.put_json(run_id, {"summary": "Finished"})
        await finish(store, files, run_id, [wrong])
        assert (await evaluate(store, files, suite, task.id, run_id))["task_success"] is False
    finally:
        await store.close()


async def test_active_run_and_unrelated_task_cannot_be_graded(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_total")
    try:
        with pytest.raises(OrchestrationError, match="ended"):
            await evaluate(store, files, suite, task.id, run_id)
        await finish(store, files, run_id, [])
        with pytest.raises(OrchestrationError, match="exact public task"):
            await evaluate(store, files, suite, "sales_by_region", run_id)
    finally:
        await store.close()


async def test_altered_output_and_original_input_fail_integrity(tmp_path):
    suite, task, store, run_id, files, inputs = await prepare(tmp_path, "sales_total")
    try:
        ref = await files.put_json(run_id, {"rows": [{"total_amount": 6357.5}]})
        await finish(store, files, run_id, [ref])
        path = await files.checked_path(run_id, inputs[0].ref)
        path.write_bytes(b"changed")
        value = await evaluate(store, files, suite, task.id, run_id)
        assert value["status"] == "FAILED" and value["checks"][-1]["code"] == "FILE_CHANGED"
    finally:
        await store.close()


async def test_human_review_remains_pending_and_preserves_previous_result(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_report")
    try:
        table = await files.put_json(run_id, {"rows": [{"total_amount": 6357.5}]})
        report = await files.put_bytes(run_id, b"Completed sales: 6357.50 INR.", "md")
        await finish(store, files, run_id, [table, report])
        result = await evaluate(store, files, suite, task.id, run_id)
        assert result["task_success"] is None and result["status"] == "REVIEW_NEEDED"
        reviewed = await review(
            store,
            run_id,
            result["evaluation_id"],
            passed=False,
            reviewer="Test reviewer",
            note="Missing the requested source link.",
        )
        assert reviewed["task_success"] is False
        assert (await store.get(run_id, result["evaluation_id"]))["payload"][
            "status"
        ] == "REVIEW_NEEDED"
    finally:
        await store.close()


async def test_clarification_requires_a_question_and_a_human_check(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "missing_profit_inputs")
    try:
        await store.put(
            run_id, "main_task", {"clarification_questions": ["What costs define profit?"]}
        )
        await store.transition(run_id, "NEEDS_CLARIFICATION")
        result = await evaluate(store, files, suite, task.id, run_id)
        assert result["status"] == "REVIEW_NEEDED" and result["task_success"] is None
    finally:
        await store.close()


@pytest.mark.parametrize("error,passed", [(5, True), (0, False), (6, False)])
async def test_forecast_recomputes_scores_and_checks_time_split(tmp_path, error, passed):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "last_value_forecast")
    try:
        rows, train, test = forecast_rows(suite.path("daily_sales.csv"))
        table = await files.put_bytes(run_id, csv_bytes(rows), "csv")
        split = await files.put_json(
            run_id, {"training_source_rows": train, "test_source_rows": test}
        )
        metrics = {"mean_absolute_error": error, "root_mean_squared_error": math.sqrt(31.5)}
        scores = await files.put_json(
            run_id, {"details": {"metrics": metrics, "baseline_metrics": metrics}}
        )
        await finish(store, files, run_id, [table, split, scores])
        result = await evaluate(store, files, suite, task.id, run_id)
        assert result["task_success"] is passed, result["checks"]
    finally:
        await store.close()


async def test_foreign_reference_cannot_be_smuggled_after_valid_reference(tmp_path):
    suite, task, store, run_id, files, _ = await prepare(tmp_path, "sales_total")
    try:
        valid = await files.put_json(run_id, {"rows": [{"total_amount": 6357.5}]})
        fake = valid.model_dump() | {"run_id": "run_" + "a" * 32}
        output = await files.put_json(run_id, {"valid": valid.model_dump(), "forged": fake})
        await finish(store, files, run_id, [output])
        result = await evaluate(store, files, suite, task.id, run_id)
        assert result["task_success"] is False
    finally:
        await store.close()


def test_grader_has_no_import_from_agent_operations():
    directory = Path(__file__).resolve().parents[2] / "src/mcp_execution_lab/evaluation"
    assert not any("agents." in p.read_text() for p in directory.glob("*.py"))
    public = json.dumps([task.model_dump() for task in Suite(SUITE).tasks])
    assert "expected_rows" not in public
