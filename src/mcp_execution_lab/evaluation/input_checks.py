"""Checks specific to the approved local Input suite; host-only after execution."""

from .comparison import rows_equal, table_check
from .input_answers import ORDER_COLUMNS, answer_tables, cleaned_orders


def table_checks(outputs, task, paths):
    answers = answer_tables(task.id, paths)
    checks = [table_check(outputs, answers["answer_rows"], task)]
    for name, specification in task.additional_tables.items():
        checks.append(table_check(outputs, answers[name], specification) | {"id": name})
    if task.id != "input_q05":
        return checks
    cleaned, changes, removed = cleaned_orders(paths["orders_messy.csv"])
    clean_spec = task.model_copy(
        update={
            "columns": ORDER_COLUMNS,
            "numeric_columns": ["amount_inr"],
            "tolerance": "0",
        }
    )
    candidates = [
        table["rows"] for table in outputs.csv_tables if set(ORDER_COLUMNS) <= set(table["columns"])
    ]
    checks.append(
        {
            "id": "cleaned_csv",
            "passed": bool(candidates)
            and all(rows_equal(rows, cleaned, clean_spec) for rows in candidates),
        }
    )
    columns = ["source_row", "column", "old", "new", "removed"]
    log_spec = task.model_copy(update={"columns": columns, "numeric_columns": []})
    logs = [
        rows
        for rows in outputs.tables
        if rows and all(isinstance(row, dict) and set(columns) <= row.keys() for row in rows)
    ]

    def valid_log(rows):
        edited = [row for row in rows if str(row["removed"]) == "false"]
        deleted = [row for row in rows if str(row["removed"]) == "true"]
        if len(edited) + len(deleted) != len(rows) or not rows_equal(edited, changes, log_spec):
            return False
        if len(deleted) != len(removed) or {str(row["source_row"]) for row in deleted} != set(
            removed
        ):
            return False
        return all(
            row["column"] in removed[str(row["source_row"])] and row["old"] == row["new"] == ""
            for row in deleted
        )

    checks.append(
        {"id": "change_log", "passed": bool(logs) and all(valid_log(rows) for rows in logs)}
    )
    return checks
