"""Independent comparison of returned tables against host-only reference rows."""

from decimal import Decimal, InvalidOperation


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
                    tolerance = Decimal(task.column_tolerances.get(column, task.tolerance))
                    if not x.is_finite() or not y.is_finite() or abs(x - y) > tolerance:
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
