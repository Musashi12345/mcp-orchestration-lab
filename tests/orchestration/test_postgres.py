import asyncio
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mcp_execution_lab.orchestration.config import Settings, load_settings
from mcp_execution_lab.orchestration.files import Files
from mcp_execution_lab.orchestration.models import FileRef, Limits, fingerprint
from mcp_execution_lab.orchestration.service import Application
from mcp_execution_lab.orchestration.storage import Store, identity, links, records, runs

from .postgres import LocalPostgres

pytestmark = pytest.mark.skipif(
    os.environ.get("MCP_LAB_POSTGRES_TEST") != "1",
    reason="Set MCP_LAB_POSTGRES_TEST=1 for a temporary native PostgreSQL instance.",
)


async def test_native_postgres_planner_executor_ownership_and_live_records(lab, tmp_path):
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres").start)
    store = Store(cluster.url)
    try:
        await store.initialize()
        await store.initialize()  # The versioned initialization is safe to repeat.
        lab.client.store = store
        settings = Settings(servers=lab.servers, limits=lab.limits)
        application = Application(store, lab.files.root, settings, client=lab.client)
        handoff = await application.plan("Count the rows", [lab.source])
        result = await application.execute(handoff.run_id)
        assert result["status"] == "COMPLETED"
        assert len(await store.list_records(handoff.run_id, "tool_attempt")) == 2
        assert len(await store.list_records(handoff.run_id, "model_call")) == 4
        assert len(await store.history(handoff.run_id)) > 30
        link_rows = await store.transact(
            lambda connection: (
                connection.execute(select(links).where(links.c.run_id == handoff.run_id))
                .mappings()
                .all()
            )
        )
        assert link_rows
        other = await store.create_run({})
        with pytest.raises(IntegrityError):
            await store.put(other, "plan", {}, parents=[("plan", handoff.plan_record)])
        assert await store.list_records(other) == []
        cached = await store.get(handoff.run_id, handoff.cache_record)
        assert cached["payload"]["fingerprint"] == handoff.cache.digest
        assert (
            fingerprint(settings.model_dump(mode="json"))
            == (await store.list_records(handoff.run_id, "configuration"))[0]["payload"][
                "fingerprint"
            ]
        )
        # Independent connections can observe committed records before run completion.
        reader = Store(cluster.url)
        try:
            assert (await reader.get(handoff.run_id, handoff.plan_record))["kind"] == "plan"
        finally:
            await reader.close()
        await store.transact(
            lambda connection: connection.execute(select(records).limit(1)).first()
        )
    finally:
        await store.close()
        await asyncio.to_thread(cluster.close)


@pytest.mark.skipif(
    os.environ.get("MCP_LAB_CODEX_TEST") != "1",
    reason="Explicit opt-in required for subscription-consuming Codex smoke.",
)
async def test_bounded_live_codex_planner_with_native_postgres_and_real_mcp(
    lab, tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[2]
    live_root = root / "runs" / "data_analysis_smoke" / identity("validation")
    monkeypatch.setenv("MCP_LAB_DATA_ROOT", str(live_root))
    configured = load_settings(root / "configs" / "agents_stdio.yaml").model
    settings = Settings(
        servers=lab.servers,
        model=configured.model_copy(update={"timeout_seconds": 90}),
        limits=Limits(max_model_calls=8, max_observed_tokens=60000, run_seconds=600),
    )
    cluster = await asyncio.to_thread(LocalPostgres(tmp_path / "postgres_live").start)
    store = Store(cluster.url)
    try:
        await store.initialize()
        app = Application(store, live_root, settings)
        handoff = await app.plan(
            "Read the attached CSV through an available tool and report its number of data rows.",
            [lab.source],
        )
        result = await app.execute(handoff.run_id)
        assert result["status"] == "COMPLETED"
        attempts = await store.list_records(handoff.run_id, "tool_attempt")
        assert any(
            row["payload"]["arguments"].get("dataset") == handoff.datasets[0].ref.model_dump()
            for row in attempts
        )
        files = Files(live_root, store, settings.limits)
        values = [
            await files.read_json(handoff.run_id, FileRef.model_validate(ref))
            for ref in result["outputs"].values()
        ]

        def contains_count(value):
            if isinstance(value, dict):
                return any(contains_count(part) for part in value.values())
            if isinstance(value, list):
                return any(contains_count(part) for part in value)
            return value == 2

        assert any(contains_count(value) for value in values)
    finally:
        captured = await store.transact(
            lambda connection: [dict(row) for row in connection.execute(select(runs)).mappings()]
        )
        for run in captured:
            evidence = root / "reports" / "orchestration_validation" / run["id"]
            evidence.mkdir(parents=True, exist_ok=False)
            (evidence / "audit.json").write_text(
                json.dumps(
                    {
                        "run": run,
                        "file_root": str(live_root.relative_to(root)),
                        "records": await store.list_records(run["id"]),
                        "events": await store.history(run["id"]),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        await store.close()
        await asyncio.to_thread(cluster.close)
