"""Small code-audit probes. Fixed inputs, no real model calls, no production DB.

Run from the project root with .venv/Scripts/python.exe.
The constructed run is an audit example, not a generated research episode.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

from dotenv import dotenv_values

from mcp_execution_lab.agents.combining.models import Recipe, Rules
from mcp_execution_lab.agents.combining.operations import combine
from mcp_execution_lab.agents.common.models import Fact, Table
from mcp_execution_lab.agents.common.operations import render_text
from mcp_execution_lab.evaluation.grading import evaluate
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.orchestration.budget import Budget
from mcp_execution_lab.orchestration.config import ModelConfig
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.model import ModelCalls
from mcp_execution_lab.orchestration.models import FileRef, Limits, MainTask, OrchestrationError
from mcp_execution_lab.orchestration.provenance import source_identity
from mcp_execution_lab.orchestration.storage import Store


class NeverCalled:
    provider = "audit-no-provider"
    is_model = False
    calls = 0

    async def generate(self, request, directory):
        self.calls += 1
        raise AssertionError("An audit probe must not make a model request.")


async def main():
    root = Path.cwd()
    scratch = root / ".runtime/cross_check"
    scratch.mkdir(parents=True, exist_ok=True)
    result = {
        "audit_date": "2026-10-23",
        "purpose": "Code audit, deterministic probes only",
        **source_identity(),
    }
    env = dotenv_values(root / ".env") if (root / ".env").exists() else {}
    url = os.environ.get("MCP_LAB_DATABASE_URL") or env.get("MCP_LAB_DATABASE_URL") or ""
    result["workspace"] = {
        "env_file_exists": (root / ".env").exists(),
        "database_url_present": bool(url),
        "database_url_placeholder": "YOUR_" in url,
        "codex_executable_present": bool(shutil.which("codex")),
    }

    def table(name, row):
        return Table(
            ref=FileRef(id=name, run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64),
            columns=list(row),
            rows=[row],
        )

    columns, rows, _, details = combine(
        [
            table("left", {"id": "001", "amount": "10"}),
            table("middle", {"id": "001", "segment": "Personal"}),
            table("right", {"id": "001", "category": "Home"}),
        ],
        Recipe(operation="join", keys=["id"], join_type="left"),
        Rules(keys=["id"]),
    )
    result["three_file_join"] = {
        "input_files": 3,
        "columns": columns,
        "rows": rows,
        "join_checks": len(details.checks),
    }
    try:
        render_text("Total: 999 dollars.", [])
    except ValueError:
        rejected = True
    else:
        rejected = False
    result["numeric_text_check"] = {
        "bare_digits_rejected": rejected,
        "number_in_words_accepted": render_text("Total: twenty dollars.", []),
        "fact_marker": render_text(
            "Total: {{fact:total}}.", [Fact(id="total", label="Total", value=10)]
        ),
    }

    store = Store("sqlite://", allow_sqlite_for_tests=True)
    try:
        await store.initialize()
        run_id = await store.create_run({"purpose": "prompt-size audit"})
        budget = Budget(Limits(max_prompt_chars=1000))
        client = NeverCalled()
        files = Files(scratch / "files", store, budget.limits)
        model = ModelCalls(
            client, ModelConfig(provider="command", model_id="audit"), store, files, budget
        )
        try:
            await model.ask(run_id, "main_task", MainTask, {"long_context": "x" * 2000})
        except OrchestrationError as exc:
            code = exc.code
        else:
            code = "unexpected success"
        result["oversize_prompt_accounting"] = {
            "code": code,
            "budget_model_calls": budget.model_calls,
            "saved_model_call_records": len(await store.list_records(run_id, "model_call")),
            "provider_requests": client.calls,
        }

        suite = Suite(root / "fixtures/data_analysis_evals/development")
        task = suite.task("sales_total")
        run_id = await store.create_run(
            {
                "request": task.query,
                "mode": "D1",
                "is_model": False,
                "exploratory": True,
                "execution_kind": "audit_constructed",
                **source_identity(),
            }
        )
        files = Files(scratch / "files", store, Limits())
        await files.register_csv(run_id, suite.path("orders.csv"))
        await files.register_csv(run_id, suite.path("customers.csv"))
        answer = await files.put_json(run_id, {"rows": [{"total_amount": "6357.50"}]})
        await store.put(
            run_id,
            "execution_result",
            {"status": "COMPLETED", "outputs": {"answer": answer.model_dump()}},
        )
        await store.transition(run_id, "COMPLETED")
        grade = await evaluate(store, files, suite, task.id, run_id)
        result["manual_grade_extra_input"] = {
            "required_input_files": task.files,
            "registered_input_files": ["orders.csv", "customers.csv"],
            "task_success": grade["task_success"],
            "execution_kind": "audit_constructed, not model-generated",
        }
    finally:
        await store.close()
    output = root / "docs/Cross-check/evidence/probes.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
