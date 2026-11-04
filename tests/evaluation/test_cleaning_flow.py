"""Fixed replies exercise the approved cleaning question; no measured model claims."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from agents.workers import AgentModel
from orchestration.postgres import LocalPostgres

from mcp_execution_lab.evaluation.grading import evaluate
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.orchestration.config import ModelConfig, Settings, load_settings
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.models import Limits, ReviewRule, ServerConfig, TaskRules
from mcp_execution_lab.orchestration.service import Application
from mcp_execution_lab.orchestration.storage import Store

from .test_input_suite import suite as suite

RULES = {
    "trim_columns": [
        "order_id",
        "order_date",
        "customer_id",
        "product_id",
        "region",
        "status",
        "amount_inr",
    ],
    "label_values": {
        "region": ["North", "South", "East", "West"],
        "status": ["completed", "pending", "cancelled"],
    },
    "number_columns": ["amount_inr"],
    "drop_missing_columns": ["customer_id", "amount_inr"],
    "remove_exact_duplicates": True,
}
CLEANING = {
    "operations": [
        *(
            {"action": "trim", "column": name, "reason": "User rule"}
            for name in RULES["trim_columns"]
        ),
        *(
            {"action": "normalize_label", "column": name, "reason": "User labels"}
            for name in ("region", "status")
        ),
        {"action": "convert_number", "column": "amount_inr", "reason": "User numeric rule"},
        *(
            {"action": "drop_missing", "column": name, "reason": "User missing rule"}
            for name in ("customer_id", "amount_inr")
        ),
        {"action": "remove_exact_duplicates", "reason": "User duplicate rule"},
    ]
}
ANALYSIS = {
    "filters": [{"column": "status", "operation": "eq", "value": "completed"}],
    "group_by": ["region"],
    "measures": [{"name": "total_amount_inr", "operation": "sum", "column": "amount_inr"}],
}
JOBS = {
    "clean": "Apply the supplied explicit cleaning rules",
    "analyse": "Sum completed orders by region",
}


class FixedCleaningFlow(AgentModel):
    def __init__(self, store, *, omit_rules_once=False):
        super().__init__(store, "data_cleaning", "clean_data", CLEANING)
        self.omit_rules_once = omit_rules_once

    async def generate(self, request, directory):
        stage, context = request["stage"], request["context"]
        if request["role"] == "worker":
            self.recipe = CLEANING if ".data_cleaning." in stage else ANALYSIS
            return await super().generate(request, directory)
        keys = ["cleaner/clean_data", "analyst/analyze_data"]
        selection = {"tool_keys": keys, "reasons": ["User cleaning request", "User total request"]}
        if stage == "tool_selection":
            value = selection
        elif stage == "subtasks":
            value = {
                "selection": selection,
                "subtasks": [
                    {"id": name, "tool_key": key, "job": JOBS[name], "expected_outputs": ["answer"]}
                    for name, key in zip(JOBS, keys, strict=True)
                ],
            }
        elif stage == "dag":
            dataset = context["datasets"][0]["ref"]["id"]
            value = {
                "steps": [
                    {
                        "id": "clean",
                        "subtask_id": "clean",
                        "server": "cleaner",
                        "tool": "clean_data",
                        "arguments": {
                            "job": {"kind": "literal", "value": JOBS["clean"]},
                            "dataset": {"kind": "dataset", "key": dataset},
                            "rules": {"kind": "literal", "value": RULES},
                        },
                    },
                    {
                        "id": "analyse",
                        "subtask_id": "analyse",
                        "server": "analyst",
                        "tool": "analyze_data",
                        "depends_on": ["clean"],
                        "arguments": {
                            "job": {"kind": "literal", "value": JOBS["analyse"]},
                            "datasets": {
                                "kind": "list",
                                "items": [
                                    {"kind": "step", "key": "clean", "path": ["datasets", 0]}
                                ],
                            },
                        },
                    },
                ],
                "outputs": {
                    "cleaned": {"kind": "step", "key": "clean"},
                    "answer": {"kind": "step", "key": "analyse"},
                },
            }
        elif stage == "program":
            dataset = context["datasets"][0]["ref"]["id"]
            # Trusted fixed test input, executed only by the real Docker runner.
            value = {
                "source": f"""async def run(sdk, inputs):
    cleaned = await sdk.call("clean", {{
        "job": {JOBS["clean"]!r},
        "dataset": inputs["datasets"][{dataset!r}],
        "rules": {RULES!r}
    }})
    answer = await sdk.call("analyse", {{
        "job": {JOBS["analyse"]!r},
        "datasets": [cleaned["value"]["datasets"][0]]
    }})
    return {{"cleaned": cleaned["value"], "answer": answer["value"]}}
