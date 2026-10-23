"""Local PostgreSQL-backed planner and DAG executor commands."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from .config import load_settings, local_environment
from .service import Application
from .storage import Store


async def dispatch(args):
    root = Path.cwd()
    url, data_root = local_environment(root)
    store = Store(url)
    try:
        await store.initialize()
        if args.action == "db-init":
            return {"status": "READY", "schema_version": 1, "database": "local PostgreSQL"}
        if args.action == "inspect":
            return {
                "run": await store.run(args.run),
                "records": await store.list_records(args.run),
                "events": await store.history(args.run),
            }
        application = Application(store, data_root, load_settings(args.config))
        if args.action == "execute":
            return await application.execute(args.run)
        handoff = await application.plan(
            args.query, args.csv, mode=args.mode, encoding=args.encoding, delimiter=args.delimiter
        )
        if args.action == "run":
            return await application.execute(handoff.run_id)
        return {
            "run_id": handoff.run_id,
            "status": "READY_FOR_EXECUTION",
            "plan_id": handoff.plan_record,
            "tool_cache_fingerprint": handoff.cache.digest,
            "handoff": handoff.model_dump(mode="json"),
        }
    finally:
        await store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Data-analysis planning and DAG execution")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("db-init", help="Create the project tables in configured local PostgreSQL")
    inspect = actions.add_parser("inspect", help="Read a run's live records")
    inspect.add_argument("--run", required=True)
    execute = actions.add_parser("execute", help="Execute an accepted, unstarted plan")
    execute.add_argument("--run", required=True)
    execute.add_argument("--config", type=Path, required=True)
    for name in ("plan", "run"):
        command = actions.add_parser(
            name, help="Plan only" if name == "plan" else "Plan then execute"
        )
        command.add_argument("--query", required=True)
        command.add_argument("--csv", type=Path, action="append", required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--mode", choices=["D1", "D2"], default="D1")
        command.add_argument("--encoding", default="utf-8-sig")
        command.add_argument("--delimiter", default=",")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(dispatch(args))
    except SQLAlchemyError:
        print(
            json.dumps(
                {
                    "error": "DATABASE_ERROR",
                    "message": "Could not use PostgreSQL. Check .env and database permissions.",
                }
            )
        )
        return 2
    except (ValueError, OSError, TimeoutError) as exc:
        print(
            json.dumps(
                {"error": getattr(exc, "code", type(exc).__name__), "message": str(exc)[:4000]}
            )
        )
        return 2
    print(json.dumps(result, indent=2))
    return (
        0 if result.get("status", "READY") in {"READY", "READY_FOR_EXECUTION", "COMPLETED"} else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
