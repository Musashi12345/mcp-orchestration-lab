"""Small paired development batches. No shared model-response cache or auto-resume."""

import asyncio
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from ..orchestration.files import Files
from ..orchestration.models import fingerprint
from ..orchestration.provenance import source_identity
from ..orchestration.service import Application
from ..orchestration.storage import identity, now
from .grading import evaluate, grade_identity, measurements


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class EpisodeStore:
    def __init__(self, store, episode, callback):
        self.store, self.episode, self.callback = store, episode, callback
        self.run_id = None

    def __getattr__(self, name):
        return getattr(self.store, name)

    async def create_run(self, payload, **kwargs):
        self.run_id = await self.store.create_run(payload, **kwargs)
        await self.store.put(self.run_id, "evaluation_episode", self.episode)
        self.callback(self.run_id)
        return self.run_id


async def run_batch(
    store,
    data_root,
    settings,
    suite,
    output_root,
    *,
    task_ids=None,
    modes=("D1", "D2"),
    repeats=1,
    seed=0,
    max_model_calls,
    client=None,
):
    if repeats < 1 or repeats > 100 or max_model_calls < 1:
        raise ValueError("Provide positive repeats and a total model-request ceiling.")
    if not modes or len(set(modes)) != len(modes) or not set(modes) <= {"D1", "D2", "P1", "P2"}:
        raise ValueError("Choose distinct supported modes: D1, D2, P1, P2.")
    if {"D2", "P2"}.intersection(modes) and len(settings.task_rules.reviews) != 2:
        raise ValueError("D2/P2 evaluation needs two configured task review opportunities.")
    chosen = [suite.task(key) for key in task_ids] if task_ids else suite.tasks
    if not chosen or len({t.id for t in chosen}) != len(chosen):
        raise ValueError("Choose distinct task IDs.")
    rng = random.Random(seed)
    blocks = [(task, repeat) for task in chosen for repeat in range(1, repeats + 1)]
    rng.shuffle(blocks)
    schedule = []
    for task, repeat in blocks:
        ordered = list(modes)
        rng.shuffle(ordered)
        schedule.extend(
            {"task_id": task.id, "repeat": repeat, "mode": mode, "status": "QUEUED"}
            for mode in ordered
        )
    directory = Path(output_root).resolve() / identity("eval_batch")
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "batch_id": directory.name,
        "created_at": now(),
        "status": "RUNNING",
        "study_stage": "development",
        "exploratory": True,
        "suite_version": suite.version,
        "suite_sha256": suite.digest,
        "grader_sha256": grade_identity(),
        **source_identity(),
        "configuration_sha256": fingerprint(settings.model_dump(mode="json")),
        "settings": settings.model_dump(mode="json"),
        "seed": seed,
        "max_model_calls": max_model_calls,
        "used_model_calls": 0,
        "episodes": schedule,
    }
    path = directory / "manifest.json"
    save(path, manifest)

    def check_source():
        current = source_identity()
        if (
            any(current[key] != manifest[key] for key in ("source_sha256", "lock_sha256"))
            or grade_identity() != manifest["grader_sha256"]
        ):
            raise ValueError("Source changed during the batch; start a new batch.")

    try:
        for offset in range(0, len(schedule), len(modes)):
            check_source()
            # Reserve room for an entire matched block without reducing later runs' limits.
            if max_model_calls - manifest[
                "used_model_calls"
            ] < settings.limits.max_model_calls * len(modes):
                manifest["status"] = "BUDGET_STOPPED"
                break
            for episode in schedule[offset : offset + len(modes)]:
                check_source()
                task = suite.task(episode["task_id"])
                sources = [suite.path(name) for name in task.files]
                episode["status"] = "RUNNING"
                save(path, manifest)

                def created(run_id, current=episode):
                    current["run_id"] = run_id
                    save(path, manifest)

                tracked = EpisodeStore(
                    store,
                    {
                        "batch_id": directory.name,
                        "task_id": task.id,
                        "repeat": episode["repeat"],
                        "suite_sha256": suite.digest,
                        "condition": "original_csvs",
                        "seed": seed,
                    },
                    created,
                )
                try:
                    app = Application(tracked, data_root, settings, client=client)
                    handoff = await app.plan(task.query, sources, mode=episode["mode"])
                    await app.execute(handoff.run_id)
                except asyncio.CancelledError:
                    episode["status"] = "INTERRUPTED"
                    raise
                except Exception as exc:
                    # The detailed error already belongs to the run's records.
                    episode["error_type"] = type(exc).__name__
                finally:
                    if tracked.run_id:
                        records = await store.list_records(tracked.run_id)
                        usage = sum(row["kind"] == "model_call" for row in records)
                        manifest["used_model_calls"] += usage
                        episode["model_calls"] = usage
                        save(path, manifest)
                if tracked.run_id is None:
                    raise RuntimeError("No saved run was created; batch stopped.")
                check_source()
                try:
                    result = await evaluate(
                        store,
                        Files(data_root, store, settings.limits),
                        suite,
                        task.id,
                        tracked.run_id,
                    )
                    episode["status"] = result["status"]
                    episode["evaluation_id"] = result["evaluation_id"]
                except Exception as exc:
                    episode["status"] = "EVALUATION_ERROR"
                    episode["evaluation_error_type"] = type(exc).__name__
                    await store.event(
                        tracked.run_id,
                        "evaluation_error",
                        {"task_id": task.id, "error_type": type(exc).__name__},
                    )
                save(path, manifest)
        else:
            manifest["status"] = "COMPLETED"
    except BaseException as exc:
        manifest["status"] = "INTERRUPTED" if isinstance(exc, asyncio.CancelledError) else "STOPPED"
        manifest["error_type"] = type(exc).__name__
        raise
    finally:
        manifest["finished_at"] = now()
        save(path, manifest)
    await report_batch(store, directory)
    return {"directory": str(directory), "manifest": manifest}


