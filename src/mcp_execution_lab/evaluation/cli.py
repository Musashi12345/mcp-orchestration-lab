"""Public task listing, native PostgreSQL grading, paired batches, and human review."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from ..orchestration.config import load_settings, local_environment
from ..orchestration.files import Files
from ..orchestration.models import Limits
from ..orchestration.storage import Store
from .batch import report_batch, run_batch
from .grading import evaluate, review
from .suite import Suite


async def dispatch(args):
    suite = Suite(args.suite)
    if args.action == "list":
        return {
            "suite": suite.version,
            "suite_sha256": suite.digest,
            "tasks": [task.model_dump() for task in suite.tasks],
        }
    url, data_root = local_environment(Path.cwd())
    store = Store(url)
    try:
        await store.initialize()
        if args.action == "grade":
            return await evaluate(
                store, Files(data_root, store, Limits()), suite, args.task, args.run
            )
        if args.action == "review":
            return await review(
                store,
                args.run,
                args.evaluation,
                passed=args.decision == "pass",
                reviewer=args.reviewer,
                note=args.note,
            )
        if args.action == "report":
            return await report_batch(store, args.directory)
        return await run_batch(
            store,
            data_root,
            load_settings(args.config),
            suite,
            args.output,
            task_ids=args.task,
            modes=args.modes,
            repeats=args.repeats,
            seed=args.seed,
            max_model_calls=args.max_model_calls,
        )
    finally:
        await store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Data-analysis development evaluations")
    parser.add_argument(
        "--suite", type=Path, default=Path("fixtures/data_analysis_evals/development")
    )
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="List public questions without database or model work")
    grade = actions.add_parser("grade", help="Independently grade an ended run")
    grade.add_argument("--run", required=True)
    grade.add_argument("--task", required=True)
    human = actions.add_parser("review", help="Save a named human's review decision")
    human.add_argument("--run", required=True)
    human.add_argument("--evaluation", required=True)
    human.add_argument("--decision", choices=["pass", "fail"], required=True)
    human.add_argument("--reviewer", required=True)
    human.add_argument("--note", required=True)
    batch = actions.add_parser("run", help="Run a fresh paired batch; uses the configured model")
    batch.add_argument("--config", required=True, type=Path)
    batch.add_argument("--task", action="append")
    batch.add_argument("--modes", choices=["D1", "D2", "P1", "P2"], nargs="+", default=["D1", "D2"])
    batch.add_argument("--repeats", type=int, default=1)
    batch.add_argument("--seed", type=int, default=0)
    batch.add_argument("--max-model-calls", type=int, required=True)
    batch.add_argument("--output", type=Path, default=Path("reports/evaluation_batches"))
    report = actions.add_parser("report", help="Refresh a batch report after human review")
    report.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(dispatch(args))
    except SQLAlchemyError:
        print(
            json.dumps(
                {
                    "error": "DATABASE_ERROR",
                    "message": "Check the local PostgreSQL connection in .env.",
                }
            )
        )
        return 2
    except (ValueError, OSError, KeyError) as exc:
        print(
            json.dumps(
                {"error": getattr(exc, "code", type(exc).__name__), "message": str(exc)[:2000]}
            )
        )
        return 2
    print(json.dumps(result, indent=2))
    if args.action == "run":
        return 0 if result["manifest"]["status"] == "COMPLETED" else 1
    return 1 if result.get("status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
