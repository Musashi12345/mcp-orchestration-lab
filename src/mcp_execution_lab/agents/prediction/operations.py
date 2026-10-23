import math
import random
from collections import Counter
from datetime import datetime

from ..common.models import NeedsInput, Unsupported
from ..common.operations import finite, number, require_columns
from .models import Details


def predict(table, recipe, rules, target=None, time_column=None, prediction_table=None):
    import numpy as np

    if recipe.question:
        raise NeedsInput(recipe.question)
    if target and target != recipe.target:
        raise NeedsInput("Proposed target differs from the assigned target.")
    if time_column and time_column != recipe.time_column:
        raise NeedsInput("Proposed time column differs from the assigned time column.")
    if len(set(recipe.features)) != len(recipe.features):
        raise NeedsInput("Prediction features must be distinct.")
    if recipe.target in recipe.features or set(recipe.features) & set(rules.excluded_columns):
        raise NeedsInput("Features include the answer or an explicitly excluded column.")
    if rules.allowed_features and not set(recipe.features) <= set(rules.allowed_features):
        raise NeedsInput("A feature is outside the task's allowed input columns.")
    required = (
        [recipe.target] + recipe.features + ([recipe.time_column] if recipe.time_column else [])
    )
    require_columns(table, required)
    if recipe.method == "last_value" and (not recipe.time_column or recipe.features):
        raise NeedsInput("Last-value forecasting requires a time column and no other features.")
    if recipe.method != "last_value" and not recipe.features:
        raise NeedsInput("This prediction method requires explicit numeric input columns.")
    usable, excluded = [], 0
    for index, row in enumerate(table.rows):
        if any(not row[column].strip() for column in required):
            if rules.missing_policy == "error":
                raise NeedsInput("Missing model inputs require an explicit handling rule.")
            excluded += 1
            continue
        usable.append((index + 2, row))
    if len(usable) < rules.minimum_rows:
        raise Unsupported("There are too few usable records for the configured prediction check.")
    if recipe.time_column:
        try:
            usable.sort(key=lambda item: datetime.fromisoformat(item[1][recipe.time_column]))
        except (ValueError, TypeError) as exc:
            raise NeedsInput(
                "Time-based prediction requires unambiguous, compatible ISO dates."
            ) from exc
        dates = [datetime.fromisoformat(item[1][recipe.time_column]) for item in usable]
        cut = len(usable) - max(1, math.ceil(len(usable) * rules.test_fraction))
        if dates[cut - 1] == dates[cut]:
            raise NeedsInput("Equal-time records cross the split; provide a task split rule.")
    else:
        random.Random(rules.seed).shuffle(usable)
    test_size = max(1, math.ceil(len(usable) * rules.test_fraction))
    train, test = usable[:-test_size], usable[-test_size:]
    manifest = {
        "training_source_rows": [index for index, _ in train],
        "test_source_rows": [index for index, _ in test],
        "seed": rules.seed,
        "time_column": recipe.time_column,
        "test_fraction": rules.test_fraction,
        "input": table.ref.model_dump(),
        "recipe": recipe.model_dump(),
    }

    def values(rows, columns):
        result = np.asarray(
            [[finite(number(row[column])) for column in columns] for _, row in rows], dtype=float
        )
        if not np.isfinite(result).all():
            raise Unsupported("Numeric inputs exceed supported limits.")
        return result

    prediction_rows, warnings = [], []
    future = (
        []
        if prediction_table is None
        else [(i + 2, row) for i, row in enumerate(prediction_table.rows)]
    )
    if prediction_table:
        require_columns(prediction_table, recipe.features)
        if recipe.method == "last_value":
            raise Unsupported(
                "Last-value forecasts use the specified horizon, not another input table."
            )
        if any(not row[column].strip() for _, row in future for column in recipe.features):
            raise NeedsInput("Rows to predict contain missing input values.")
    if recipe.method == "nearest_centroid":
        xtrain, xtest = values(train, recipe.features), values(test, recipe.features)
        means, scales = xtrain.mean(axis=0), xtrain.std(axis=0)
        scales = np.where(scales == 0, 1, scales)
        normalized = (xtrain - means) / scales
        labels = [row[recipe.target] for _, row in train]
        classes = sorted(set(labels))
        if len(classes) < 2 or len(classes) > 50:
            raise Unsupported("Classification needs between two and fifty training classes.")
        centroids = np.asarray(
            [normalized[np.asarray(labels) == label].mean(axis=0) for label in classes]
        )

        def infer(array):
            return [
                classes[int(np.argmin(np.sum((centroids - value) ** 2, axis=1)))]
                for value in (array - means) / scales
            ]

        predictions = infer(xtest)
        actual = [row[recipe.target] for _, row in test]
        majority = min(classes, key=lambda label: (-Counter(labels)[label], label))
        baseline = [majority] * len(test)
        metrics = {
            "accuracy": sum(a == b for a, b in zip(actual, predictions, strict=True)) / len(test)
        }
        baseline_metrics = {
            "accuracy": sum(a == b for a, b in zip(actual, baseline, strict=True)) / len(test)
        }
        parameters = {
            "classes": classes,
            "training_means": means.tolist(),
            "training_scales": scales.tolist(),
            "centroids": centroids.tolist(),
            "training_class_counts": dict(Counter(labels)),
        }
        future_predictions = infer(values(future, recipe.features)) if future else []
        warnings.append(
            "Classification currently reports accuracy and class counts; "
            "other scoring methods are not implemented."
        )
    else:
        ytrain = values(train, [recipe.target]).reshape(-1)
        actual = values(test, [recipe.target]).reshape(-1).tolist()
        if recipe.method == "linear_regression":
            if len(train) < len(recipe.features) + 2:
                raise Unsupported("Training data is too small for the requested number of inputs.")
            xtrain, xtest = values(train, recipe.features), values(test, recipe.features)
            design = np.column_stack((np.ones(len(train)), xtrain))
            coefficients = np.linalg.lstsq(design, ytrain, rcond=None)[0]

            def infer(array):
                return np.column_stack((np.ones(len(array)), array)) @ coefficients

            predictions = [finite(value) for value in infer(xtest)]
            baseline = [finite(ytrain.mean())] * len(test)
            parameters = {"coefficients": coefficients.tolist(), "intercept_included": True}
            future_predictions = (
                [finite(value) for value in infer(values(future, recipe.features))]
                if future
                else []
            )
        else:
            predictions = [finite(ytrain[-1])] * len(test)
            baseline = list(predictions)
            parameters = {
                "last_training_value": finite(ytrain[-1]),
                "last_observed_value": finite(number(usable[-1][1][recipe.target])),
            }
            future_predictions = [parameters["last_observed_value"]] * recipe.horizon
            warnings.append(
                "This is a simple last-value reference forecast, not an advanced forecasting model."
            )

        def errors(predicted):
            differences = [
                finite(number(a) - number(b)) for a, b in zip(actual, predicted, strict=True)
            ]
            return {
                "mean_absolute_error": finite(sum(abs(x) for x in differences) / len(differences)),
                "root_mean_squared_error": finite(
                    math.sqrt(sum(x * x for x in differences) / len(differences))
                ),
            }

        metrics, baseline_metrics = errors(predictions), errors(baseline)
    for (source_row, _), expected, predicted in zip(test, actual, predictions, strict=True):
        prediction_rows.append(
            {"source_row": source_row, "split": "test", "actual": expected, "predicted": predicted}
        )
    for index, predicted in enumerate(future_predictions):
        prediction_rows.append(
            {
                "source_row": future[index][0] if future else f"future_{index + 1}",
                "split": "future",
                "actual": "",
                "predicted": predicted,
            }
        )
    if not recipe.time_column:
        warnings.append(
            "A random held-back split checks similar records; "
            "it does not establish future time accuracy."
        )
    details = Details(
        method=recipe.method,
        target=recipe.target,
        features=recipe.features,
        training_rows=len(train),
        test_rows=len(test),
        excluded_rows=excluded,
        seed=rules.seed,
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        model_parameters=parameters,
        predictions_created=len(prediction_rows),
    )
    return details, manifest, prediction_rows, warnings
