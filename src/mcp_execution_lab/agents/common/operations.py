"""Checked table helpers, deterministic numbers, and fact-based text rendering."""

import csv
import io
import math
import re
from decimal import Decimal, InvalidOperation

from .models import NeedsInput, Unsupported


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise NeedsInput(f"Expected a number; received {str(value)[:60]!r}.") from exc
    if not result.is_finite():
        raise NeedsInput("Non-finite numbers need an explicit handling rule.")
    return result


def numeric_value(value):
    result = number(value)
    converted = int(result) if result == result.to_integral() else float(result)
    if isinstance(converted, float) and not math.isfinite(converted):
        raise Unsupported("Calculation exceeds the supported numeric range.")
    return converted


def require_columns(table, columns):
    missing = set(columns) - set(table.columns)
    if missing:
        raise NeedsInput(f"Unknown columns: {sorted(missing)}")


def csv_bytes(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def render_text(text, facts):
    values = {fact.id: fact.value for fact in facts}
    markers = re.findall(r"\{\{fact:([a-zA-Z0-9_]+)\}\}", text)
    if any(key not in values for key in markers):
        raise NeedsInput("The explanation references an unknown fact.")
    plain = re.sub(r"\{\{fact:[a-zA-Z0-9_]+\}\}", "", text)
    if re.search(r"(?<!\w)[+-]?\d+(?:\.\d+)?", plain):
        raise NeedsInput("Numeric claims must reference checked facts.")
    for key in markers:
        text = text.replace("{{fact:" + key + "}}", str(values[key]))
    return text


def finite(value):
    if not math.isfinite(float(value)):
        raise Unsupported("Calculation produced a non-finite result.")
    return float(value)
