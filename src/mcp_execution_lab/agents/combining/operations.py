from collections import Counter, defaultdict

from ..common.models import NeedsInput, Unsupported
from ..common.operations import require_columns
from .models import Details


def combine(tables, recipe, rules):
    if recipe.question:
        raise NeedsInput(recipe.question)
    if len(tables) < 2:
        raise NeedsInput("Combining requires at least two supplied files.")
    columns = list(tables[0].columns)
    rows = [dict(row) for row in tables[0].rows]
    mapping = [
        [{"dataset": tables[0].ref.id, "source_row": index + 2}] for index in range(len(rows))
    ]
    checks, column_maps = [], []
    if recipe.operation == "append":
        if any(set(table.columns) != set(columns) for table in tables):
            raise NeedsInput("Appended files must have the same explicitly compatible columns.")
        if sum(len(table.rows) for table in tables) > rules.max_output_rows:
            raise Unsupported("Appended output exceeds its row allowance.")
        for table in tables[1:]:
            rows.extend(dict(row) for row in table.rows)
            mapping.extend(
                [{"dataset": table.ref.id, "source_row": index + 2}]
                for index in range(len(table.rows))
            )
        return columns, rows, mapping, Details(operation="append", output_rows=len(rows))
    if not recipe.keys or len(set(recipe.keys)) != len(recipe.keys):
        raise NeedsInput("A join needs distinct, explicit matching columns.")
    if rules.keys and recipe.keys != rules.keys:
        raise NeedsInput("Proposed matching columns differ from the task rules.")
    if rules.join_type and recipe.join_type != rules.join_type:
        raise NeedsInput("Proposed row retention differs from the task rules.")
    if recipe.relationship != rules.relationship:
        raise NeedsInput("Proposed key multiplicity differs from the task rules.")
    if recipe.relationship == "many_to_many" and not rules.allow_many_to_many:
        raise NeedsInput("Many-to-many matching needs an explicit allowed rule.")
    for table in tables:
        require_columns(table, recipe.keys)

    def key(row):
        values = tuple(row[name] for name in recipe.keys)
        return values if all(value.strip() for value in values) else None

    for index, table in enumerate(tables[1:], 1):
        left_counts = Counter(key(row) for row in rows if key(row) is not None)
        right_counts = Counter(key(row) for row in table.rows if key(row) is not None)
        if recipe.relationship in {"one_to_one", "one_to_many"} and any(
            v > 1 for v in left_counts.values()
        ):
            raise NeedsInput("Left matching keys are repeated under a unique-key rule.")
        if recipe.relationship in {"one_to_one", "many_to_one"} and any(
            v > 1 for v in right_counts.values()
        ):
            raise NeedsInput("Right matching keys are repeated under a unique-key rule.")
        right_groups = defaultdict(list)
        for number, row in enumerate(table.rows):
            if key(row) is not None:
                right_groups[key(row)].append((number, row))
        names = {}
        for column in table.columns:
            if column in recipe.keys:
                continue
            name = column if column not in columns else f"file_{index}_{column}"
            while name in columns or name in names.values():
                name += "_"
            names[column] = name
        output_columns = columns + list(names.values())
        merged, provenance, matched_right = [], [], set()
        left_unmatched = 0

        def emit(row, source, merged=merged, provenance=provenance):
            if len(merged) >= rules.max_output_rows:
                raise Unsupported("Join output exceeds its row allowance.")
            merged.append(row)
            provenance.append(source)

        for left_index, row in enumerate(rows):
            matches = right_groups.get(key(row), []) if key(row) is not None else []
            if not matches:
                left_unmatched += 1
                if recipe.join_type in {"left", "outer"}:
                    emit(row | {name: "" for name in names.values()}, mapping[left_index])
            for right_index, right in matches:
                matched_right.add(right_index)
                emit(
                    row | {name: right[column] for column, name in names.items()},
                    mapping[left_index]
                    + [{"dataset": table.ref.id, "source_row": right_index + 2}],
                )
        if recipe.join_type == "outer":
            for right_index, right in enumerate(table.rows):
                if right_index not in matched_right:
                    out = dict.fromkeys(output_columns, "")
                    out.update({name: right[column] for column, name in names.items()})
                    out.update({column: right[column] for column in recipe.keys})
                    emit(out, [{"dataset": table.ref.id, "source_row": right_index + 2}])
        checks.append(
            {
                "right_dataset": table.ref.id,
                "left_unmatched": left_unmatched,
                "right_unmatched": len(table.rows) - len(matched_right),
                "output_rows": len(merged),
            }
        )
        column_maps.append(names)
        columns, rows, mapping = output_columns, merged, provenance
    return (
        columns,
        rows,
        mapping,
        Details(operation="join", output_rows=len(rows), checks=checks, column_mapping=column_maps),
    )
