"""Run an approved CSV queue, keeping the experiment implementation unchanged.

This host helper launches the existing evaluator CLI, never generated Python. It has
no provider client, retries, crash resume, or permission to replace retained attempts.
"""

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import random
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from mcp_execution_lab.evaluation.grading import grade_identity
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.evaluation.tokens import model_call_rows, token_report
from mcp_execution_lab.orchestration.atomic_json import save_json
from mcp_execution_lab.orchestration.config import load_settings, local_environment
from mcp_execution_lab.orchestration.models import fingerprint
from mcp_execution_lab.orchestration.program_container import docker, image_identity
from mcp_execution_lab.orchestration.provenance import source_identity
from mcp_execution_lab.orchestration.storage import Store, now, runs

MODES = ("D1", "D2", "P1", "P2")
TERMINAL = {"COMPLETED", "STOPPED", "INTERRUPTED", "BUDGET_STOPPED"}
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    save_json(path, value)


def baseline(mode, path, margin):
    status = read(path)
    if status.get("state") != "FINISHED" or status.get("mode") != mode:
        raise ValueError("Baseline must be a finished attempt for the requested mode.")
    duration = (
        datetime.fromisoformat(status["finished_at"]) - datetime.fromisoformat(status["started_at"])
    ).total_seconds()
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Baseline duration must be positive.")
    manifest_path = Path(status["batch_directory"]) / "manifest.json"
    manifest = read(manifest_path)
    episodes = manifest["episodes"]
    if manifest["status"] not in TERMINAL or len(episodes) != 1:
        raise ValueError("Baseline needs one finished evaluation episode.")
    episode = episodes[0]
    if (
        episode["mode"] != mode
        or episode["task_id"] != "input_q01"
        or episode["run_id"] != status["run_id"]
        or episode["status"] in {"RUNNING", "QUEUED"}
    ):
        raise ValueError("Baseline episode identity does not match Q01.")
    return {
        "mode": mode,
        "task_id": "input_q01",
        "run_id": status["run_id"],
        "status_path": str(Path(path).resolve()),
        "status_sha256": digest(path),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": digest(manifest_path),
        "elapsed_seconds": duration,
        "first_check_seconds": math.ceil(duration + margin),
        "source_sha256": manifest["source_sha256"],
        "lock_sha256": manifest["lock_sha256"],
        "configuration_sha256": manifest["configuration_sha256"],
        "suite_sha256": manifest["suite_sha256"],
        "grader_sha256": manifest["grader_sha256"],
    }


