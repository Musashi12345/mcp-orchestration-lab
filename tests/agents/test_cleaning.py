import pytest

from mcp_execution_lab.agents.cleaning.models import Operation, Recipe, Rules
from mcp_execution_lab.agents.cleaning.operations import clean
from mcp_execution_lab.agents.common.models import NeedsInput, Table
from mcp_execution_lab.orchestration.models import FileRef

from .workers import agent_episode


def test_cleaning_preserves_source_and_explains_each_change():
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(
        ref=ref,
        columns=["id", "value"],
        rows=[
            {"id": "001", "value": " a "},
            {"id": "001", "value": " a "},
            {"id": "002", "value": ""},
        ],
    )
    recipe = Recipe(
        operations=[
            Operation(action="trim", column="value", reason="Explicit rule"),
            Operation(action="remove_exact_duplicates", reason="Exact repeated rows"),
        ]
    )
    rows, changes, mapping, details = clean(
        table, recipe, Rules(trim_columns=["value"], remove_exact_duplicates=True)
    )
    assert rows == [{"id": "001", "value": "a"}, {"id": "002", "value": ""}]
    assert table.rows[0]["value"] == " a "
    assert mapping == [2, 4] and details.removed_rows == 1 and len(changes) == 3
    with pytest.raises(NeedsInput, match="does not allow"):
        clean(table, recipe, Rules())


async def test_cleaning_through_real_mcp_registers_a_new_dataset(tmp_path):
    def arguments(context, job):
        return {
            "job": {"kind": "literal", "value": job},
            "dataset": {"kind": "dataset", "key": context["datasets"][0]["ref"]["id"]},
            "rules": {
                "kind": "literal",
                "value": {"trim_columns": ["value"], "remove_exact_duplicates": True},
            },
        }

    result, value, published, records = await agent_episode(
        tmp_path,
        "data_cleaning",
        "clean_data",
        {
            "operations": [
                {"action": "trim", "column": "value", "reason": "Explicit rule"},
                {"action": "remove_exact_duplicates", "reason": "Exact duplicate"},
            ]
        },
        arguments,
    )
    assert result["status"] == "COMPLETED"
    assert value["details"]["after_rows"] == 2
    assert published[value["datasets"][0]["id"]].decode() == "id,value\n001,a\n002,b\n"
    assert (
        len([row for row in records if row["kind"] == "dataset"]) == 3
    )  # Source, cleaned, changes.
