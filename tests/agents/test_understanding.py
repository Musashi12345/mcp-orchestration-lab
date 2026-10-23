from mcp_execution_lab.agents.common.models import Table
from mcp_execution_lab.agents.understanding.models import Recipe
from mcp_execution_lab.agents.understanding.operations import inspect_tables
from mcp_execution_lab.orchestration.models import FileRef


def test_full_profile_finds_duplicates_missing_values_and_preserves_identifiers():
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    rows = [
        {"id": "001", "amount": "10"},
        {"id": "002", "amount": ""},
        {"id": "001", "amount": "10"},
    ]
    details, facts = inspect_tables(
        [Table(ref=ref, columns=["id", "amount"], rows=rows)], Recipe(key_columns=["id"])
    )
    assert details.profiles[0].duplicate_rows == 1
    assert details.profiles[0].columns[1].missing == 1
    assert not details.key_checks[0]["unique"]
    assert facts[0].value == 3 and rows[0]["id"] == "001"


async def test_understanding_through_real_mcp_and_live_run_records(tmp_path):
    from mcp_execution_lab.orchestration.config import ModelConfig, Settings
    from mcp_execution_lab.orchestration.models import ServerConfig
    from mcp_execution_lab.orchestration.service import Application
    from mcp_execution_lab.orchestration.storage import Store

    from .workers import AgentModel

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    model = AgentModel(store, "data_understanding", "understand_data")
    config = Settings(
        servers=[
            ServerConfig(
                id="worker",
                command="{python}",
                args=["-m", "mcp_execution_lab.agents.understanding.server"],
            )
        ],
        model=ModelConfig(provider="command", model_id="test"),
    )
    source = tmp_path / "sample.csv"
    source.write_text("name,amount\na,10\nb,20\n", encoding="utf-8")
    try:
        app = Application(store, tmp_path / "data", config, client=model)
        handoff = await app.plan("Understand this dataset", [source])
        result = await app.execute(handoff.run_id)
        assert result["status"] == "COMPLETED"
        records = await store.list_records(handoff.run_id)
        assert len([row for row in records if row["kind"] == "worker_call"]) == 1
        assert len([row for row in records if row["kind"] == "model_call"]) == 6
        assert result["metrics"]["model_calls"] == 6
        worker = next(row for row in records if row["kind"] == "worker_call")
        assert worker["payload"]["result"]["details"]["profiles"][0]["row_count"] == 2
    finally:
        await store.close()


async def test_unknown_column_is_a_saved_non_completed_worker_outcome(tmp_path):
    from .workers import agent_episode

    result, value, _, records = await agent_episode(
        tmp_path, "data_understanding", "understand_data", {"columns": ["not_a_column"]}
    )
    assert result["status"] == "FAILED" and value["outcome"] == "NEEDS_INPUT"
    assert value["questions"] and len(value["usage_record_ids"]) == 1
    assert any(row["kind"] == "execution_result" for row in records)
