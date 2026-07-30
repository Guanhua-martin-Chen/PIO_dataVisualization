from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from pio_platform.forecasting import (
    backtest_history,
    candidate_models,
    forecast_history,
    preprocess_history,
    select_best_model,
)
from pio_platform.ets_experiments import (
    VALIDATED_HMA_REVENUE_SPEC,
    forecast_ets_candidate,
)


FORECAST_LEVELS = {"brand", "model", "model_accessory"}
LATEST_MONTH_COMPLETENESS_THRESHOLD = 0.90
STATISTICAL_MODELS = {
    "naive_last", "mean", "weighted_moving_average", "trailing_12_mean",
    "trend_adjusted_moving_average", "damped_trend", "log_linear_trend",
    "seasonal_naive", "seasonal_mean", "ets_additive", "croston_sba",
}
MODEL_STRATEGIES = {
    "auto",
    "baseline_auto",
    "driver_adjusted_regression",
    "reference_portfolio",
    *STATISTICAL_MODELS,
}


def build_hierarchical_forecast(
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    *,
    level: str,
    horizon: int = 6,
    use_working_days: bool = True,
    use_seasonality: bool = True,
    tariff_impact_pct: float = 0.0,
    min_monthly_volume: float = 5.0,
    model_strategy: str = "auto",
    target_metric: str = "quantity",
    limit: int = 100,
    latest_month_is_complete: bool = False,
    check_latest_volume: bool = True,
) -> dict[str, Any]:
    if level not in FORECAST_LEVELS:
        raise ValueError(f"Unsupported forecast level: {level}")
    if model_strategy not in MODEL_STRATEGIES:
        raise ValueError(f"Unsupported model strategy: {model_strategy}")
    if model_strategy == "reference_portfolio" and (
        level != "brand" or target_metric != "revenue"
    ):
        raise ValueError(
            "reference_portfolio is available only for Forecast Center Revenue Brand anchors."
        )
    if level == "model_accessory" and model_strategy != "auto":
        raise ValueError(
            "Model × accessory forecasting always uses automatic per-series model selection; "
            "a shared forced model is not available at this level."
        )
    if facts.empty:
        return _empty_payload(level, horizon, use_working_days, use_seasonality, tariff_impact_pct, min_monthly_volume, model_strategy)

    working = facts.copy()
    working["installationQuantity"] = pd.to_numeric(working["installationQuantity"], errors="coerce").fillna(0).clip(lower=0)
    working["month"] = pd.to_datetime(working["month"].astype(str) + "-01", errors="coerce")
    working = working[working["month"].notna()]
    if working.empty:
        return _empty_payload(level, horizon, use_working_days, use_seasonality, tariff_impact_pct, min_monthly_volume, model_strategy)

    latest_observed_month = working["month"].max()
    monthly_total = working.groupby("month")["installationQuantity"].sum().sort_index()
    prior_totals = monthly_total[monthly_total.index < latest_observed_month].tail(3)
    prior_median = float(prior_totals.median()) if not prior_totals.empty else 0.0
    latest_total = float(monthly_total.get(latest_observed_month, 0.0))
    completeness_ratio = latest_total / prior_median if prior_median > 0 else None
    volume_supports_complete = (
        not check_latest_volume
        or completeness_ratio is None
        or completeness_ratio >= LATEST_MONTH_COMPLETENESS_THRESHOLD
    )
    resolved_latest_complete = bool(latest_month_is_complete and volume_supports_complete)
    latest_complete_month = (
        latest_observed_month
        if resolved_latest_complete
        else latest_observed_month - pd.offsets.MonthBegin(1)
    )
    working = working[working["month"] <= latest_complete_month]
    if working.empty:
        return _empty_payload(level, horizon, use_working_days, use_seasonality, tariff_impact_pct, min_monthly_volume, model_strategy)

    group_columns = _group_columns(level)
    monthly = working.groupby(group_columns + ["month"], as_index=False)["installationQuantity"].sum()
    metadata = working.groupby(group_columns, as_index=False).agg(
        lifecycleStatus=("lifecycleStatus", _mixed_or_mode),
        historyVolume=("installationQuantity", "sum"),
    )
    working_day_map = _working_day_map(working_days)
    records: list[dict[str, Any]] = []
    group_stats = (
        monthly.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            historyVolume=("installationQuantity", "sum"),
            activeMonths=("installationQuantity", lambda values: int((values > 0).sum())),
            firstMonth=("month", "min"),
        )
    )
    group_stats["historyMonths"] = (
        (latest_complete_month.year - group_stats["firstMonth"].dt.year) * 12
        + latest_complete_month.month
        - group_stats["firstMonth"].dt.month
        + 1
    )
    group_stats["monthlyAverage"] = group_stats["historyVolume"] / group_stats["historyMonths"].clip(lower=1)
    eligible_stats = group_stats[
        (group_stats["monthlyAverage"] >= min_monthly_volume)
        & (group_stats["activeMonths"] >= 6)
    ].sort_values("historyVolume", ascending=False)
    excluded_low_volume = int(len(group_stats) - len(eligible_stats))
    selected_keys = {
        tuple(str(row[column]) for column in group_columns)
        for _, row in eligible_stats.head(limit).iterrows()
    }

    grouped = monthly.groupby(group_columns[0] if len(group_columns) == 1 else group_columns, dropna=False, sort=True)
    for raw_key, group in grouped:
        key_values = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        dimensions = dict(zip(group_columns, key_values, strict=False))
        if tuple(str(dimensions[column]) for column in group_columns) not in selected_keys:
            continue
        start_month = group["month"].min()
        month_index = pd.date_range(start_month, latest_complete_month, freq="MS")
        series = group.set_index("month")["installationQuantity"].reindex(month_index, fill_value=0.0).astype(float)
        history = series.tolist()
        active_months = int((series > 0).sum())
        monthly_average = float(series.mean()) if len(series) else 0.0
        meta_mask = pd.Series(True, index=metadata.index)
        for column, value in dimensions.items():
            meta_mask &= metadata[column].fillna("").astype(str) == str(value)
        meta = metadata.loc[meta_mask].iloc[0] if meta_mask.any() else None
        lifecycle_status = str(meta["lifecycleStatus"]) if meta is not None else "Unknown"

        final_selection = _select_forecast_candidate(
            series,
            working_day_map,
            entity=str(dimensions.get("brand", "")),
            horizon=horizon,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            model_strategy=model_strategy,
        )
        evaluation = _independent_outer_backtest(
            series,
            working_day_map,
            entity=str(dimensions.get("brand", "")),
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            model_strategy=model_strategy,
        )
        selected_model = final_selection["model"]
        baseline_values = final_selection["forecast"]

        if lifecycle_status.startswith("Discontinued through") and level != "brand":
            selected_model = "discontinued_zero"
            baseline_values = [0.0] * horizon

        tariff_multiplier = max(0.0, 1.0 + float(tariff_impact_pct) / 100.0)
        forecast_values = [max(0.0, float(value) * tariff_multiplier) for value in baseline_values]
        future_months = pd.date_range(latest_complete_month + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
        volume = float(series.sum())
        record = {
            "seriesKey": "::".join(str(dimensions[column]) for column in group_columns),
            "level": level,
            "brand": str(dimensions.get("brand", "")),
            "modelName": str(dimensions.get("modelName", "")),
            "entityKey": str(dimensions.get("entityKey", "")),
            "partNumber": str(dimensions.get("partNumber", "")),
            "partDescription": _dimension_description(working, dimensions),
            "lifecycleStatus": lifecycle_status,
            "historyMonths": int(len(history)),
            "activeMonths": active_months,
            "historyVolume": volume,
            "monthlyAverage": monthly_average,
            "latestActual": float(series.iloc[-1]),
            "selectedModel": selected_model,
            "brandSpecificMethod": selected_model,
            "requestedModelStrategy": model_strategy,
            "selectionNote": final_selection["selectionNote"],
            "learnedCoefficients": final_selection["coefficients"],
            "backtestModel": evaluation["model"],
            "backtestPoints": evaluation["points"],
            "backtestActual": evaluation["actualSum"],
            "backtestAbsoluteError": evaluation["absoluteErrorSum"],
            "wape": evaluation["wape"],
            "accuracyPct": _accuracy_pct(evaluation["wape"]),
            "mae": evaluation["mae"],
            "bias": evaluation["bias"],
            "applicationRecentH1Rows": evaluation["rows"],
            "rollingOriginResiduals": [],
            "forecast": [
                {"month": month.strftime("%Y-%m"), "value": float(value)}
                for month, value in zip(future_months, forecast_values, strict=False)
            ],
            "nextForecast": float(forecast_values[0]) if forecast_values else 0.0,
        }
        records.append(record)

    records.sort(key=lambda item: item["historyVolume"], reverse=True)
    model_counts = Counter(item["selectedModel"] for item in records)
    total_backtest_actual = sum(float(item["backtestActual"]) for item in records)
    total_backtest_error = sum(float(item["backtestAbsoluteError"]) for item in records)
    weighted_wape = total_backtest_error / total_backtest_actual if total_backtest_actual > 0 else None
    return {
        "summary": {
            "level": level,
            "seriesCount": len(records),
            "excludedLowVolumeSeries": excluded_low_volume,
            "latestCompleteMonth": latest_complete_month.strftime("%Y-%m"),
            "latestObservedMonth": latest_observed_month.strftime("%Y-%m"),
            "latestMonthCompletenessRatio": round(float(completeness_ratio), 4) if completeness_ratio is not None else None,
            "latestMonthCompletenessThreshold": LATEST_MONTH_COMPLETENESS_THRESHOLD,
            "latestMonthExcluded": not resolved_latest_complete,
            "horizon": horizon,
            "weightedWape": float(weighted_wape) if weighted_wape is not None else None,
            "accuracyPct": _accuracy_pct(weighted_wape),
            "modelCounts": dict(model_counts),
            "factors": {
                "workingDays": use_working_days,
                "seasonality": use_seasonality,
                "tariffImpactPct": float(tariff_impact_pct),
                "minMonthlyVolume": float(min_monthly_volume),
                "modelStrategy": model_strategy,
            },
            "calculation": _calculation_description(level),
            "accuracyDefinition": "Accuracy = max(0, 1 - independent outer rolling-test WAPE); test months are not used for model selection.",
        },
        "records": records,
}


def _select_forecast_candidate(
    series: pd.Series,
    working_day_map: dict[str, float],
    *,
    entity: str,
    horizon: int,
    use_working_days: bool,
    use_seasonality: bool,
    model_strategy: str,
) -> dict[str, Any]:
    history = series.astype(float).tolist()
    if model_strategy == "reference_portfolio":
        return _reference_portfolio_selection(
            series,
            working_day_map,
            entity=entity,
            horizon=horizon,
        )
    model_name, _, diagnostics = select_best_model(history, use_seasonality=use_seasonality)
    processed_history, _ = preprocess_history(history, diagnostics.preprocessing)
    selection: dict[str, Any] = {
        "model": model_name,
        "preprocessing": diagnostics.preprocessing,
        "forecast": forecast_history(processed_history, horizon=horizon, model_name=model_name),
        "wape": diagnostics.wape,
        "selectionNote": "Automatically selected the lowest-WAPE eligible statistical baseline.",
        "coefficients": {},
    }
    if model_strategy in STATISTICAL_MODELS:
        eligible = candidate_models(history, use_seasonality=use_seasonality)
        if model_strategy in eligible:
            forced_diagnostics = backtest_history(history, model_strategy, preprocessing="raw")
            return {
                "model": model_strategy,
                "preprocessing": "raw",
                "forecast": forecast_history(history, horizon=horizon, model_name=model_strategy),
                "wape": forced_diagnostics.wape,
                "selectionNote": f"User forced statistical model: {model_strategy}.",
                "coefficients": {},
            }
        selection["selectionNote"] = (
            f"Requested {model_strategy}, but the series did not meet its history/seasonality requirements; "
            f"fell back to automatic baseline {model_name}."
        )
        return selection

    driver_result = _driver_forecast(
        series,
        working_day_map,
        horizon=horizon,
        use_working_days=use_working_days,
        use_seasonality=use_seasonality,
    )
    if model_strategy == "baseline_auto":
        selection["selectionNote"] = "Automatic selection restricted to statistical baselines; driver regression was excluded."
        return selection
    if model_strategy == "driver_adjusted_regression":
        if driver_result is None:
            selection["selectionNote"] = (
                "Driver regression was requested but requires at least 18 months and one enabled driver; "
                f"fell back to automatic baseline {model_name}."
            )
            return selection
        return {
            "model": "driver_adjusted_regression",
            "preprocessing": "raw",
            "forecast": driver_result["forecast"],
            "wape": driver_result["wape"],
            "selectionNote": "User forced OLS driver regression.",
            "coefficients": driver_result["coefficients"],
        }
    if driver_result is not None and (
        selection["wape"] is None
        or (driver_result["wape"] is not None and driver_result["wape"] < selection["wape"])
    ):
        selection = {
            "model": "driver_adjusted_regression",
            "preprocessing": "raw",
            "forecast": driver_result["forecast"],
            "wape": driver_result["wape"],
            "selectionNote": "Auto selected OLS driver regression because its inner-validation WAPE beat the statistical baselines.",
            "coefficients": driver_result["coefficients"],
        }
    return selection


def _independent_outer_backtest(
    series: pd.Series,
    working_day_map: dict[str, float],
    *,
    entity: str,
    use_working_days: bool,
    use_seasonality: bool,
    model_strategy: str,
) -> dict[str, Any]:
    values = series.astype(float)
    holdout = min(6, max(3, len(values) // 4))
    split = len(values) - holdout
    if split < 3:
        return _empty_backtest()

    selection = _select_forecast_candidate(
        values.iloc[:split],
        working_day_map,
        entity=entity,
        horizon=1,
        use_working_days=use_working_days,
        use_seasonality=use_seasonality,
        model_strategy=model_strategy,
    )
    predictions: list[float] = []
    actuals: list[float] = []
    rows: list[dict[str, Any]] = []
    for index in range(split, len(values)):
        expanding = values.iloc[:index]
        if model_strategy == "reference_portfolio":
            prediction = _reference_portfolio_selection(
                expanding,
                working_day_map,
                entity=entity,
                horizon=1,
            )["forecast"][0]
        elif selection["model"] == "driver_adjusted_regression":
            prediction = _regression_predict(
                list(expanding.index),
                expanding.to_numpy(dtype=float),
                [values.index[index]],
                working_day_map,
                use_working_days,
                use_seasonality,
            )[0]
        else:
            processed, _ = preprocess_history(expanding.tolist(), selection["preprocessing"])
            prediction = forecast_history(processed, horizon=1, model_name=selection["model"])[0]
        predictions.append(max(0.0, float(prediction)))
        actuals.append(float(values.iloc[index]))
        rows.append(
            {
                "origin_month": str(pd.Timestamp(values.index[index - 1]).to_period("M")),
                "target_month": str(pd.Timestamp(values.index[index]).to_period("M")),
                "horizon": 1,
                "actual": float(values.iloc[index]),
                "prediction": max(0.0, float(prediction)),
                "entity": entity,
            }
        )

    absolute_error = sum(abs(predicted - actual) for predicted, actual in zip(predictions, actuals, strict=False))
    actual_sum = sum(actuals)
    predicted_sum = sum(predictions)
    return {
        "model": selection["model"],
        "points": len(actuals),
        "actualSum": float(actual_sum),
        "absoluteErrorSum": float(absolute_error),
        "wape": float(absolute_error / actual_sum) if actual_sum > 0 else None,
        "mae": float(absolute_error / len(actuals)) if actuals else None,
        "bias": float((predicted_sum - actual_sum) / actual_sum) if actual_sum > 0 else None,
        "rows": rows,
    }


def rolling_origin_residuals(
    series: pd.Series,
    working_day_map: dict[str, float],
    *,
    entity: str,
    use_working_days: bool,
    use_seasonality: bool,
    model_strategy: str,
    minimum_training_months: int = 24,
    horizons: tuple[int, ...] = (1, 2, 3),
) -> list[dict[str, Any]]:
    """Return complete H1/H2/H3 held-out rows for interval calibration."""

    values = series.astype(float)
    if len(values) <= minimum_training_months:
        return []
    rows: list[dict[str, Any]] = []
    max_horizon = max(horizons)
    for training_end in range(minimum_training_months, len(values)):
        available_horizons = [
            horizon
            for horizon in horizons
            if training_end + horizon - 1 < len(values)
        ]
        if not available_horizons:
            continue
        training = values.iloc[:training_end]
        requested_horizon = min(max_horizon, max(available_horizons))
        selection = _select_forecast_candidate(
            training,
            working_day_map,
            entity=entity,
            horizon=requested_horizon,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            model_strategy=model_strategy,
        )
        forecasts = selection["forecast"]
        origin = pd.Timestamp(values.index[training_end - 1]).to_period("M")
        for horizon in available_horizons:
            target_position = training_end + horizon - 1
            rows.append(
                {
                    "origin_month": str(origin),
                    "target_month": str(
                        pd.Timestamp(values.index[target_position]).to_period("M")
                    ),
                    "horizon": horizon,
                    "actual": float(values.iloc[target_position]),
                    "prediction": max(0.0, float(forecasts[horizon - 1])),
                    "entity": entity,
                    "backtest_model": selection["model"],
                }
            )
    return rows


def _reference_portfolio_selection(
    series: pd.Series,
    working_day_map: dict[str, float],
    *,
    entity: str,
    horizon: int,
) -> dict[str, Any]:
    history = series.astype(float).tolist()
    normalized_entity = str(entity).strip().upper()
    if normalized_entity == "HMA":
        forecast, diagnostics = forecast_ets_candidate(
            history,
            horizon,
            VALIDATED_HMA_REVENUE_SPEC,
        )
        return {
            "model": VALIDATED_HMA_REVENUE_SPEC.model_id,
            "preprocessing": VALIDATED_HMA_REVENUE_SPEC.preprocessing,
            "forecast": forecast,
            "wape": None,
            "selectionNote": (
                "Validated reference portfolio: HMA uses optimized additive "
                "Holt-Winters with the governed rolling-24 configuration."
            ),
            "coefficients": diagnostics["parameters"],
        }
    if normalized_entity == "GMA":
        return {
            "model": "naive_last",
            "preprocessing": "raw",
            "forecast": forecast_history(history, horizon, "naive_last"),
            "wape": None,
            "selectionNote": "Validated reference portfolio: GMA uses Last-Month Revenue.",
            "coefficients": {},
        }
    if normalized_entity == "KUS":
        if not working_day_map:
            raise ValueError(
                "reference_portfolio requires the governed Working_Days calendar for KUS."
            )
        return {
            "model": "working_day_adjusted_seasonal",
            "preprocessing": "raw",
            "forecast": _working_day_adjusted_seasonal_forecast(
                series,
                horizon,
                working_day_map,
            ),
            "wape": None,
            "selectionNote": (
                "Validated reference portfolio: KUS uses Working-Day-Adjusted Seasonal."
            ),
            "coefficients": {},
        }
    raise ValueError(
        f"reference_portfolio supports only HMA, GMA, and KUS; received {entity!r}."
    )


def _working_day_adjusted_seasonal_forecast(
    series: pd.Series,
    horizon: int,
    working_day_map: dict[str, float],
) -> list[float]:
    values = [max(float(value), 0.0) for value in series.tolist()]
    last_month = pd.Timestamp(series.index[-1])
    forecasts: list[float] = []
    for step in range(1, horizon + 1):
        target = last_month + pd.offsets.MonthBegin(step)
        target_key = target.strftime("%Y-%m")
        prior_key = (target - pd.DateOffset(years=1)).strftime("%Y-%m")
        seasonal_value = values[-12] if len(values) >= 12 else values[-1]
        current_days = float(working_day_map.get(target_key, 0.0) or 0.0)
        prior_days = float(working_day_map.get(prior_key, 0.0) or 0.0)
        ratio = current_days / prior_days if current_days > 0 and prior_days > 0 else 1.0
        prediction = max(float(seasonal_value) * ratio, 0.0)
        forecasts.append(prediction)
        values.append(prediction)
    return forecasts


def _empty_backtest() -> dict[str, Any]:
    return {
        "model": "unavailable",
        "points": 0,
        "actualSum": 0.0,
        "absoluteErrorSum": 0.0,
        "wape": None,
        "mae": None,
        "bias": None,
        "rows": [],
    }


def _driver_forecast(
    series: pd.Series,
    working_day_map: dict[str, float],
    *,
    horizon: int,
    use_working_days: bool,
    use_seasonality: bool,
) -> dict[str, Any] | None:
    if len(series) < 18 or not (use_working_days or use_seasonality):
        return None
    months = list(series.index)
    values = series.astype(float).to_numpy()
    holdout = min(6, max(3, len(values) // 4))
    predictions: list[float] = []
    actuals: list[float] = []
    for index in range(len(values) - holdout, len(values)):
        if index < 12:
            continue
        prediction = _regression_predict(
            months[:index],
            values[:index],
            [months[index]],
            working_day_map,
            use_working_days,
            use_seasonality,
        )[0]
        predictions.append(max(0.0, float(prediction)))
        actuals.append(float(values[index]))
    if not actuals:
        return None
    error_sum = sum(abs(predicted - actual) for predicted, actual in zip(predictions, actuals, strict=False))
    actual_sum = sum(actuals)
    wape = error_sum / actual_sum if actual_sum else None
    mae = error_sum / len(actuals)
    bias = (sum(predictions) - actual_sum) / actual_sum if actual_sum else None
    future_months = list(pd.date_range(months[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS"))
    forecast = _regression_predict(
        months,
        values,
        future_months,
        working_day_map,
        use_working_days,
        use_seasonality,
    )
    mean_days = np.mean(list(working_day_map.values())) if working_day_map else 21.0
    design = _design_matrix(months, 0, working_day_map, mean_days, use_working_days, use_seasonality)
    fitted_coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    coefficient_names = ["intercept", "trendPerMonth"]
    if use_working_days:
        coefficient_names.append("workingDaysCenteredRatio")
    if use_seasonality:
        coefficient_names.extend(["seasonSin", "seasonCos"])
    coefficients = {
        name: round(float(value), 6)
        for name, value in zip(coefficient_names, fitted_coefficients, strict=False)
    }
    if use_working_days and "workingDaysCenteredRatio" in coefficients:
        coefficients["workingDaysPerDayEffect"] = round(
            coefficients["workingDaysCenteredRatio"] / max(float(mean_days), 1.0), 6
        )
    if use_seasonality and {"seasonSin", "seasonCos"}.issubset(coefficients):
        coefficients["seasonalAmplitude"] = round(
            float(np.hypot(coefficients["seasonSin"], coefficients["seasonCos"])), 6
        )
    return {
        "forecast": [max(0.0, float(value)) for value in forecast],
        "wape": float(wape) if wape is not None else None,
        "mae": float(mae),
        "bias": float(bias) if bias is not None else None,
        "coefficients": coefficients,
    }


def _regression_predict(
    train_months: list[pd.Timestamp],
    train_values: np.ndarray,
    future_months: list[pd.Timestamp],
    working_day_map: dict[str, float],
    use_working_days: bool,
    use_seasonality: bool,
) -> np.ndarray:
    mean_days = np.mean(list(working_day_map.values())) if working_day_map else 21.0
    train_x = _design_matrix(train_months, 0, working_day_map, mean_days, use_working_days, use_seasonality)
    coefficients, *_ = np.linalg.lstsq(train_x, train_values, rcond=None)
    future_x = _design_matrix(
        future_months,
        len(train_months),
        working_day_map,
        mean_days,
        use_working_days,
        use_seasonality,
    )
    return future_x @ coefficients


def _design_matrix(
    months: list[pd.Timestamp],
    start_index: int,
    working_day_map: dict[str, float],
    mean_days: float,
    use_working_days: bool,
    use_seasonality: bool,
) -> np.ndarray:
    rows: list[list[float]] = []
    for offset, month in enumerate(months):
        row = [1.0, float(start_index + offset)]
        if use_working_days:
            days = working_day_map.get(month.strftime("%Y-%m"), _calendar_month_working_day_fallback(month, working_day_map, mean_days))
            row.append((float(days) - mean_days) / max(mean_days, 1.0))
        if use_seasonality:
            angle = 2.0 * np.pi * month.month / 12.0
            row.extend([float(np.sin(angle)), float(np.cos(angle))])
        rows.append(row)
    return np.asarray(rows, dtype=float)


def _working_day_map(working_days: pd.DataFrame | None) -> dict[str, float]:
    if working_days is None or working_days.empty or not {"month", "workingDays"}.issubset(working_days.columns):
        return {}
    return {
        str(row["month"])[:7]: float(row["workingDays"])
        for _, row in working_days.dropna(subset=["month", "workingDays"]).iterrows()
    }


def _calendar_month_working_day_fallback(month: pd.Timestamp, mapping: dict[str, float], overall: float) -> float:
    values = [value for key, value in mapping.items() if key.endswith(f"-{month.month:02d}")]
    return float(np.mean(values)) if values else overall


def _group_columns(level: str) -> list[str]:
    if level == "brand":
        return ["brand"]
    if level == "model":
        return ["brand", "entityKey", "modelName"]
    return ["brand", "entityKey", "modelName", "partNumber"]


def _calculation_description(level: str) -> dict[str, Any]:
    grain = {
        "brand": "month × brand",
        "model": "month × brand × model entity",
        "model_accessory": "month × brand × model entity × accessory",
    }[level]
    return {
        "target": "Monthly SUM(installationQuantity)",
        "aggregationGrain": grain,
        "workingDaysFeature": "x_wd = (workingDays - meanWorkingDays) / meanWorkingDays; OLS learns beta_wd. It has no fixed manual weight.",
        "seasonalityFeature": "x_sin = sin(2*pi*month/12), x_cos = cos(2*pi*month/12); OLS learns both coefficients. The switch also controls seasonal baseline eligibility.",
        "driverEquation": "y_hat = beta0 + betaTrend*t + betaWD*x_wd + betaSin*x_sin + betaCos*x_cos",
        "tariffFormula": "finalForecast = max(0, modelForecast * max(0, 1 + tariffImpactPct/100))",
        "volumeFilter": "Keep a series only when history average >= minMonthlyVolume and activeMonths >= 6.",
        "selectionProcess": "Inner rolling validation selects a model; the last 3-6 months are held out for independent outer testing.",
    }


def _dimension_description(facts: pd.DataFrame, dimensions: dict[str, Any]) -> str:
    if "partNumber" not in dimensions or "partDescription" not in facts.columns:
        return ""
    mask = pd.Series(True, index=facts.index)
    for column, value in dimensions.items():
        if column in facts.columns:
            mask &= facts[column].fillna("").astype(str) == str(value)
    values = facts.loc[mask, "partDescription"].dropna().astype(str).str.strip()
    return values.mode().iloc[0] if not values.empty else ""


def _mixed_or_mode(values: pd.Series) -> str:
    cleaned = sorted({str(value) for value in values.dropna() if str(value)})
    return cleaned[0] if len(cleaned) == 1 else "Mixed"


def _accuracy_pct(wape: float | None) -> float | None:
    return round(max(0.0, 1.0 - float(wape)) * 100.0, 2) if wape is not None else None


def _empty_payload(
    level: str,
    horizon: int,
    use_working_days: bool,
    use_seasonality: bool,
    tariff_impact_pct: float,
    min_monthly_volume: float,
    model_strategy: str,
) -> dict[str, Any]:
    return {
        "summary": {
            "level": level,
            "seriesCount": 0,
            "excludedLowVolumeSeries": 0,
            "latestCompleteMonth": None,
            "latestObservedMonth": None,
            "latestMonthCompletenessRatio": None,
            "latestMonthCompletenessThreshold": LATEST_MONTH_COMPLETENESS_THRESHOLD,
            "latestMonthExcluded": False,
            "horizon": horizon,
            "weightedWape": None,
            "accuracyPct": None,
            "modelCounts": {},
            "factors": {
                "workingDays": use_working_days,
                "seasonality": use_seasonality,
                "tariffImpactPct": tariff_impact_pct,
                "minMonthlyVolume": min_monthly_volume,
                "modelStrategy": model_strategy,
            },
            "calculation": _calculation_description(level),
            "accuracyDefinition": "Accuracy = max(0, 1 - independent outer rolling-test WAPE); test months are not used for model selection.",
        },
        "records": [],
    }