async def report_batch(store, directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for episode in manifest["episodes"]:
        row = {k: episode.get(k) for k in ("task_id", "repeat", "mode", "run_id", "status")}
        row["task_success"] = None
        if episode.get("run_id"):
            run = await store.run(episode["run_id"])
            records = await store.list_records(episode["run_id"])
            evaluations = [
                r
                for r in records
                if r["kind"] == "evaluation_result"
                and r["payload"]["task_id"] == episode["task_id"]
                and r["payload"]["suite_sha256"] == manifest["suite_sha256"]
                and r["payload"]["grader_sha256"] == manifest["grader_sha256"]
            ]
            metrics = measurements(run, records, await store.history(run["id"]))
            row.update(
                {
                    "execution_status": run["status"],
                    "is_model": run["payload"]["is_model"],
                    **metrics,
                }
            )
            if evaluations:
                value = evaluations[-1]["payload"]
                row.update(
                    status=value["status"],
                    task_success=value["task_success"],
                    evaluation_id=value["evaluation_id"],
                )
        rows.append(row)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["mode"]].append(row)
    summary = {
        "batch_id": manifest["batch_id"],
        "exploratory": True,
        "study_stage": "development",
        "modes": {},
        "comparisons": {},
    }
    for mode, values in grouped.items():
        attempted = [r for r in values if r.get("run_id")]
        summary["modes"][mode] = {
            "planned": len(values),
            "attempted": len(attempted),
            "statuses": dict(Counter(r["status"] for r in values)),
            "passed": sum(r["task_success"] is True for r in attempted),
            "failed": sum(r["task_success"] is False for r in attempted),
            "unresolved": sum(r["task_success"] is None for r in attempted),
            "confirmed_pass_fraction_of_attempts": sum(r["task_success"] is True for r in attempted)
            / len(attempted)
            if attempted
            else None,
            "model_calls": sum(r.get("model_calls", 0) for r in attempted),
            "median_total_seconds": median(
                [r["total_seconds"] for r in attempted if r.get("total_seconds") is not None]
            )
            if any(r.get("total_seconds") is not None for r in attempted)
            else None,
        }
    for a, b in (("D1", "D2"), ("P1", "P2"), ("D1", "P1"), ("D2", "P2")):
        pairs = defaultdict(dict)
        for row in rows:
            if row["mode"] in {a, b}:
                pairs[row["task_id"], row["repeat"]][row["mode"]] = row
        complete = [
            p
            for p in pairs.values()
            if a in p and b in p and all(p[m]["task_success"] is not None for m in (a, b))
        ]
        summary["comparisons"][a + "_to_" + b] = {
            "scored_pairs": len(complete),
            "unresolved_or_missing_pairs": len(pairs) - len(complete),
            "second_only_passes": sum(
                p[b]["task_success"] and not p[a]["task_success"] for p in complete
            ),
            "first_only_passes": sum(
                p[a]["task_success"] and not p[b]["task_success"] for p in complete
            ),
        }
    save(directory / "summary.json", summary)
    with (directory / "episodes.csv").open("w", encoding="utf-8", newline="") as stream:
        columns = [
            "task_id",
            "repeat",
            "mode",
            "run_id",
            "status",
            "execution_status",
            "task_success",
            "is_model",
            "model_calls",
            "tool_attempts",
            "tokens",
            "known_tokens",
            "planning_seconds",
            "execution_seconds",
            "total_seconds",
            "usd_cost",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    text = [
        "# Development evaluation",
        "",
        "Fixed-reply runs are exploratory engineering checks. "
        "Live runs are still development work.",
        "",
        "| Mode | Attempted | Passed | Failed | Unresolved | Model calls |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, value in summary["modes"].items():
        text.append(
            f"| {mode} | {value['attempted']} | {value['passed']} | {value['failed']} "
            f"| {value['unresolved']} | {value['model_calls']} |"
        )
    text += [
        "",
        "All attempts stay in the denominator. "
        "Missing reviews and evaluation errors remain unresolved.",
        "",
        "Paired counts exclude unresolved pairs and report their count separately. "
        "These small development examples do not establish a representation winner.",
        "",
        "Chart/report claims require human review. Dollar costs remain unknown. "
        "No injected service-failure recovery score is claimed.",
    ]
    (directory / "report.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return summary
