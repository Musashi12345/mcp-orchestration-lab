"""Independent reference rules for the user's approved Input questions."""

from collections import defaultdict
from decimal import Decimal

from .answers import read, total

ORDER_COLUMNS = [
    "order_id",
    "order_date",
    "customer_id",
    "product_id",
    "region",
    "status",
    "amount_inr",
]


def grouped(rows, key, amount, output, *, count=False):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return [
        {
            key: group,
            output: total(values, amount),
            **({"order_count": len(values)} if count else {}),
        }
        for group, values in sorted(groups.items())
    ]


def cleaned_orders(path):
    """Approved normalization, then missing-row removal, then deduplication."""
    rows, changes, removed, seen = [], [], {}, set()
    regions = {value.lower(): value for value in ("North", "South", "East", "West")}
    statuses = {value: value for value in ("completed", "pending", "cancelled")}
    for source_row, original in enumerate(read(path), 2):
        row = dict(original)

        def change(column, new, row=row, source_row=source_row):
            old = row[column]
            if old != new:
                changes.append(
                    {
                        "source_row": str(source_row),
                        "column": column,
                        "old": old,
                        "new": new,
                        "removed": "false",
                    }
                )
                row[column] = new

        for column in ORDER_COLUMNS:
            change(column, row[column].strip())
        change("region", regions[row["region"].lower()])
        change("status", statuses[row["status"].lower()])
        if row["amount_inr"]:
            text = row["amount_inr"]
            if "," in text:
                # Independent host reference; do not import the agent's number parser.
                whole, dot, fractional = text.partition(".")
                unsigned = whole[1:] if whole.startswith(("+", "-")) else whole
                groups = unsigned.split(",")
                if (
                    not 1 <= len(groups[0]) <= 3
                    or any(not group.isascii() or not group.isdigit() for group in groups)
                    or any(len(group) != 3 for group in groups[1:])
                    or (dot and (not fractional.isascii() or not fractional.isdigit()))
                ):
                    raise ValueError(
                        f"Invalid amount grouping at source row {source_row}: {text!r}."
                    )
                text = text.replace(",", "")
            amount = Decimal(text)
            if not amount.is_finite():
                raise ValueError("Non-finite source amount needs a new approved handling rule.")
            change("amount_inr", format(amount, "f"))
        missing = [column for column in ("customer_id", "amount_inr") if not row[column]]
        key = tuple(row[column] for column in ORDER_COLUMNS)
        if missing:
            removed[str(source_row)] = missing
        elif key in seen:
            removed[str(source_row)] = [""]
        else:
            seen.add(key)
            rows.append(row)
    return rows, changes, removed


def answer_tables(task_id, paths):
    tables = {name: read(path) for name, path in paths.items()}
    if task_id in {"input_q01", "input_q02", "input_q03", "input_q04", "input_q14"}:
        rows = [row for row in tables["orders.csv"] if row["status"] == "completed"]
        if task_id == "input_q01":
            answer = [{"total_amount_inr": total(rows, "amount_inr")}]
        elif task_id in {"input_q02", "input_q14"}:
            answer = grouped(
                rows, "region", "amount_inr", "total_amount_inr", count=task_id == "input_q02"
            )
        else:
            key, name, label = (
                ("customer_id", "customers.csv", "segment")
                if task_id == "input_q03"
                else ("product_id", "products.csv", "category")
            )
            lookup = {row[key]: row[label] for row in tables[name]}
            if len(lookup) != len(tables[name]):
                raise ValueError("Reference join requires unique lookup keys.")
            enriched = [row | {label: lookup.get(row[key], "")} for row in rows]
            answer = grouped(
                enriched, label, "amount_inr", "total_amount_inr", count=task_id == "input_q03"
            )
    elif task_id == "input_q05":
        rows, _, _ = cleaned_orders(paths["orders_messy.csv"])
        answer = grouped(
            [row for row in rows if row["status"] == "completed"],
            "region",
            "amount_inr",
            "total_amount_inr",
        )
    elif task_id == "input_q06":
        answer = [
            {
                "approved_refund_inr": total(
                    [row for row in tables["returns.csv"] if row["status"] == "approved"],
                    "refund_inr",
                )
            }
        ]
    elif task_id == "input_q07":
        answer = grouped(
            [row for row in tables["payments.csv"] if row["status"] == "captured"],
            "order_id",
            "amount_inr",
            "captured_amount_inr",
        )
    elif task_id == "input_q08":
        answer = grouped(tables["monthly_targets.csv"], "region", "target_inr", "target_amount_inr")
    elif task_id == "input_q09":
        answer = [row for row in tables["stock.csv"] if Decimal(row["available_units"]) < 5]
    elif task_id == "input_q11":
        answer = [
            {
                "total_amount_inr": total(
                    [
                        row
                        for row in tables["orders_with_notes.csv"]
                        if row["status"] == "completed"
                    ],
                    "amount_inr",
                )
            }
        ]
    elif task_id == "input_q13":
        return {
            "answer_rows": [
                {
                    "total_amount_inr": total(
                        [r for r in tables["orders.csv"] if r["status"] == "completed"],
                        "amount_inr",
                    )
                }
            ],
            "captured_payments": [
                {
                    "captured_amount_inr": total(
                        [r for r in tables["payments.csv"] if r["status"] == "captured"],
                        "amount_inr",
                    )
                }
            ],
            "approved_refunds": [
                {
                    "approved_refund_inr": total(
                        [r for r in tables["returns.csv"] if r["status"] == "approved"],
                        "refund_inr",
                    )
                }
            ],
        }
    else:
        raise ValueError("No Input table reference for this task.")
    return {"answer_rows": answer}
