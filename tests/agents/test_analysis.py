import csv
import io

from mcp_execution_lab.agents.analysis.models import Comparison, Definitions, Measure, Recipe
from mcp_execution_lab.agents.analysis.operations import analyze, chart
from mcp_execution_lab.agents.common.models import Table
from mcp_execution_lab.orchestration.models import FileRef

from .workers import agent_episode


def test_analysis_exact_totals_denominators_and_zero_reference():
    ref = FileRef(id="sample", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(
        ref=ref,
        columns=["month", "sales"],
        rows=[
            {"month": "first", "sales": "0"},
            {"month": "next", "sales": "10.1"},
            {"month": "next", "sales": "0.2"},
            {"month": "next", "sales": ""},
        ],
    )
    recipe = Recipe(
        group_by=["month"],
        measures=[Measure(name="sales", column="sales", operation="sum")],
        comparison=Comparison(before="first", after="next", measure="sales"),
        chart_metric="sales",
    )
    details, _, warnings = analyze(table, recipe, Definitions())
    assert details.groups[1].metrics["sales"] == 10.3
    assert details.groups[1].missing_counts["sales"] == 1
    assert details.comparison["percent_change"] is None and warnings
    assert chart(details).startswith(b"\x89PNG")


async def test_analysis_through_real_mcp(tmp_path):
    result, value, published, _ = await agent_episode(
        tmp_path,
        "data_analysis",
        "analyze_data",
        {
            "measures": [{"name": "total", "operation": "sum", "column": "amount"}],
            "chart_metric": "total",
        },
        csvs=["product,amount\na,10\nb,20\n"],
    )
    assert result["status"] == "COMPLETED"
    assert value["details"]["groups"][0]["metrics"]["total"] == 30
    assert any(data.startswith(b"\x89PNG") for data in published.values())


async def test_discovered_analysis_contract_matches_filtered_decimal_table_and_evidence(tmp_path):
    result, value, published, records = await agent_episode(
        tmp_path,
        "data_analysis",
        "analyze_data",
        {
            "filters": [{"column": "status", "operation": "eq", "value": "completed"}],
            "measures": [{"name": "total_amount_inr", "operation": "sum", "column": "amount"}],
        },
        csvs=["status,amount\ncompleted,10.1\ncompleted,0.2\ncancelled,999\n"],
    )
    assert result["status"] == "COMPLETED"
    cache = next(row["payload"]["cache"] for row in records if row["kind"] == "tool_cache")
    description = cache["tools"][0]["description"]
    assert "Decimal internally" in description
    assert "not exact Decimal JSON" in description
    assert "one row" in description and "named measure columns" in description
    tables = [
        list(csv.DictReader(io.StringIO(published[ref["id"]].decode("utf-8-sig"))))
        for ref in value["artifacts"]
        if ref["kind"] == "csv"
    ]
    assert tables == [[{"total_amount_inr": "10.3"}]]
    assert any(ref["kind"] == "json" for ref in value["artifacts"])
    assert value["details"]["rows_used"] == 2
    assert value["details"]["rows_excluded"] == 1
    assert value["details"]["groups"][0]["metrics"] == {"total_amount_inr": 10.3}
