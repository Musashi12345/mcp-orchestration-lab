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