def prepare(args):
    waits = (args.margin_seconds, args.poll_seconds, args.startup_delay_seconds)
    if (
        not all(math.isfinite(value) for value in waits)
        or args.margin_seconds < 0
        or args.poll_seconds <= 0
        or args.startup_delay_seconds < 0
    ):
        raise ValueError("Provide non-negative waits and a positive polling interval.")
    settings = load_settings(args.config)
    suite = Suite(args.suite, input_directory=args.input_directory)
    retained = getattr(args, "baseline", None) or []
    timing_only = getattr(args, "timing_baseline", None) or []
    if retained and timing_only:
        raise ValueError("Choose reused Q01 results or timing-only baselines, not both.")
    supplied = retained or timing_only
    sources = dict(item.split("=", 1) for item in supplied)
    if len(supplied) != 4 or set(sources) != set(MODES):
        raise ValueError("Provide exactly one Q01 baseline for each of D1/D2/P1/P2.")
    if not args.task or len(set(args.task)) != len(args.task):
        raise ValueError("Select distinct new questions.")
    if retained and "input_q01" in args.task:
        raise ValueError("Q01 cannot be both reused and relaunched; use timing-only baselines.")
    for key in args.task:
        suite.task(key)
    count = len(args.task) * len(MODES)
    if args.max_model_calls < count * settings.limits.max_model_calls:
        raise ValueError("The queue ceiling must cover every new run's full allowance.")
    identities = {
        **source_identity(),
        "configuration_sha256": fingerprint(settings.model_dump(mode="json")),
        "suite_sha256": suite.digest,
        "grader_sha256": grade_identity(),
    }
    baselines = [baseline(mode, sources[mode], args.margin_seconds) for mode in MODES]
    for item in baselines:
        if retained and any(item[key] != value for key, value in identities.items()):
            raise ValueError("A retained Q01 attempt has different source, settings or fixtures.")
    rng = random.Random(args.seed)
    tasks = list(args.task)
    rng.shuffle(tasks)
    episodes = []
    for task in tasks:
        modes = list(MODES)
        rng.shuffle(modes)
        episodes.extend({"task_id": task, "mode": mode, "state": "QUEUED"} for mode in modes)
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    plan = {
        "created_at": now(),
        "queue_id": directory.name,
        "project_root": str(ROOT),
        "configuration": str(args.config.resolve()),
        "suite": str(args.suite.resolve()),
        "input_directory": str(args.input_directory.resolve()),
        "helper_sha256": digest(__file__),
        **identities,
        "seed": args.seed,
        "max_new_model_calls": args.max_model_calls,
        "per_run_model_calls": settings.limits.max_model_calls,
        "request_gap_seconds": settings.model.request_gap_seconds,
        "startup_delay_seconds": args.startup_delay_seconds,
        "poll_seconds": args.poll_seconds,
        "margin_seconds": args.margin_seconds,
        "failure_policy": "record_and_continue",
        "retries": 0,
        "reused_q01": baselines if retained else [],
        "timing_baselines": baselines,
        "episodes": episodes,
        "comparison_note": (
            "Exploratory collection of separate batches; retained Q01 is labeled reused."
            if retained
            else "Fresh exploratory attempts on one frozen source/settings; historical Q01 "
            "timings schedule checks only; old results and tokens are excluded."
        ),
    }
    save(directory / "plan.json", plan)
    save(
        directory / "status.json",
        {"state": "PREPARED", "plan_sha256": digest(directory / "plan.json")},
    )
    return plan


