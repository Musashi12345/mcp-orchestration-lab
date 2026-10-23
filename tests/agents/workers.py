"""Scripted model replies are test fixtures, never measured model runs."""

import json


async def agent_episode(tmp_path, role, tool, recipe=None, arguments=None, csvs=None):
    from mcp_execution_lab.agents.common.registry import MODULES
    from mcp_execution_lab.orchestration.config import ModelConfig, Settings
    from mcp_execution_lab.orchestration.files import Files
    from mcp_execution_lab.orchestration.models import FileRef, ServerConfig
    from mcp_execution_lab.orchestration.service import Application
    from mcp_execution_lab.orchestration.storage import Store

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    client = AgentModel(store, role, tool, recipe, arguments)
    settings = Settings(
        servers=[
            ServerConfig(
                id="worker",
                command="{python}",
                args=["-m", f"mcp_execution_lab.agents.{MODULES[role]}.server"],
            )
        ],
        model=ModelConfig(provider="command", model_id="test"),
    )
    sources = []
    for index, text in enumerate(csvs or ["id,value\n001, a \n001, a \n002,b\n"]):
        path = tmp_path / f"input_{index}.csv"
        path.write_text(text, encoding="utf-8")
        sources.append(path)
    files = Files(tmp_path / "data", store, settings.limits)
    try:
        app = Application(store, files.root, settings, client=client)
        handoff = await app.plan("Complete the assigned data task", sources)
        result = await app.execute(handoff.run_id)
        records = await store.list_records(handoff.run_id)
        worker = next(row for row in records if row["kind"] == "worker_call")
        value = worker["payload"].get("result")
        assert value is not None, worker["payload"]
        published = {}
        for reference in value["datasets"] + value["artifacts"]:
            ref = FileRef.model_validate(reference)
            path = await files.checked_path(handoff.run_id, ref)
            published[ref.id] = path.read_bytes()
        return result, value, published, records
    finally:
        await store.close()


class AgentModel:
    provider = "scripted-worker-test"
    is_model = False

    def __init__(self, store, role, tool, recipe=None, arguments=None):
        self.store, self.role, self.tool = store, role, tool
        self.recipe = recipe or {}
        self.arguments = arguments
        self.requests = []

    async def generate(self, request, directory):
        self.requests.append(request)
        records = await self.store.list_records(directory.parent.parent.name, "model_call")
        assert any(row["payload"]["status"] == "RUNNING" for row in records)
        stage, context = request["stage"], request["context"]
        job = "Complete the assigned data task"
        selection = {"tool_keys": ["worker/" + self.tool], "reasons": ["Needed for the question"]}
        if request["role"] == "worker":
            if stage.endswith(".recipe"):
                value = self.recipe
            else:
                facts = context["facts"]["facts"]
                key = facts[0]["id"] if facts else None
                value = {
                    "text": "Checked result: {{fact:" + key + "}}." if key else "Checks completed.",
                    "fact_ids": [key] if key else [],
                }
        elif stage == "main_task":
            value = {
                "goal": context["original_request"],
                "dataset_ids": [item["ref"]["id"] for item in context["datasets"]],
                "required_outputs": ["answer"],
            }
        elif stage == "tool_selection":
            value = selection
        elif stage == "subtasks":
            value = {
                "selection": selection,
                "subtasks": [
                    {
                        "id": "work",
                        "tool_key": "worker/" + self.tool,
                        "job": job,
                        "expected_outputs": ["answer"],
                    }
                ],
            }
        elif stage == "dag":
            refs = [{"kind": "dataset", "key": item["ref"]["id"]} for item in context["datasets"]]
            args = {
                "job": {"kind": "literal", "value": job},
                "datasets": {"kind": "list", "items": refs},
            }
            if self.arguments:
                args = self.arguments(context, job)
            value = {
                "steps": [
                    {
                        "id": "work",
                        "subtask_id": "work",
                        "server": "worker",
                        "tool": self.tool,
                        "arguments": args,
                    }
                ],
                "outputs": {"answer": {"kind": "step", "key": "work"}},
            }
        else:
            value = {"decision": "KEEP", "reason": "Continue the saved plan"}
        return {
            "content": {"content_json": json.dumps(value)},
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
