"""Short durable transactions; synchronous drivers run off the event-loop thread."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.pool import StaticPool

from .models import OrchestrationError

metadata = MetaData()
versions = Table("lab_schema_versions", metadata, Column("version", Integer, primary_key=True))
runs = Table(
    "lab_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("status", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("sequence", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False),
)
records = Table(
    "lab_records",
    metadata,
    Column("id", String, primary_key=True),
    Column("run_id", String, nullable=False),
    Column("kind", String, nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", String, nullable=False),
    UniqueConstraint("run_id", "id"),
    ForeignKeyConstraint(["run_id"], ["lab_runs.id"]),
)
links = Table(
    "lab_record_links",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("source_id", String, primary_key=True),
    Column("target_id", String, primary_key=True),
    Column("role", String, primary_key=True),
    ForeignKeyConstraint(["run_id", "source_id"], ["lab_records.run_id", "lab_records.id"]),
    ForeignKeyConstraint(["run_id", "target_id"], ["lab_records.run_id", "lab_records.id"]),
)
events = Table(
    "lab_events",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("kind", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", String, nullable=False),
    ForeignKeyConstraint(["run_id"], ["lab_runs.id"]),
)
steps = Table(
    "lab_plan_steps",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("plan_id", String, primary_key=True),
    Column("step_id", String, primary_key=True),
    Column("state", String, nullable=False),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(["run_id", "plan_id"], ["lab_records.run_id", "lab_records.id"]),
)


def identity(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """PostgreSQL in production; SQLite is an explicit test seam only.

    Using the sync psycopg driver in worker threads allows Windows subprocess-based
    MCP clients to retain their required Proactor event loop.
    """

    def __init__(self, url: str, *, allow_sqlite_for_tests: bool = False):
        if not url.startswith("postgresql+psycopg://") and not allow_sqlite_for_tests:
            raise OrchestrationError("DATABASE_CONFIG", "A local PostgreSQL URL is required.")
        options: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("postgresql"):
            options["connect_args"] = {"connect_timeout": 5}
        if url.startswith("sqlite"):
            options.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.engine = create_engine(url, **options)
        self.lock = asyncio.Lock()
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    async def transact(self, action):
        def commit():
            with self.engine.begin() as connection:
                return action(connection)

        async with self.lock:
            pending = asyncio.create_task(asyncio.to_thread(commit))
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                # A cancelled coroutine must not release the connection while its
                # background transaction is still committing or rolling back.
                await pending
                raise

    async def initialize(self):
        def migrate(connection):
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(68434237401)")
            metadata.create_all(connection)
            existing = list(connection.execute(select(versions.c.version)).scalars())
            if not existing:
                connection.execute(insert(versions).values(version=1))
            elif existing != [1]:
                raise OrchestrationError("DATABASE_VERSION", "Unsupported database schema version.")

        await self.transact(migrate)

    def _event(self, connection, run_id, kind, payload):
        sequence = connection.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(sequence=runs.c.sequence + 1)
            .returning(runs.c.sequence)
        ).scalar_one()
        connection.execute(
            insert(events).values(
                run_id=run_id, sequence=sequence, kind=kind, payload=payload, created_at=now()
            )
        )

    async def create_run(self, payload: dict, *, run_id: str | None = None) -> str:
        run_id = run_id or identity("run")

        def create(connection):
            connection.execute(
                insert(runs).values(
                    id=run_id, status="CREATED", payload=payload, sequence=0, created_at=now()
                )
            )
            self._event(connection, run_id, "run_created", payload)

        await self.transact(create)
        return run_id

    async def event(self, run_id, kind, payload):
        await self.transact(lambda connection: self._event(connection, run_id, kind, payload))

    async def transition(self, run_id, status, detail=None, *, expected=None):
        def change(connection):
            query = update(runs).where(runs.c.id == run_id)
            if expected is not None:
                query = query.where(runs.c.status == expected)
            changed = connection.execute(query.values(status=status))
            if changed.rowcount != 1:
                raise OrchestrationError("RUN_STATE", "Run is no longer in the expected state.")
            self._event(connection, run_id, "run_state", {"state": status, "detail": detail})

        await self.transact(change)

    async def put(self, run_id, kind, payload, *, parents=(), record_id=None) -> str:
        record_id = record_id or identity(kind)

        def save(connection):
            connection.execute(
                insert(records).values(
                    id=record_id, run_id=run_id, kind=kind, payload=payload, created_at=now()
                )
            )
            for role, parent_id in parents:
                connection.execute(
                    insert(links).values(
                        run_id=run_id, source_id=record_id, target_id=parent_id, role=role
                    )
                )
            self._event(connection, run_id, kind + "_saved", {"record_id": record_id})

        await self.transact(save)
        return record_id

    async def finish(self, run_id, record_id, payload):
        def save(connection):
            kind = connection.execute(
                select(records.c.kind).where(records.c.id == record_id, records.c.run_id == run_id)
            ).scalar_one_or_none()
            if kind not in {
                "stage",
                "model_call",
                "tool_attempt",
                "review",
                "worker_call",
                "file_write",
            }:
                raise OrchestrationError(
                    "RECORD_STATE", "Only active call or stage records may change."
                )
            changed = connection.execute(
                update(records)
                .where(records.c.id == record_id, records.c.run_id == run_id)
                .values(payload=payload)
            )
            if changed.rowcount != 1:
                raise OrchestrationError("RECORD_OWNERSHIP", "Unknown record for this run.")
            self._event(
                connection,
                run_id,
                "record_finished",
                {"record_id": record_id, "status": payload.get("status")},
            )

        await self.transact(save)

    async def get(self, run_id, record_id):
        row = await self.transact(
            lambda connection: (
                connection.execute(
                    select(records).where(records.c.id == record_id, records.c.run_id == run_id)
                )
                .mappings()
                .first()
            )
        )
        if row is None:
            raise OrchestrationError("RECORD_OWNERSHIP", "Unknown record for this run.")
        return dict(row)

    async def list_records(self, run_id, kind=None):
        query = select(records).where(records.c.run_id == run_id)
        if kind:
            query = query.where(records.c.kind == kind)
        return await self.transact(
            lambda connection: [
                dict(row)
                for row in connection.execute(query.order_by(records.c.created_at)).mappings()
            ]
        )

    async def history(self, run_id):
        return await self.transact(
            lambda connection: [
                dict(row)
                for row in connection.execute(
                    select(events).where(events.c.run_id == run_id).order_by(events.c.sequence)
                ).mappings()
            ]
        )

    async def run(self, run_id):
        row = await self.transact(
            lambda connection: (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
            )
        )
        return dict(row)

    async def register_steps(self, run_id, plan_id, plan):
        await self.register_calls(run_id, plan_id, plan.steps)

    async def register_calls(self, run_id, plan_id, calls):
        """Save declared call identities without requiring a graph representation."""

        def save(connection):
            for step in calls:
                connection.execute(
                    insert(steps).values(
                        run_id=run_id,
                        plan_id=plan_id,
                        step_id=step.id,
                        state="WAITING",
                        payload={"definition": step.model_dump(mode="json")},
                    )
                )
            self._event(connection, run_id, "steps_registered", {"plan_id": plan_id})

        await self.transact(save)

    async def step_state(self, run_id, plan_id, step_id, state, detail=None):
        def save(connection):
            current = connection.execute(
                select(steps.c.state).where(
                    steps.c.run_id == run_id, steps.c.plan_id == plan_id, steps.c.step_id == step_id
                )
            ).scalar_one_or_none()
            allowed = {
                "WAITING": {"READY", "SKIPPED", "BLOCKED", "FAILED", "REPLACED", "CANCELLED"},
                "READY": {"RUNNING", "REPLACED", "CANCELLED", "FAILED"},
                "RUNNING": {"SUCCEEDED", "FAILED", "UNCERTAIN", "CANCELLED"},
                "BLOCKED": {"REPLACED"},
            }
            if state not in allowed.get(current, set()):
                raise OrchestrationError(
                    "STEP_STATE", f"Invalid step transition {current} -> {state}."
                )
            changed = connection.execute(
                update(steps)
                .where(
                    steps.c.run_id == run_id, steps.c.plan_id == plan_id, steps.c.step_id == step_id
                )
                .values(state=state)
            )
            if changed.rowcount != 1:
                raise OrchestrationError("STEP_OWNERSHIP", "Unknown step for this plan and run.")
            self._event(
                connection,
                run_id,
                "step_state",
                {"plan_id": plan_id, "step_id": step_id, "state": state, "detail": detail},
            )

        await self.transact(save)

    async def close(self):
        await asyncio.to_thread(self.engine.dispose)
