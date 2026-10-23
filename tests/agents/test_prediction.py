import pytest

from mcp_execution_lab.agents.common.models import NeedsInput, Table
from mcp_execution_lab.agents.prediction.models import Recipe, Rules
from mcp_execution_lab.agents.prediction.operations import predict
from mcp_execution_lab.orchestration.models import FileRef

from .workers import agent_episode


def table():
    ref = FileRef(id="sample", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    return Table(
        ref=ref,
        columns=["x", "y", "date"],
        rows=[
            {"x": str(i), "y": str(2 * i + 3), "date": f"2026-01-{i + 1:02d}"} for i in range(20)
        ],
    )


def test_prediction_separates_future_records_and_beats_a_reference():
    details, split, rows, _ = predict(
        table(),
        Recipe(method="linear_regression", target="y", features=["x"], time_column="date"),
        Rules(),
    )
    assert max(split["training_source_rows"]) < min(split["test_source_rows"])
    assert details.metrics["mean_absolute_error"] < 1e-10
    assert details.baseline_metrics["mean_absolute_error"] > 0
    assert all(row["split"] == "test" for row in rows)
    with pytest.raises(NeedsInput, match="answer"):
        predict(table(), Recipe(method="linear_regression", target="y", features=["y"]), Rules())


def test_last_value_preserves_weak_baseline_and_has_no_invented_future_actuals():
    details, _, rows, warnings = predict(
        table(), Recipe(method="last_value", target="y", time_column="date", horizon=2), Rules()
    )
    assert details.metrics == details.baseline_metrics and warnings
    assert all(row["actual"] == "" for row in rows if row["split"] == "future")


def test_classification_uses_training_scaling_and_retains_class_counts():
    source = table()
    rows = [row | {"label": "low" if int(row["x"]) < 10 else "high"} for row in source.rows]
    source = source.model_copy(update={"rows": rows, "columns": source.columns + ["label"]})
    details, manifest, _, _ = predict(
        source, Recipe(method="nearest_centroid", target="label", features=["x"]), Rules()
    )
    assert 0 <= details.metrics["accuracy"] <= 1
    assert sum(details.model_parameters["training_class_counts"].values()) == details.training_rows
    assert set(manifest["training_source_rows"]).isdisjoint(manifest["test_source_rows"])


def test_equivalent_timestamps_cannot_cross_the_time_split():
    source = table()
    rows = [dict(row) for row in source.rows]
    rows[15]["date"] = "2026-01-17"
    rows[16]["date"] = "2026-01-17T00:00:00"
    source = source.model_copy(update={"rows": rows})
    with pytest.raises(NeedsInput, match="Equal-time"):
        predict(source, Recipe(method="last_value", target="y", time_column="date"), Rules())


async def test_prediction_through_real_mcp(tmp_path):
    def arguments(context, job):
        return {
            "job": {"kind": "literal", "value": job},
            "dataset": {"kind": "dataset", "key": context["datasets"][0]["ref"]["id"]},
            "target": {"kind": "literal", "value": "y"},
        }

    csv = "x,y\n" + "".join(f"{i},{2 * i + 3}\n" for i in range(20))
    result, value, _, _ = await agent_episode(
        tmp_path,
        "prediction",
        "predict_data",
        {"method": "linear_regression", "target": "y", "features": ["x"]},
        arguments,
        [csv],
    )
    assert result["status"] == "COMPLETED"
    assert value["details"]["metrics"]["mean_absolute_error"] < 1e-10
