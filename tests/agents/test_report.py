import json

import pytest

from mcp_execution_lab.agents.common.models import Fact, NeedsInput
from mcp_execution_lab.agents.report.models import Recipe, Section, Style
from mcp_execution_lab.agents.report.operations import render


def test_report_rejects_invented_numbers_and_escapes_active_content():
    facts = [Fact(id="total", label="Total", value=30)]
    recipe = Recipe(
        title="Findings",
        sections=[
            Section(
                title="Answer",
                fact_ids=["total"],
                paragraphs=["The checked total is {{fact:total}}. <script>bad</script>"],
            )
        ],
    )
    text, details = render(recipe, facts, {"total": "artifact_test"}, [], [], Style())
    assert "30" in text and "<script>" not in text and details.claim_sources
    bad = recipe.model_copy(
        update={
            "sections": [Section(title="Answer", fact_ids=["total"], paragraphs=["Total is 999."])]
        }
    )
    with pytest.raises(NeedsInput, match="Numeric claims"):
        render(bad, facts, {"total": "artifact_test"}, [], [], Style())


async def test_report_consumes_real_analysis_output_over_mcp(tmp_path):
    from mcp_execution_lab.orchestration.config import ModelConfig, Settings
    from mcp_execution_lab.orchestration.files import Files
    from mcp_execution_lab.orchestration.models import FileRef, ServerConfig
    from mcp_execution_lab.orchestration.service import Application
    from mcp_execution_lab.orchestration.storage import Store

    from .workers import AgentModel

    class PipelineModel(AgentModel):
        async def generate(self, request, directory):
            stage = request["stage"]
            context = request["context"]
            selection = {
                "tool_keys": ["calc/analyze_data", "writer/create_report"],
                "reasons": ["Compute requested total", "Explain saved findings"],
            }
            if request["role"] == "worker" and context["worker_role"] == "report":
                value = {
                    "title": "Saved findings",
                    "sections": [
                        {
                            "title": "Answer",
                            "paragraphs": [
                                "The checked total is {{fact:source_0_group_0_metric_0}}."
                            ],
                            "fact_ids": ["source_0_group_0_metric_0"],
                        }
                    ],
                }
            elif stage == "tool_selection":
                value = selection
            elif stage == "subtasks":
                value = {
                    "selection": selection,
                    "subtasks": [
                        {
                            "id": "calc",
                            "tool_key": "calc/analyze_data",
                            "job": "Calculate the total",
                            "expected_outputs": ["facts"],
                        },
                        {
                            "id": "write",
                            "tool_key": "writer/create_report",
                            "job": "Write from the saved total",
                            "expected_outputs": ["report"],
                        },
                    ],
                }
            elif stage == "dag":
                value = {
                    "steps": [
                        {
                            "id": "calc",
                            "subtask_id": "calc",
                            "server": "calc",
                            "tool": "analyze_data",
                            "arguments": {
                                "job": {"kind": "literal", "value": "Calculate the total"},
                                "datasets": {
                                    "kind": "list",
                                    "items": [
                                        {
                                            "kind": "dataset",
                                            "key": context["datasets"][0]["ref"]["id"],
                                        }
                                    ],
                                },
                            },
                        },
                        {
                            "id": "write",
                            "subtask_id": "write",
                            "server": "writer",
                            "tool": "create_report",
                            "depends_on": ["calc"],
                            "arguments": {
                                "job": {"kind": "literal", "value": "Write from the saved total"},
                                "evidence": {
                                    "kind": "list",
                                    "items": [
                                        {"kind": "step", "key": "calc", "path": ["artifacts", 0]}
                                    ],
                                },
                            },
                        },
                    ],
                    "outputs": {"answer": {"kind": "step", "key": "write"}},
                }
            else:
                return await super().generate(request, directory)
            return {
                "content": {"content_json": json.dumps(value)},
                "usage": {"input_tokens": 5, "output_tokens": 5},
            }

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    settings = Settings(
        servers=[
            ServerConfig(
                id=name,
                command="{python}",
                args=["-m", f"mcp_execution_lab.agents.{module}.server"],
            )
            for name, module in [("calc", "analysis"), ("writer", "report")]
        ],
        model=ModelConfig(provider="command", model_id="test"),
    )
    client = PipelineModel(
        store,
        "data_analysis",
        "analyze_data",
        {"measures": [{"name": "total", "operation": "sum", "column": "amount"}]},
    )
    source = tmp_path / "source.csv"
    source.write_text("amount\n10\n20\n", encoding="utf-8")
    files = Files(tmp_path / "data", store, settings.limits)
    try:
        app = Application(store, files.root, settings, client=client)
        handoff = await app.plan("Calculate and explain the total", [source])
        result = await app.execute(handoff.run_id)
        assert result["status"] == "COMPLETED"
        workers = await store.list_records(handoff.run_id, "worker_call")
        report = next(
            row["payload"]["result"] for row in workers if row["payload"]["role"] == "report"
        )
        ref = FileRef.model_validate(report["artifacts"][0])
        path = await files.checked_path(handoff.run_id, ref)
        assert "checked total is 30" in path.read_text(encoding="utf-8")
        assert result["metrics"]["model_calls"] == 7
    finally:
        await store.close()
