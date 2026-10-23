from datetime import datetime

from ..common.models import NeedsInput, Unsupported
from ..common.operations import number, require_columns
from .models import Details


def clean(table, recipe, rules):
    if recipe.question:
        raise NeedsInput(recipe.question)
    rows = [(index + 2, dict(row)) for index, row in enumerate(table.rows)]
    changes = []
    for operation in recipe.operations:
        action, column = operation.action, operation.column
        if action != "remove_exact_duplicates":
            require_columns(table, [column])
        allowed = {
            "trim": column in rules.trim_columns,
            "fill": column in rules.fill_values,
            "replace": column in rules.replacements,
            "parse_date": column in rules.date_formats,
            "convert_number": column in rules.number_columns,
            "remove_exact_duplicates": rules.remove_exact_duplicates,
            "drop_missing": column in rules.drop_missing_columns,
        }
        if not allowed[action]:
            raise NeedsInput(f"Cleaning rule does not allow {action} on {column!r}.")
        retained, seen = [], set()
        for source_row, row in rows:
            if len(changes) >= 100000:
                raise Unsupported("The complete change record exceeds the supported allowance.")
            old = row.get(column, "")
            new, remove = old, False
            if action == "remove_exact_duplicates":
                key = tuple(row[name] for name in table.columns)
                remove = key in seen
                seen.add(key)
            elif action == "drop_missing":
                remove = not old.strip()
            elif action == "trim":
                new = old.strip()
            elif action == "fill" and not old.strip():
                new = rules.fill_values[column]
            elif action == "replace":
                new = rules.replacements[column].get(old, old)
            elif action == "parse_date" and old.strip():
                try:
                    new = datetime.strptime(old, rules.date_formats[column]).isoformat()
                except ValueError as exc:
                    raise NeedsInput(
                        f"Date in {column!r} does not match the permitted format."
                    ) from exc
            elif action == "convert_number" and old.strip():
                new = format(number(old), "f")
            if remove or new != old:
                changes.append(
                    {
                        "source_row": source_row,
                        "column": column,
                        "old": old,
                        "new": "" if remove else new,
                        "operation": action,
                        "reason": operation.reason,
                        "removed": str(remove).lower(),
                    }
                )
            if not remove:
                if action != "remove_exact_duplicates":
                    row[column] = new
                retained.append((source_row, row))
        rows = retained
    details = Details(
        before_rows=len(table.rows),
        after_rows=len(rows),
        changed_cells=len(
            {
                (change["source_row"], change["column"])
                for change in changes
                if change["removed"] == "false"
            }
        ),
        removed_rows=len(table.rows) - len(rows),
        recipe=recipe.operations,
    )
    return [row for _, row in rows], changes, [index for index, _ in rows], details
