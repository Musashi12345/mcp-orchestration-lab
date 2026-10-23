import pytest

from mcp_execution_lab.agents.combining.models import Recipe, Rules
from mcp_execution_lab.agents.combining.operations import combine
from mcp_execution_lab.agents.common.models import NeedsInput, Table
from mcp_execution_lab.orchestration.models import FileRef

from .workers import agent_episode


def test_join_keeps_missing_keys_unmatched_and_rejects_unapproved_multiplication():
    def table(name, rows):
        ref = FileRef(id=name, run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
        return Table(ref=ref, columns=["id", "value"], rows=rows)

    left = table("left", [{"id": "001", "value": "a"}, {"id": "", "value": "b"}])
    right = table("right", [{"id": "001", "value": "x"}, {"id": "", "value": "y"}])
    _, rows, mapping, details = combine(
        [left, right], Recipe(operation="join", keys=["id"], join_type="outer"), Rules()
    )
    assert len(rows) == 3 and details.checks[0]["right_unmatched"] == 1
    assert len(mapping[0]) == 2 and rows[0]["id"] == "001"
    duplicate = right.model_copy(update={"rows": [right.rows[0]] * 2})
    with pytest.raises(NeedsInput, match="repeated"):
        combine([left, duplicate], Recipe(operation="join", keys=["id"]), Rules())


async def test_combining_through_real_mcp(tmp_path):
    result, value, published, _ = await agent_episode(
        tmp_path,
        "data_combining",
        "combine_data",
        {"operation": "join", "keys": ["id"], "join_type": "left"},
        csvs=["id,value\n001,a\n002,b\n", "id,amount\n001,10\n003,30\n"],
    )
    assert result["status"] == "COMPLETED"
    assert value["details"]["checks"][0]["left_unmatched"] == 1
    assert b"001,a,10" in published[value["datasets"][0]["id"]]