@contextmanager
def queue_lock(path):
    """OS-owned lock releases after a crash; the per-queue claim still forbids resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def verify(plan):
    if Path(plan["project_root"]).resolve() != ROOT:
        raise ValueError("Queue belongs to another checkout.")
    settings = load_settings(Path(plan["configuration"]))
    suite = Suite(plan["suite"], input_directory=plan["input_directory"])
    current = {
        **source_identity(),
        "configuration_sha256": fingerprint(settings.model_dump(mode="json")),
        "suite_sha256": suite.digest,
        "grader_sha256": grade_identity(),
        "helper_sha256": digest(__file__),
    }
    if any(plan[key] != value for key, value in current.items()):
        raise ValueError(
            "Source, helper, settings or inputs changed; queue will not launch more work."
        )
    for item in [*plan["reused_q01"], *plan.get("timing_baselines", [])]:
        for name in ("status", "manifest"):
            if digest(item[name + "_path"]) != item[name + "_sha256"]:
                raise ValueError("Q01 comparison or timing evidence changed.")
    return settings


async def preflight(store, settings, *, python_mode):
    active = await store.transact(
        lambda connection: list(
            connection.execute(
                select(runs.c.id).where(runs.c.status.in_(["CREATED", "EXECUTING"]))
            ).scalars()
        )
    )
    if active:
        raise RuntimeError("An unfinished application run needs inspection before another launch.")
    if os.name == "nt" and settings.model.provider == "codex":
        process = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "@(Get-CimInstance Win32_Process -Filter \"Name = 'codex.exe'\" "
            "-ErrorAction Stop | Where-Object { $_.CommandLine -match "
            "'(?:^|\\s)exec(?:\\s|$)' }).Count",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=20)
        if process.returncode or output.strip() != b"0":
            raise RuntimeError("Another Codex exec is active, or its state could not be checked.")
    if python_mode:
        await image_identity(settings.program_runner)
        if (await docker("ps", "-aq", "--filter", "name=mcp-lab-p1-")).strip():
            raise RuntimeError("An existing lab container needs inspection before another launch.")


def command(plan, episode, output):
    return [
        sys.executable,
        "-m",
        "mcp_execution_lab.cli",
        "eval",
        "--suite",
        plan["suite"],
        "--input-directory",
        plan["input_directory"],
        "run",
        "--config",
        plan["configuration"],
        "--task",
        episode["task_id"],
        "--modes",
        episode["mode"],
        "--repeats",
        "1",
        "--seed",
        str(plan["seed"]),
        "--max-model-calls",
        str(plan["per_run_model_calls"]),
        "--output",
        str(output),
    ]


async def watch(process, output, first_seconds, poll_seconds, update, *, sleep=asyncio.sleep):
    """Timing only chooses when to inspect; neither a clock nor a file can imply a pass."""
    await sleep(first_seconds)
    while True:
        await update()
        if process.returncode is not None:
            paths = list(output.glob("*/manifest.json"))
            if len(paths) != 1:
                raise RuntimeError("Exited evaluator did not save exactly one batch manifest.")
            manifest = read(paths[0])
            return paths[0], manifest
        await sleep(poll_seconds)


async def collection_report(store, directory, plan, state):
    """Export calls without prompts/answers; do not manufacture a matched batch."""
    entries = [{**item, "state": "REUSED"} for item in plan["reused_q01"]] + state["episodes"]
    calls, rows = [], []
    for entry in entries:
        row = {
            key: entry.get(key) for key in ("task_id", "mode", "state", "run_id", "manifest_path")
        }
        if entry.get("run_id"):
            run = await store.run(entry["run_id"])
            records = await store.list_records(entry["run_id"])
            row["execution_status"] = run["status"]
            row["database_records"] = len(records)
            calls.extend(
                {"task_id": entry["task_id"], "origin": entry["state"], **call}
                for call in model_call_rows(run, records)
            )
        rows.append(row)
    save(
        directory / "collection.json",
        {
            "queue_id": plan["queue_id"],
            "updated_at": now(),
            "comparison_note": plan["comparison_note"],
            "attempts": rows,
            "tokens_by_mode": {
                mode: token_report([call for call in calls if call["mode"] == mode])
                for mode in MODES
            },
        },
    )
    if calls:
        with (directory / "model_calls.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(calls[0]))
            writer.writeheader()
            writer.writerows(calls)
    progress(directory, plan, state)


def progress(directory, plan, state):
    """Refresh the readable view on state changes, without model or database calls."""
    lines = [
        "# Evaluation queue",
        "",
        f"State: {state['state']}",
        f"New runs checked: {state['finished_new_runs']} / {len(state['episodes'])}.",
        (
            f"{len(plan['reused_q01'])} Q01 attempts are reused."
            if plan["reused_q01"]
            else "All result attempts are fresh; historical Q01 timings only choose checks."
        ),
        f"Last update (UTC): {state.get('updated_at', now())}",
        "FINISHED means ended, not a correct answer.",
        "",
        "| Question | Mode | Queue state | Execution | Answer checks | Run |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {row['task_id']} | {row['mode']} | {row['state']} | "
        f"{row.get('execution_status', '')} | {row.get('evaluation_status', '')} | "
        f"{row.get('run_id', '')} |"
        for row in [
            *[{**item, "state": "REUSED"} for item in plan["reused_q01"]],
            *state["episodes"],
        ]
    )
    if state.get("current_index") is not None:
        current = state["episodes"][state["current_index"]]
        lines += ["", f"Current mode: {current['mode']}."]
        if current.get("next_check_at") and current["state"] == "RUNNING":
            lines += [f"Next saved-result check (UTC): {current['next_check_at']}."]
    if state.get("next_start_not_before") and state["state"] == "BETWEEN_RUNS":
        lines += ["", f"Next launch no earlier than (UTC): {state['next_start_not_before']}."]
    (directory / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_queue(directory):
    directory = directory.resolve()
    plan_path, status_path = directory / "plan.json", directory / "status.json"
    plan, initial = read(plan_path), read(status_path)
    if initial["state"] != "PREPARED" or digest(plan_path) != initial["plan_sha256"]:
        raise ValueError(
            "Only an unchanged, prepared queue can start; there is no automatic resume."
        )
    verify(plan)
    state = {
        "state": "STARTING",
        "queue_id": plan["queue_id"],
        "pid": os.getpid(),
        "started_at": now(),
        "plan_sha256": digest(plan_path),
        "reused_q01_count": len(plan["reused_q01"]),
        "finished_new_runs": 0,
        "new_model_calls": 0,
        "episodes": plan["episodes"],
    }

    async def update():
        state["updated_at"] = now()
        save(status_path, state)
        progress(directory, plan, state)

    with queue_lock(ROOT / ".runtime" / "evaluation_queue.lock"):
        with (directory / "launch.claim").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "started_at": now()}))
        await update()
        store = None
        child = waiter = None
        try:
            url, _ = local_environment(ROOT)
            store = Store(url)
            await collection_report(store, directory, plan, state)
            await asyncio.sleep(plan["startup_delay_seconds"])
            baselines = {
                item["mode"]: item for item in plan.get("timing_baselines", plan["reused_q01"])
            }
            for index, episode in enumerate(state["episodes"]):
                settings = verify(plan)
                if digest(plan_path) != state["plan_sha256"]:
                    raise ValueError("Queue plan changed during execution.")
                if (
                    state["new_model_calls"] + plan["per_run_model_calls"]
                    > plan["max_new_model_calls"]
                ):
                    raise RuntimeError("The next run would exceed the approved call ceiling.")
                await preflight(store, settings, python_mode=episode["mode"] in {"P1", "P2"})
                state["state"] = "RUNNING"
                state["current_index"] = index
                output = directory / f"episode_{index + 1:02d}" / "batches"
                output.mkdir(parents=True, exist_ok=False)
                log = output.parent / "live.log"
                first = baselines[episode["mode"]]["first_check_seconds"]
                episode.update(
                    state="RUNNING",
                    started_at=now(),
                    output=str(output),
                    log_path=str(log),
                    first_check_seconds=first,
                    next_check_at=(datetime.now(UTC) + timedelta(seconds=first)).isoformat(),
                )
                with log.open("wb") as stream:
                    child = await asyncio.create_subprocess_exec(
                        *command(plan, episode, output),
                        cwd=ROOT,
                        stdout=stream,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    episode["pid"] = child.pid
                    waiter = asyncio.create_task(child.wait())
                    await update()

                    async def checking(current=episode):
                        current["last_checked_at"] = now()
                        current["next_check_at"] = (
                            datetime.now(UTC) + timedelta(seconds=plan["poll_seconds"])
                        ).isoformat()
                        await update()

                    try:
                        path, manifest = await watch(
                            child, output, first, plan["poll_seconds"], checking
                        )
                        await waiter
                        saved = manifest["episodes"]
                        if len(saved) != 1 or any(
                            saved[0][key] != episode[key] for key in ("task_id", "mode")
                        ):
                            raise RuntimeError("Saved batch identity differs from the queued run.")
                        for key in (
                            "source_sha256",
                            "configuration_sha256",
                            "suite_sha256",
                            "grader_sha256",
                        ):
                            if manifest[key] != plan[key]:
                                raise RuntimeError(
                                    "Saved batch identity differs from the approved queue."
                                )
                        run_id = saved[0].get("run_id")
                        if not run_id:
                            raise RuntimeError("No run record was saved; child launch failed.")
                        run = await store.run(run_id)
                        records = await store.list_records(run_id)
                        calls = sum(row["kind"] == "model_call" for row in records)
                        state["new_model_calls"] += calls
                        episode.update(
                            state="FINISHED",
                            manifest_path=str(path),
                            run_id=run_id,
                            batch_id=manifest["batch_id"],
                            evaluation_status=saved[0]["status"],
                            execution_status=run["status"],
                            model_calls=calls,
                            cli_exit_code=child.returncode,
                            database_records=len(records),
                        )
                        if manifest["status"] not in TERMINAL:
                            # Account for the saved run even when its final file write failed.
                            episode["evaluation_status"] = "UNRESOLVED_SAVE_ERROR"
                            episode["original_manifest_status"] = manifest["status"]
                            raise RuntimeError("Exited evaluator left an unfinished manifest.")
                    except Exception as exc:
                        episode.update(state="CHECK_ERROR", error_type=type(exc).__name__)
                    if episode.get("run_id"):
                        await store.put(
                            episode["run_id"],
                            "evaluation_queue_episode",
                            {
                                "queue_id": plan["queue_id"],
                                "plan_sha256": state["plan_sha256"],
                                "queue_index": index,
                                "task_id": episode["task_id"],
                                "mode": episode["mode"],
                                "batch_id": episode["batch_id"],
                                "queue_state": episode["state"],
                            },
                        )
                    episode["finished_at"] = now()
                    state["finished_new_runs"] += 1
                    await update()
                await collection_report(store, directory, plan, state)
                # This conservative gap starts after exit was observed, outside run timing.
                if index + 1 < len(state["episodes"]):
                    state["state"] = "BETWEEN_RUNS"
                    state["next_start_not_before"] = (
                        datetime.now(UTC) + timedelta(seconds=plan["request_gap_seconds"])
                    ).isoformat()
                    await update()
                    await asyncio.sleep(plan["request_gap_seconds"])
            state["state"] = "FINISHED"
            await collection_report(store, directory, plan, state)
        except BaseException as exc:
            state.update(state="STOPPED", error_type=type(exc).__name__)
            # Do not kill or replay uncertain work. An owned child may still be finishing.
            if child is not None and child.returncode is None:
                state["inspect_child_pid"] = child.pid
            raise
        finally:
            state["finished_at"] = now()
            await update()
            if store is not None:
                await store.close()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("prepare", help="Save a queue without contacting a model or DB")
    create.add_argument("--directory", type=Path, required=True)
    create.add_argument("--config", type=Path, required=True)
    create.add_argument("--suite", type=Path, required=True)
    create.add_argument("--input-directory", type=Path, required=True)
    timing = create.add_mutually_exclusive_group(required=True)
    timing.add_argument(
        "--baseline", action="append", help="MODE=status.json; reuse matching Q01 results"
    )
    timing.add_argument(
        "--timing-baseline", action="append", help="MODE=status.json; use Q01 durations only"
    )
    create.add_argument("--task", action="append", required=True)
    create.add_argument("--margin-seconds", type=float, required=True)
    create.add_argument("--poll-seconds", type=float, required=True)
    create.add_argument("--max-model-calls", type=int, required=True)
    create.add_argument("--seed", type=int, default=0)
    create.add_argument("--startup-delay-seconds", type=float, default=60)
    for action in ("run", "status"):
        actions.add_parser(action).add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare(args)
            print(json.dumps({"state": "PREPARED", "new_runs": len(result["episodes"])}))
        elif args.action == "run":
            result = asyncio.run(run_queue(args.directory))
            print(
                json.dumps(
                    {"state": result["state"], "finished_new_runs": result["finished_new_runs"]}
                )
            )
        else:
            value = read(args.directory / "status.json")
            print(json.dumps(value, indent=2))
    except Exception as exc:
        # Connection exceptions can include credentials; retain only the error type here.
        print(json.dumps({"state": "ERROR", "error_type": type(exc).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
