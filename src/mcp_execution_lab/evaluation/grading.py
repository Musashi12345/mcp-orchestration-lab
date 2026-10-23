"""Independent post-run grading with immutable, same-run evaluation records."""

import hashlib
import math
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..orchestration.models import FileRef, OrchestrationError, fingerprint
from ..orchestration.provenance import source_identity
from ..orchestration.storage import identity
from .answers import expected, forecast_rows
from .evidence import collect

TERMINAL = {
    "COMPLETED",
    "FAILED",
    "INTERRUPTED",
    "UNCERTAIN",
    "PLANNING_FAILED",
    "NEEDS_CLARIFICATION",
}


def rows_equal(actual, wanted, task):
    if len(actual) != len(wanted) or not all(isinstance(row, dict) for row in actual):
        return False
    remaining = list(actual)

    def equal(a, b):
        for column in task.columns:
            if column not in a or column not in b:
                return False
            left, right = str(a[column]), str(b[column])
            if column in task.numeric_columns and left and right:
                try:
                    x, y = Decimal(left), Decimal(right)
                    if (
                        not x.is_finite()
                        or not y.is_finite()
                        or abs(x - y) > Decimal(task.tolerance)
                    ):
                        return False
                except InvalidOperation:
                    return False
            elif left != right:
                return False
        return True

    for row in wanted:
        index = next((i for i, value in enumerate(remaining) if equal(value, row)), None)
        if index is None:
            return False
        remaining.pop(index)
    return True


def table_check(outputs, wanted, task):
    candidates = [
        rows
        for rows in outputs.tables
        if rows and all(isinstance(row, dict) and set(task.columns) <= row.keys() for row in rows)
    ]
    return {
        "id": "answer_rows",
        "passed": bool(candidates) and all(rows_equal(rows, wanted, task) for rows in candidates),
        "message": "Returned answer tables must match the requested rows and values. "
        "Row order is ignored.",
        "candidate_tables": len(candidates),
        "expected_rows": wanted,
    }


