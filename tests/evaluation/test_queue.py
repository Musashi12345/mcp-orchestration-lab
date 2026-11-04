"""Queue controls use saved fixtures; no provider call is permitted in these tests."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_execution_lab.evaluation.grading import grade_identity
from mcp_execution_lab.evaluation.suite import Suite
from mcp_execution_lab.orchestration.config import load_settings
from mcp_execution_lab.orchestration.models import fingerprint
from mcp_execution_lab.orchestration.provenance import source_identity
from mcp_execution_lab.orchestration.storage import Store

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "evaluation_queue_helper", ROOT / "scripts/evaluation_queue.py"
)
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)
SUITE = ROOT / "fixtures/data_analysis_evals/development"


def arguments(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        json.dumps(
            {
                "servers": [{"id": "fixture", "command": "{python}"}],
                "model": {"provider": "command", "request_gap_seconds": 90},
                "limits": {"max_model_calls": 32},
            }
        )
    )
    settings, suite = load_settings(config), Suite(SUITE)
    identities = {
        **source_identity(),
        "suite_sha256": suite.digest,
        "grader_sha256": grade_identity(),
        "configuration_sha256": fingerprint(settings.model_dump(mode="json")),
    }
    baselines = []
    for mode in queue.MODES:
        directory = tmp_path / mode
        directory.mkdir()
        queue.save(
            directory / "manifest.json",
            {
                **identities,
                "status": "COMPLETED",
                "episodes": [
                    {"task_id": "input_q01", "mode": mode, "run_id": mode, "status": "FAILED"}
                ],
            },
        )
        path = directory / "status.json"
        queue.save(
            path,
            {
                "state": "FINISHED",
                "mode": mode,
                "run_id": mode,
                "batch_directory": str(directory),
                "started_at": "2026-10-26T14:00:00+00:00",
                "finished_at": "2026-10-26T14:08:41.2+00:00",
            },
        )
        baselines.append(f"{mode}={path}")
    return SimpleNamespace(
        config=config,
        suite=SUITE,
        input_directory=SUITE,
        baseline=baselines,
        task=["sales_total", "sales_by_region"],
        margin_seconds=120,
        poll_seconds=60,
        startup_delay_seconds=0,
        max_model_calls=256,
        seed=0,
        directory=tmp_path / "queue",
    )


def test_prepare_reuses_four_attempts_and_schedules_exactly_eight(tmp_path):
    args = arguments(tmp_path)
    result = queue.prepare(args)
    assert len(result["reused_q01"]) == 4
    assert len(result["episodes"]) == 8
    assert {(row["task_id"], row["mode"]) for row in result["episodes"]} == {
        (task, mode) for task in args.task for mode in queue.MODES
    }
    assert all(row["first_check_seconds"] == 642 for row in result["reused_q01"])
    assert result["request_gap_seconds"] == 90
    assert result["retries"] == 0
    assert queue.verify(result) == load_settings(args.config)
    with pytest.raises(FileExistsError):
        queue.prepare(args)


def timing_arguments(tmp_path):
    args = arguments(tmp_path)
    args.timing_baseline, args.baseline = args.baseline, []
    # Historic code/settings must not become part of this fresh comparison.
    for baseline in args.timing_baseline:
        directory = Path(baseline.split("=", 1)[1]).parent
        path = directory / "manifest.json"
        manifest = queue.read(path)
        manifest["source_sha256"] = "historic-source"
        manifest["configuration_sha256"] = "historic-configuration"
        queue.save(path, manifest)
    return args


def test_fresh_queue_uses_old_durations_without_reusing_old_results(tmp_path):
    args = timing_arguments(tmp_path)
    plan = queue.prepare(args)
    assert plan["reused_q01"] == []
    assert len(plan["timing_baselines"]) == 4 and len(plan["episodes"]) == 8
    assert all(item["first_check_seconds"] == 642 for item in plan["timing_baselines"])
    assert plan["source_sha256"] != plan["timing_baselines"][0]["source_sha256"]
    assert queue.verify(plan) == load_settings(args.config)
    timing_status = Path(plan["timing_baselines"][0]["status_path"])
    timing_status.write_text("{}")
    with pytest.raises(ValueError, match="timing evidence changed"):
        queue.verify(plan)


def test_reused_results_still_need_matching_source_and_settings(tmp_path):
    args = timing_arguments(tmp_path)
    args.baseline, args.timing_baseline = args.timing_baseline, []
    with pytest.raises(ValueError, match="different source"):
        queue.prepare(args)


def test_fresh_q01_schedules_four_runs_without_reusing_old_answers(tmp_path):
    args = timing_arguments(tmp_path)
    args.task, args.max_model_calls = ["input_q01"], 128
    # The development suite has other task IDs; provide a public Q01 alias for
    # this host scheduling test, without contacting a model.
    original = queue.Suite

    class PublicQ01(original):
        def task(self, task_id):
            return super().task("sales_total" if task_id == "input_q01" else task_id)

    from unittest.mock import patch

    with patch.object(queue, "Suite", PublicQ01):
        plan = queue.prepare(args)
    assert plan["reused_q01"] == []
    assert len(plan["episodes"]) == 4
    assert {(e["task_id"], e["mode"]) for e in plan["episodes"]} == {
        ("input_q01", mode) for mode in queue.MODES
    }
    assert plan["max_new_model_calls"] == 128 and plan["retries"] == 0


def test_progress_updates_during_a_run_without_database_reads(tmp_path):
    args = timing_arguments(tmp_path)
    plan = queue.prepare(args)
    state = {
        "state": "RUNNING",
        "finished_new_runs": 0,
        "current_index": 0,
        "updated_at": "2026-10-27T14:00:00+00:00",
        "episodes": plan["episodes"],
    }
    state["episodes"][0].update(state="RUNNING", next_check_at="2026-10-27T14:10:00+00:00")
    queue.progress(args.directory, plan, state)
    text = (args.directory / "progress.md").read_text()
    assert "State: RUNNING" in text and "14:10:00" in text
    state.update(state="BETWEEN_RUNS", next_start_not_before="2026-10-27T14:12:00+00:00")
    state["episodes"][0].update(
        state="FINISHED", execution_status="FAILED", evaluation_status="FAILED"
    )
    queue.progress(args.directory, plan, state)
    text = (args.directory / "progress.md").read_text()
    assert "State: BETWEEN_RUNS" in text and "14:12:00" in text
    assert "FINISHED | FAILED | FAILED" in text


async def test_timing_baselines_are_absent_from_fresh_results_and_tokens(tmp_path):
    args = timing_arguments(tmp_path)
    plan = queue.prepare(args)
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    state = {"state": "STARTING", "finished_new_runs": 0, "episodes": plan["episodes"]}
    try:
        # No Q01 database rows exist: they must not be looked up or counted.
        await queue.collection_report(store, args.directory, plan, state)
        collection = queue.read(args.directory / "collection.json")
        assert len(collection["attempts"]) == 8
        assert all(item["task_id"] != "input_q01" for item in collection["attempts"])
        assert all(v["model_calls"] == 0 for v in collection["tokens_by_mode"].values())
        assert "All result attempts are fresh" in (args.directory / "progress.md").read_text()
    finally:
        await store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("poll_seconds", 0),
        ("poll_seconds", float("nan")),
        ("margin_seconds", -1),
        ("startup_delay_seconds", float("inf")),
        ("max_model_calls", 255),
        ("task", ["sales_total", "sales_total"]),
        ("task", ["input_q01"]),
        ("baseline", []),
    ],
)
def test_prepare_rejects_bad_controls_before_creating_output(tmp_path, field, value):
    args = arguments(tmp_path)
    setattr(args, field, value)
    with pytest.raises(ValueError):
        queue.prepare(args)
    assert not args.directory.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "RUNNING"),
        ("mode", "P1"),
        ("run_id", "different"),
        ("finished_at", "2026-10-26T13:00:00+00:00"),
    ],
)
def test_baseline_rejects_wrong_or_unfinished_attempt(tmp_path, field, value):
    args = arguments(tmp_path)
    path = Path(args.baseline[0].split("=", 1)[1])
    status = queue.read(path)
    status[field] = value
    queue.save(path, status)
    with pytest.raises(ValueError):
        queue.baseline("D1", path, 120)


@pytest.mark.parametrize("change", ["helper", "baseline", "configuration"])
def test_verify_refuses_changed_evidence_or_configuration(tmp_path, change):
    args = arguments(tmp_path)
    plan = queue.prepare(args)
    if change == "helper":
        plan["helper_sha256"] = "changed"
    elif change == "baseline":
        Path(plan["reused_q01"][0]["status_path"]).write_text("{}")
    else:
        args.config.write_text(
            args.config.read_text().replace('"90"', '"91"').replace(": 90", ": 91")
        )
    with pytest.raises(ValueError):
        queue.verify(plan)


async def test_watch_checks_process_and_file_and_keeps_waiting(tmp_path):
    directory = tmp_path / "batch"
    directory.mkdir()
    queue.save(directory / "manifest.json", {"status": "COMPLETED"})
    process = SimpleNamespace(returncode=None)
    waits, checks = [], []

    async def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            process.returncode = 1

    async def update():
        checks.append(True)

    _, manifest = await queue.watch(process, tmp_path, 642, 60, update, sleep=sleep)
    assert waits == [642, 60]
    assert len(checks) == 2
    assert manifest["status"] == "COMPLETED"  # Process exit one is not a retry request.


async def test_watch_rejects_exit_without_manifest(tmp_path):
    async def noop(*args):
        pass

    with pytest.raises(RuntimeError):
        await queue.watch(SimpleNamespace(returncode=0), tmp_path, 0, 60, noop, sleep=noop)


async def test_watch_preserves_unfinished_manifest_for_run_accounting(tmp_path):
    (tmp_path / "batch").mkdir()
    queue.save(tmp_path / "batch/manifest.json", {"status": "RUNNING"})

    async def noop(*args):
        pass

    _, manifest = await queue.watch(
        SimpleNamespace(returncode=1), tmp_path, 0, 60, noop, sleep=noop
    )
    # Controller must save the run ID before reporting this failure.
    assert manifest["status"] == "RUNNING"


async def test_watch_reads_real_exited_child_manifest_without_treating_exit_as_pass(tmp_path):
    child = tmp_path / "fixed_child.py"
    child.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "root = Path(sys.argv[1]) / 'batch'\nroot.mkdir()\n"
        "(root / 'manifest.json').write_text(json.dumps({'status': 'STOPPED'}))\n"
        "raise SystemExit(1)\n"
    )
    process = await asyncio.create_subprocess_exec(sys.executable, str(child), str(tmp_path))
    waiter = asyncio.create_task(process.wait())

    async def update():
        pass

    _, manifest = await queue.watch(process, tmp_path, 0.05, 0.01, update)
    await waiter
    assert process.returncode == 1
    assert manifest["status"] == "STOPPED"


def test_global_lock_prevents_two_queues(tmp_path):
    with queue.queue_lock(tmp_path / "queue.lock"):
        with pytest.raises(OSError):
            with queue.queue_lock(tmp_path / "queue.lock"):
                pytest.fail("Second lock must not be acquired.")


@pytest.mark.parametrize("unfinished_manifest", [False, True])
@pytest.mark.parametrize("timing_only", [False, True])
async def test_eight_run_queue_keeps_failures_and_unknown_tokens_without_retries(
    tmp_path, monkeypatch, unfinished_manifest, timing_only
):
    args = timing_arguments(tmp_path) if timing_only else arguments(tmp_path)
    queue.prepare(args)
    store = Store("sqlite://", allow_sqlite_for_tests=True)
    await store.initialize()
    for mode in queue.MODES:
        await store.create_run({"mode": mode}, run_id=mode)
        await store.transition(mode, "FAILED")
    monkeypatch.setattr(queue, "ROOT", tmp_path)
    original_verify = queue.verify
    monkeypatch.setattr(queue, "ROOT", ROOT)
    original_verify(queue.read(args.directory / "plan.json"))
    monkeypatch.setattr(queue, "verify", lambda plan: load_settings(args.config))
    monkeypatch.setattr(queue, "ROOT", tmp_path)
    monkeypatch.setattr(queue, "local_environment", lambda root: ("not-a-real-url", root))
    monkeypatch.setattr(queue, "Store", lambda url: store)
    waits, launched, active = [], [], []

    async def sleep(seconds):
        waits.append(seconds)

    async def preflight(*args, **kwargs):
        assert not active, "A new evaluator must never overlap its predecessor."

    async def spawn(*argv, **kwargs):
        assert not active
        active.append(True)
        mode, task = argv[argv.index("--modes") + 1], argv[argv.index("--task") + 1]
        output = Path(argv[argv.index("--output") + 1])
        run_id = await store.create_run({"mode": mode})
        await store.transition(run_id, "FAILED")
        await store.put(
            run_id,
            "model_call",
            {
                "role": "initial_planner",
                "stage": "main_task",
                "status": "FAILED",
                "error": "Fixed HTTP 429 test failure",  # Retained and not retried.
                "result": {"usage": None},
            },
        )
        manifest = {
            **{
                key: queue.read(args.directory / "plan.json")[key]
                for key in (
                    "source_sha256",
                    "configuration_sha256",
                    "suite_sha256",
                    "grader_sha256",
                )
            },
            "status": "RUNNING" if unfinished_manifest and len(launched) == 5 else "COMPLETED",
            "batch_id": f"batch_{len(launched)}",
            "episodes": [{"mode": mode, "task_id": task, "run_id": run_id, "status": "FAILED"}],
        }
        (output / "batch").mkdir()
        queue.save(output / "batch/manifest.json", manifest)
        launched.append((task, mode))
        process = SimpleNamespace(returncode=0, pid=100 + len(launched))

        async def wait():
            active.clear()
            return process.returncode

        process.wait = wait
        return process

    original_sleep = asyncio.sleep

    async def yielding_sleep(seconds):
        await sleep(seconds)
        await original_sleep(0)

    monkeypatch.setattr(queue.asyncio, "sleep", yielding_sleep)
    monkeypatch.setattr(queue, "preflight", preflight)
    monkeypatch.setattr(queue.asyncio, "create_subprocess_exec", spawn)
    # watch's default captures the real sleep; explicitly inject the virtual clock.
    original_watch = queue.watch

    async def watch(*values):
        return await original_watch(*values, sleep=yielding_sleep)

    monkeypatch.setattr(queue, "watch", watch)
    state = await queue.run_queue(args.directory)
    assert state["state"] == "FINISHED"
    assert state["finished_new_runs"] == 8
    assert len(launched) == len(set(launched)) == 8
    assert state["new_model_calls"] == 8
    assert waits.count(90) == 7
    assert waits.count(642) == 8
    unresolved = [row for row in state["episodes"] if row["state"] == "CHECK_ERROR"]
    assert len(unresolved) == int(unfinished_manifest)
    if unfinished_manifest:
        assert unresolved[0]["run_id"]
        assert unresolved[0]["model_calls"] == 1
        assert unresolved[0]["evaluation_status"] == "UNRESOLVED_SAVE_ERROR"
    summary = queue.read(args.directory / "collection.json")
    assert len(summary["attempts"]) == (8 if timing_only else 12)
    assert state["reused_q01_count"] == (0 if timing_only else 4)
    assert all(value["tokens"] is None for value in summary["tokens_by_mode"].values())
    # Reopen the test store after the helper disposed its engine only to check claim refusal.
    with pytest.raises(ValueError, match="prepared queue"):
        await queue.run_queue(args.directory)
