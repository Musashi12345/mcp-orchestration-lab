from collections import Counter
from decimal import Decimal, InvalidOperation

from ..common.models import Fact, NeedsInput
from .models import ColumnProfile, Details, FileProfile


def inspect_tables(tables, recipe):
    known = {column for table in tables for column in table.columns}
    requested = set(recipe.columns) | set(recipe.key_columns) | set(recipe.column_meanings)
    if not requested <= known:
        raise NeedsInput(f"Unknown columns: {sorted(requested - known)}")
    if recipe.question:
        raise NeedsInput(recipe.question)
    profiles, facts, keys = [], [], []
    for index, table in enumerate(tables):
        profiles_for_file = []
        facts.append(
            Fact(
                id=f"file_{index}_rows",
                label="Row count",
                value=len(table.rows),
                sources=[table.ref.id],
            )
        )
        for column in table.columns:
            if recipe.columns and column not in recipe.columns:
                continue
            values = [row[column] for row in table.rows]
            present = [value for value in values if value.strip()]
            counts, numbers = Counter(), []
            for value in present:
                try:
                    number = Decimal(value)
                    if not number.is_finite():
                        raise InvalidOperation
                    counts["integer" if number == number.to_integral() else "number"] += 1
                    numbers.append(number)
                except InvalidOperation:
                    counts["text"] += 1
            profiles_for_file.append(
                ColumnProfile(
                    name=column,
                    missing=len(values) - len(present),
                    distinct=len(set(present)),
                    observed_types=dict(counts),
                    minimum=str(min(numbers)) if numbers else None,
                    maximum=str(max(numbers)) if numbers else None,
                )
            )
            facts.append(
                Fact(
                    id=f"file_{index}_missing_{len(profiles_for_file)}",
                    label=f"Missing values in {column}",
                    value=len(values) - len(present),
                    sources=[table.ref.id],
                )
            )
            if column in recipe.key_columns:
                keys.append(
                    {
                        "dataset_id": table.ref.id,
                        "column": column,
                        "unique": len(set(present)) == len(values),
                        "missing": len(values) - len(present),
                    }
                )
        duplicates = (
            len(table.rows)
            - len({tuple(row[column] for column in table.columns) for row in table.rows})
            if recipe.check_duplicates
            else None
        )
        profiles.append(
            FileProfile(
                dataset_id=table.ref.id,
                row_count=len(table.rows),
                columns=profiles_for_file,
                duplicate_rows=duplicates,
            )
        )
        if duplicates is not None:
            facts.append(
                Fact(
                    id=f"file_{index}_duplicates",
                    label="Exact duplicate rows",
                    value=duplicates,
                    sources=[table.ref.id],
                )
            )
    return Details(
        profiles=profiles, key_checks=keys, possible_meanings=recipe.column_meanings
    ), facts