""",
                "outputs": ["cleaned", "answer"],
            }
        else:
            return await super().generate(request, directory)
        if stage in {"dag", "program"} and self.omit_rules_once:
            self.omit_rules_once = False
            if stage == "dag":
                del value["steps"][0]["arguments"]["rules"]
            else:
                value["source"] = value["source"].replace(f'        "rules": {RULES!r}\n', "")
        self.requests.append(request)
        return {
            "content": {"content_json": json.dumps(value)},
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }


@pytest.mark.parametrize("mode", ["D1", "D2", "P1", "P2"])
@pytest.mark.parametrize("omit_rules_once", [False, True])
async def test_q05_cleaning_and_analysis_with_real_mcp_and_independent_grading(
    tmp_path, suite, mode, omit_rules_once
):
    if mode.startswith("P") and os.environ.get("MCP_LAB_DOCKER_TEST") != "1":
        pytest.skip("Real Docker opt-in required.")
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await cleaning_flow(tmp_path, suite, mode, store, omit_rules_once=omit_rules_once)
    finally:
        await store.close()


async def cleaning_flow(tmp_path, suite, mode, store, *, omit_rules_once=False):
    await store.initialize()
    settings = Settings(
        servers=[
            ServerConfig(
                id=server,
                command="{python}",
                args=["-m", f"mcp_execution_lab.agents.{module}.server"],
            )
            for server, module in (("cleaner", "cleaning"), ("analyst", "analysis"))
        ],
        model=ModelConfig(provider="command", model_id="fixed-cleaning-repair"),
        limits=Limits(max_observed_tokens=300000),
        task_rules=TaskRules(
            reviews=[
                ReviewRule(id="first", after_completed_steps=1),
                ReviewRule(id="second", after_completed_steps=2),
            ]
        ),
    )
    task = suite.task("input_q05")
    root = tmp_path / "files"
    model = FixedCleaningFlow(store, omit_rules_once=omit_rules_once)
    app = Application(store, root, settings, client=model)
    handoff = await app.plan(task.query, [suite.path(name) for name in task.files], mode=mode)
    # Missing rules are corrected before a tool call or a Docker container is started.
    assert not await store.list_records(handoff.run_id, "tool_attempt")
    assert not await store.list_records(handoff.run_id, "program_container")
    validations = await store.list_records(handoff.run_id, "validation")
    assert len(validations) == int(omit_rules_once)
    stage = "program" if mode.startswith("P") else "dag"
    attempts = [request for request in model.requests if request["stage"] == stage]
    assert len(attempts) == 1 + int(omit_rules_once)
    if omit_rules_once:
        assert "rules" in json.dumps(attempts[-1]["context"]["validation_errors"])
    result = await app.execute(handoff.run_id)
    assert result["status"] == "COMPLETED"
    grade = await evaluate(
        store, Files(root, store, settings.limits), suite, task.id, handoff.run_id
    )
    assert grade["status"] == "PASSED", grade
    attempts = await store.list_records(handoff.run_id, "tool_attempt")
    assert attempts[0]["payload"]["arguments"]["rules"] == RULES
    assert [attempt["payload"]["status"] for attempt in attempts] == ["SUCCEEDED", "SUCCEEDED"]
    assert not any("expected_rows" in json.dumps(request) for request in model.requests)
    (tmp_path / "audit.json").write_text(
        json.dumps(
            {
                "run": await store.run(handoff.run_id),
                "records": await store.list_records(handoff.run_id),
                "events": await store.history(handoff.run_id),
                "grade": grade,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(
    os.environ.get("MCP_LAB_INPUT_TEST") != "1"
    or os.environ.get("MCP_LAB_POSTGRES_TEST") != "1"
    or os.environ.get("MCP_LAB_DOCKER_TEST") != "1",
    reason="Explicit local Input, native PostgreSQL and real Docker opt-ins required.",
)
@pytest.mark.parametrize("mode", ["D1", "D2", "P1", "P2"])
async def test_local_q05_input_with_real_postgres_mcp_and_docker(tmp_path, mode):
    root = Path(__file__).resolve().parents[2]
    local_suite = Suite(
        root / "fixtures/data_analysis_evals/input_v1", input_directory=root / "Input"
    )
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres").start)
    store = Store(cluster.url)
    try:
        await cleaning_flow(tmp_path, local_suite, mode, store, omit_rules_once=True)
    finally:
        await store.close()
        await asyncio.to_thread(cluster.close)


def test_new_experiment_changes_only_the_approved_token_limit():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    old = load_settings(root / "configs/diagnostics/d1_q01_gap90.yaml")
    new = load_settings(root / "configs/experiments/csv_gap90_300k.yaml")
    assert new.limits.max_observed_tokens == 300000
    assert new == old.model_copy(
        update={"limits": old.limits.model_copy(update={"max_observed_tokens": 300000})}
    )