def measurements(run, records, events):
    calls = [row for row in records if row["kind"] == "model_call"]
    attempts = [row for row in records if row["kind"] == "tool_attempt"]
    known, complete = 0, True
    for row in calls:
        usage = row["payload"].get("result", {}).get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")
        ):
            complete = False
        else:
            known += usage["input_tokens"] + usage["output_tokens"]
    states = [event for event in events if event["kind"] == "run_state"]
    end = next(
        (
            event["created_at"]
            for event in reversed(states)
            if event["payload"]["state"] in TERMINAL
        ),
        None,
    )
    ready = next(
        (
            event["created_at"]
            for event in states
            if event["payload"]["state"] == "READY_FOR_EXECUTION"
        ),
        None,
    )
    start = next(
        (event["created_at"] for event in states if event["payload"]["state"] == "EXECUTING"), None
    )

    def seconds(a, b):
        return (
            max(0, (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
            if a and b
            else None
        )

    return {
        "model_calls": len(calls),
        "model_calls_by_role": dict(
            Counter(row["payload"].get("role", "planner") for row in calls)
        ),
        "tokens": known if complete else None,
        "known_tokens": known,
        "usage_complete": complete,
        "tool_attempts": len(attempts),
        "tool_attempt_states": dict(Counter(row["payload"].get("status") for row in attempts)),
        "review_decisions": dict(
            Counter(
                row["payload"].get("decision", {}).get("decision", row["payload"].get("status"))
                for row in records
                if row["kind"] == "review"
            )
        ),
        "planning_seconds": seconds(run["created_at"], ready or end),
        "execution_seconds": seconds(start, end),
        "total_seconds": seconds(run["created_at"], end),
        "usd_cost": None,
    }


def grade_identity():
    return fingerprint(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        }
    )


def score_close(actual, wanted):
    try:
        number = Decimal(str(actual))
        return (
            number.is_finite()
            and number >= 0
            and abs(number - Decimal(str(wanted))) <= Decimal("0.000001")
        )
    except InvalidOperation:
        return False


async def evaluate(store, files, suite, task_id, run_id):
    task = suite.task(task_id)
    paths = {name: suite.path(name) for name in task.files}
    run = await store.run(run_id)
    if run["status"] not in TERMINAL:
        raise OrchestrationError(
            "EVAL_RUN_ACTIVE", "Grade only after planning or execution has ended."
        )
    if run["payload"]["request"] != task.query:
        raise OrchestrationError(
            "EVAL_TASK_MISMATCH", "This run did not receive the exact public task."
        )
    records = await store.list_records(run_id)
    datasets = [row for row in records if row["kind"] == "dataset"]
    originals = []
    for name in task.files:
        rows = [row for row in datasets if row["payload"]["dataset"]["filename"] == name]
        if (
            len(rows) != 1
            or rows[0]["payload"]["dataset"]["ref"]["sha256"]
            != suite.manifest["files"][name]["sha256"]
        ):
            raise OrchestrationError(
                "EVAL_INPUT_MISMATCH", "Run inputs do not match this frozen task."
            )
        originals.append(rows[0])
    evaluation_id = identity("evaluation")
    await store.event(
        run_id,
        "evaluation_started",
        {"evaluation_id": evaluation_id, "task_id": task.id, "suite_sha256": suite.digest},
    )
    checks, outputs = [], None
    results = [row for row in records if row["kind"] == "execution_result"]
    final = results[-1] if results else None
    try:
        for row in originals:
            await files.checked_path(
                run_id, FileRef.model_validate(row["payload"]["dataset"]["ref"])
            )
        checks.append({"id": "input_integrity", "passed": True})
        if task.kind == "clarification":
            questions = [
                q
                for row in records
                if row["kind"] == "main_task"
                for q in row["payload"].get("clarification_questions", [])
            ]
            questions += [
                q
                for row in records
                if row["kind"] == "worker_call"
                for q in row["payload"].get("result", {}).get("questions", [])
            ]
            checks.append(
                {"id": "asked_for_information", "passed": bool(questions), "questions": questions}
            )
        else:
            checks.append(
                {
                    "id": "execution_completed",
                    "passed": run["status"] == "COMPLETED" and final is not None,
                }
            )
            roots = list(final["payload"].get("outputs", {}).values()) if final else []
            outputs = await collect(
                run_id, roots, files, input_ids={row["id"] for row in originals}
            )
            if task.kind == "forecast":
                wanted, train, test = forecast_rows(paths["daily_sales.csv"])
                checks.append(table_check(outputs, wanted, task))
                splits = [
                    doc
                    for doc in outputs.documents
                    if isinstance(doc, dict)
                    and "training_source_rows" in doc
                    and "test_source_rows" in doc
                ]
                checks.append(
                    {
                        "id": "held_back_split",
                        "passed": bool(splits)
                        and all(
                            doc["training_source_rows"] == train and doc["test_source_rows"] == test
                            for doc in splits
                        ),
                    }
                )
                error = sum(
                    abs(Decimal(row["actual"]) - Decimal(row["predicted"]))
                    for row in wanted
                    if row["split"] == "test"
                ) / len(test)
                rmse = math.sqrt(
                    sum(
                        (float(row["actual"]) - float(row["predicted"])) ** 2
                        for row in wanted
                        if row["split"] == "test"
                    )
                    / len(test)
                )
                metrics = [
                    doc["details"]["metrics"]
                    for doc in outputs.documents
                    if isinstance(doc, dict)
                    and isinstance(doc.get("details"), dict)
                    and "metrics" in doc["details"]
                ]
                checks.append(
                    {
                        "id": "forecast_error",
                        "passed": bool(metrics)
                        and all(
                            score_close(m.get("mean_absolute_error"), error)
                            and score_close(m.get("root_mean_squared_error"), rmse)
                            for m in metrics
                        ),
                    }
                )
                baselines = [
                    doc["details"]["baseline_metrics"]
                    for doc in outputs.documents
                    if isinstance(doc, dict)
                    and isinstance(doc.get("details"), dict)
                    and "baseline_metrics" in doc["details"]
                ]
                checks.append(
                    {
                        "id": "reference_error",
                        "passed": bool(baselines)
                        and all(
                            score_close(m.get("mean_absolute_error"), error)
                            and score_close(m.get("root_mean_squared_error"), rmse)
                            for m in baselines
                        ),
                    }
                )
            else:
                checks.append(table_check(outputs, expected(task, paths), task))
            if task.require_chart:
                checks.append({"id": "chart_present", "passed": bool(outputs.pngs)})
            if task.require_report:
                checks.append(
                    {
                        "id": "report_present",
                        "passed": any(text.strip() for text in outputs.reports),
                    }
                )
            if task.require_change_log:
                columns = ["source_row", "column", "old", "new", "removed"]
                log_task = task.model_copy(update={"columns": columns, "numeric_columns": []})
                changes = [
                    {
                        "source_row": "2",
                        "column": "region",
                        "old": " East ",
                        "new": "East",
                        "removed": "false",
                    },
                    {
                        "source_row": "3",
                        "column": "region",
                        "old": "west",
                        "new": "West",
                        "removed": "false",
                    },
                    {
                        "source_row": "4",
                        "column": "region",
                        "old": "NORTH",
                        "new": "North",
                        "removed": "false",
                    },
                    {"source_row": "10", "column": "", "old": "", "new": "", "removed": "true"},
                    {"source_row": "11", "column": "", "old": "", "new": "", "removed": "true"},
                ]
                checks.append(table_check(outputs, changes, log_task) | {"id": "change_log"})
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        checks.append(
            {
                "id": "output_integrity",
                "passed": False,
                "code": getattr(exc, "code", type(exc).__name__),
                "message": str(exc)[:1000],
            }
        )
    passed = all(check["passed"] for check in checks)
    pending = passed and bool(task.human_checks)
    result = {
        "evaluation_id": evaluation_id,
        "run_id": run_id,
        "task_id": task.id,
        "suite_version": suite.version,
        "suite_sha256": suite.digest,
        "grader_sha256": grade_identity(),
        "grader_source": source_identity(),
        "run_source_sha256": run["payload"].get("source_sha256"),
        "fixture_hashes": {name: suite.manifest["files"][name]["sha256"] for name in task.files},
        "execution_status": run["status"],
        "mode": run["payload"]["mode"],
        "is_model": run["payload"]["is_model"],
        "exploratory": True,
        "status": "REVIEW_NEEDED" if pending else ("PASSED" if passed else "FAILED"),
        "task_success": None if pending else passed,
        "checks": checks,
        "human_checks": task.human_checks,
        "measurements": measurements(run, records, await store.history(run_id)),
        "output_references": outputs.references if outputs else [],
    }
    await store.put(
        run_id,
        "evaluation_result",
        result,
        parents=[("execution", final["id"])]
        if final
        else [("input", row["id"]) for row in originals],
        record_id=evaluation_id,
    )
    return result


async def review(store, run_id, evaluation_id, *, passed, reviewer, note):
    row = await store.get(run_id, evaluation_id)
    value = row["payload"]
    if row["kind"] != "evaluation_result" or not value.get("human_checks"):
        raise ValueError("Choose an evaluation with human review criteria.")
    if not reviewer.strip() or not note.strip():
        raise ValueError("A reviewer name and explanation are required.")
    if not all(check["passed"] for check in value["checks"]):
        raise ValueError("Human review cannot override a failed automatic check.")
    updated = value | {
        "evaluation_id": identity("evaluation"),
        "status": "PASSED" if passed else "FAILED",
        "task_success": passed,
        "human_review": {"reviewer": reviewer, "note": note, "passed": passed},
        "previous_evaluation_id": evaluation_id,
    }
    await store.put(
        run_id,
        "evaluation_result",
        updated,
        parents=[("previous_evaluation", evaluation_id)],
        record_id=updated["evaluation_id"],
    )
    return updated
