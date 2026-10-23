import io
import operator
import statistics
import threading
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from ..common.models import Fact, NeedsInput, Unsupported
from ..common.operations import number, numeric_value, require_columns
from .models import Details, GroupResult

PLOT_LOCK = threading.Lock()


def analyze(table, recipe, definitions):
    if recipe.question:
        raise NeedsInput(recipe.question)
    columns = recipe.group_by + [f.column for f in recipe.filters]
    columns += [m.column for m in recipe.measures if m.operation != "count"]
    columns += recipe.correlation_columns + ([recipe.time_column] if recipe.time_column else [])
    require_columns(table, columns)
    names = [measure.name for measure in recipe.measures]
    if len(set(names)) != len(names):
        raise NeedsInput("Calculation names must be distinct.")
    if set(names) & set(recipe.group_by):
        raise NeedsInput("Calculation names must differ from grouping column names.")
    if recipe.time_column and recipe.time_column not in recipe.group_by:
        raise NeedsInput("Time grouping requires its column in group_by.")
    comparisons = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}

    def keep(row):
        for rule in recipe.filters:
            value = row[rule.column]
            if rule.operation == "missing":
                matched = not value.strip()
            elif rule.operation == "eq":
                matched = value == rule.value
            elif rule.operation == "ne":
                matched = value != rule.value
            elif rule.operation == "in":
                matched = value in rule.values
            else:
                matched = bool(value.strip()) and comparisons[rule.operation](
                    number(value), number(rule.value)
                )
            if not matched:
                return False
        return True

    rows = [row for row in table.rows if keep(row)]
    buckets = defaultdict(list)
    for row in rows:
        values = []
        for column in recipe.group_by:
            value = row[column]
            if column == recipe.time_column:
                if not value.strip():
                    raise NeedsInput("Missing dates need an explicit filtering rule.")
                try:
                    date = (
                        datetime.strptime(value, definitions.date_formats[column])
                        if column in definitions.date_formats
                        else datetime.fromisoformat(value)
                    )
                except ValueError as exc:
                    raise NeedsInput(
                        "Date grouping requires ISO dates or a stated date format."
                    ) from exc
                value = date.strftime(
                    {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}[recipe.period]
                )
            values.append(value)
        buckets[tuple(values)].append(row)
        if len(buckets) > 100:
            raise Unsupported("The calculation exceeds the supported group count.")
    if not recipe.group_by and not rows:
        buckets[()] = []
    groups, facts = (
        [],
        [Fact(id="rows_used", label="Rows included", value=len(rows), sources=[table.ref.id])],
    )
    warnings = []
    for group_index, (key, members) in enumerate(sorted(buckets.items())):
        metrics, valid, missing = {}, {}, {}
        for metric_index, measure in enumerate(recipe.measures):
            present = (
                [number(row[measure.column]) for row in members if row[measure.column].strip()]
                if measure.operation != "count"
                else []
            )
            valid[measure.name] = len(members) if measure.operation == "count" else len(present)
            missing[measure.name] = len(members) - valid[measure.name]
            if measure.operation == "count":
                value = len(members)
            elif not present:
                value = None
            elif measure.operation == "sum":
                value = numeric_value(sum(present, Decimal(0)))
            elif measure.operation == "mean":
                value = numeric_value(sum(present, Decimal(0)) / len(present))
            else:
                value = numeric_value(min(present) if measure.operation == "min" else max(present))
            metrics[measure.name] = value
            facts.append(
                Fact(
                    id=f"group_{group_index}_metric_{metric_index}",
                    label=str(dict(zip(recipe.group_by, key, strict=True))) + " " + measure.name,
                    value=value,
                    unit=definitions.units.get(measure.column, ""),
                    sources=[table.ref.id],
                )
            )
        groups.append(
            GroupResult(
                group=dict(zip(recipe.group_by, key, strict=True)),
                metrics=metrics,
                valid_counts=valid,
                missing_counts=missing,
            )
        )
    details = Details(
        rows_used=len(rows), rows_excluded=len(table.rows) - len(rows), groups=groups, recipe=recipe
    )
    if recipe.comparison:
        compare = recipe.comparison
        if len(recipe.group_by) != 1 or compare.measure not in names:
            raise NeedsInput("A comparison needs one grouping column and a known measure.")
        values = {
            next(iter(group.group.values())): group.metrics[compare.measure] for group in groups
        }
        before, after = values.get(compare.before), values.get(compare.after)
        if before is None or after is None:
            raise NeedsInput("A required comparison group has no measured value.")
        difference = numeric_value(number(after) - number(before))
        percent = numeric_value(number(difference) / number(before) * 100) if before != 0 else None
        if percent is None:
            warnings.append("Percentage change is undefined because the earlier value is zero.")
        details = details.model_copy(
            update={
                "comparison": {
                    "difference": difference,
                    "percent_change": percent,
                    "before": before,
                    "after": after,
                }
            }
        )
        facts.extend(
            [
                Fact(id="difference", label="Difference", value=difference, sources=[table.ref.id]),
                Fact(
                    id="percent_change",
                    label="Percentage change",
                    value=percent,
                    unit="percent",
                    sources=[table.ref.id],
                ),
            ]
        )
    if recipe.correlation_columns:
        if len(recipe.correlation_columns) != 2:
            raise NeedsInput("Correlation requires exactly two numeric columns.")
        a, b = recipe.correlation_columns
        pairs = [
            (float(number(row[a])), float(number(row[b])))
            for row in rows
            if row[a].strip() and row[b].strip()
        ]
        if len(pairs) < 2 or len({x for x, _ in pairs}) < 2 or len({y for _, y in pairs}) < 2:
            raise NeedsInput("Correlation requires varying values and sufficient complete pairs.")
        correlation = statistics.correlation([x for x, _ in pairs], [y for _, y in pairs])
        details = details.model_copy(
            update={"correlation": correlation, "correlation_rows": len(pairs)}
        )
        warnings.append("Correlation describes an association; it does not establish a cause.")
        facts.append(
            Fact(id="correlation", label="Correlation", value=correlation, sources=[table.ref.id])
        )
    return details, facts, warnings


def chart(details, definitions=None):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    recipe = details.recipe
    if not recipe.chart_metric:
        return None
    if recipe.chart_metric not in {m.name for m in recipe.measures}:
        raise NeedsInput("Chart refers to an unknown calculation.")
    if len(details.groups) > 50 or not details.groups:
        raise Unsupported("Chart group count is outside the supported range.")
    labels = [
        ", ".join(value or "(missing)" for value in group.group.values())
        if group.group
        else "All rows"
        for group in details.groups
    ]
    values = [group.metrics[recipe.chart_metric] for group in details.groups]
    if any(value is None for value in values):
        raise NeedsInput("Chart contains an unmeasured value.")
    with PLOT_LOCK:
        figure = Figure(figsize=(9, 5), layout="constrained")
        canvas = FigureCanvasAgg(figure)
        axes = figure.subplots()
        if recipe.chart_kind == "line":
            axes.plot(labels, values, marker="o")
        else:
            axes.bar(labels, values)
        metric = next(item for item in recipe.measures if item.name == recipe.chart_metric)
        unit = definitions.units.get(metric.column, "") if definitions else ""
        axes.set_ylabel(recipe.chart_metric + (f" ({unit})" if unit else ""))
        axes.tick_params(axis="x", labelrotation=45)
        output = io.BytesIO()
        canvas.print_png(output)
        return output.getvalue()
