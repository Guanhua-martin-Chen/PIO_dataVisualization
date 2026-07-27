from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from pio_platform.forecasting import forecast_history, preprocess_history, select_best_model


CONTRACT_VERSION = "pio-backtest-v1"


@dataclass(frozen=True)
class BacktestContract:
    """One comparison contract for statistical, reference, and ML models."""

    version: str = CONTRACT_VERSION
    minimum_training_months: int = 24
    horizons: tuple[int, ...] = (1, 2, 3)
    tie_band_wape: float = 0.01
    primary_metric: str = "wape"
    fold_type: str = "expanding_rolling_origin"

    def __post_init__(self) -> None:
        if self.minimum_training_months < 2:
            raise ValueError("minimum_training_months must be at least 2")
        if not self.horizons or any(horizon < 1 for horizon in self.horizons):
            raise ValueError("horizons must contain positive integers")


@dataclass(frozen=True)
class FoldPrediction:
    model_id: str
    target: str
    level: str
    entity: str
    origin_month: str
    target_month: str
    horizon: int
    actual: float
    prediction: float
    backtest_model: str
    training_months: int
    source_hash: str = ""
    contract_version: str = CONTRACT_VERSION


Predictor = Callable[
    [Sequence[float], int, Sequence[pd.Period], Sequence[pd.Period], Mapping[str, float] | None],
    tuple[float, str],
]


MODEL_COMPLEXITY = {
    "naive_last": 1,
    "mean": 1,
    "weighted_moving_average": 2,
    "trailing_12_mean": 2,
    "seasonal_naive": 2,
    "seasonal_mean": 3,
    "trend_adjusted_moving_average": 3,
    "damped_trend": 3,
    "log_linear_trend": 3,
    "croston_sba": 3,
    "ets_additive": 4,
    "auto": 5,
}


def normalize_monthly_series(
    values: pd.Series | pd.DataFrame | Iterable[tuple[Any, Any]],
    *,
    month_col: str = "month",
    value_col: str = "value",
    start_month: str | None = None,
    end_month: str | None = None,
) -> pd.Series:
    """Return a complete, non-negative monthly PeriodIndex series.

    Missing calendar months are explicit zero observations. Duplicate month
    rows are summed. Negative business measures, including source sentinel -1,
    are clamped to zero.
    """

    if isinstance(values, pd.Series):
        raw = pd.DataFrame({month_col: values.index, value_col: values.to_numpy()})
    elif isinstance(values, pd.DataFrame):
        raw = values[[month_col, value_col]].copy()
    else:
        raw = pd.DataFrame(list(values), columns=[month_col, value_col])

    if raw.empty:
        return pd.Series(dtype="float64", index=pd.PeriodIndex([], freq="M"), name=value_col)

    month_values = raw[month_col]
    if isinstance(month_values.dtype, pd.PeriodDtype):
        months = month_values.dt.asfreq("M")
    else:
        normalized_month_values = month_values.map(
            lambda value: str(value) if isinstance(value, pd.Period) else value
        )
        months = pd.to_datetime(normalized_month_values, errors="coerce").dt.to_period("M")
    numeric = pd.to_numeric(raw[value_col], errors="coerce").fillna(0.0).clip(lower=0.0)
    grouped = pd.DataFrame({"month": months, "value": numeric}).dropna(subset=["month"])
    grouped = grouped.groupby("month", sort=True)["value"].sum()
    if grouped.empty:
        return pd.Series(dtype="float64", index=pd.PeriodIndex([], freq="M"), name=value_col)

    first = pd.Period(start_month, freq="M") if start_month else grouped.index.min()
    last = pd.Period(end_month, freq="M") if end_month else grouped.index.max()
    index = pd.period_range(first, last, freq="M")
    result = grouped.reindex(index, fill_value=0.0).astype(float)
    result.name = value_col
    return result


def make_predictor(model_name: str) -> Predictor:
    """Build a leakage-safe predictor used inside each outer fold."""

    normalized = str(model_name).strip().lower()

    def predict(
        history: Sequence[float],
        horizon: int,
        training_months: Sequence[pd.Period],
        target_months: Sequence[pd.Period],
        working_days: Mapping[str, float] | None,
    ) -> tuple[float, str]:
        clean_history = [max(float(value), 0.0) for value in history]
        if normalized == "auto":
            selected, _, diagnostics = select_best_model(clean_history)
            prepared, _ = preprocess_history(clean_history, diagnostics.preprocessing)
            prediction = forecast_history(prepared, horizon, selected)[-1]
            return max(float(prediction), 0.0), f"{selected}:{diagnostics.preprocessing}"

        if normalized in {"working_day_adjusted_seasonal", "wd_seasonal"}:
            predictions = _working_day_adjusted_seasonal(
                clean_history,
                training_months=training_months,
                target_months=target_months[:horizon],
                working_days=working_days or {},
            )
            return predictions[-1], "working_day_adjusted_seasonal"

        prediction = forecast_history(clean_history, horizon, normalized)[-1]
        return max(float(prediction), 0.0), normalized

    return predict


def run_series_backtest(
    series: pd.Series,
    *,
    model_id: str,
    target: str,
    level: str,
    entity: str,
    contract: BacktestContract | None = None,
    predictor: Predictor | None = None,
    working_days: Mapping[str, float] | None = None,
    source_hash: str = "",
) -> list[FoldPrediction]:
    """Run one monthly series on expanding common rolling-origin folds."""

    active_contract = contract or BacktestContract()
    monthly = normalize_monthly_series(series)
    if len(monthly) <= active_contract.minimum_training_months:
        return []

    model_predictor = predictor or make_predictor(model_id)
    records: list[FoldPrediction] = []
    max_horizon = max(active_contract.horizons)

    for training_end in range(active_contract.minimum_training_months, len(monthly)):
        history = monthly.iloc[:training_end].tolist()
        training_month_index = monthly.index[:training_end].tolist()
        origin_month = monthly.index[training_end - 1]
        possible_targets = monthly.index[training_end : min(training_end + max_horizon, len(monthly))].tolist()

        for horizon in active_contract.horizons:
            target_position = training_end + horizon - 1
            if target_position >= len(monthly):
                continue
            prediction, selected_model = model_predictor(
                history,
                horizon,
                training_month_index,
                possible_targets,
                working_days,
            )
            records.append(
                FoldPrediction(
                    model_id=model_id,
                    target=target,
                    level=level,
                    entity=entity,
                    origin_month=str(origin_month),
                    target_month=str(monthly.index[target_position]),
                    horizon=horizon,
                    actual=float(monthly.iloc[target_position]),
                    prediction=max(float(prediction), 0.0),
                    backtest_model=selected_model,
                    training_months=training_end,
                    source_hash=source_hash,
                    contract_version=active_contract.version,
                )
            )
    return records


def run_portfolio_backtest(
    monthly_frame: pd.DataFrame,
    *,
    model_id: str,
    target: str,
    entity_models: Mapping[str, str],
    contract: BacktestContract | None = None,
    month_col: str = "month",
    entity_col: str = "entity",
    value_col: str = "value",
    working_days: Mapping[str, float] | None = None,
    source_hash: str = "",
) -> dict[str, Any]:
    """Backtest entities and evaluate the official total on common folds."""

    active_contract = contract or BacktestContract()
    entity_rows: list[FoldPrediction] = []
    for entity, model_name in entity_models.items():
        entity_source = monthly_frame[monthly_frame[entity_col].astype(str) == str(entity)]
        series = normalize_monthly_series(
            entity_source,
            month_col=month_col,
            value_col=value_col,
        )
        entity_rows.extend(
            run_series_backtest(
                series,
                model_id=model_id,
                target=target,
                level="anchor_brand",
                entity=str(entity),
                contract=active_contract,
                predictor=make_predictor(model_name),
                working_days=working_days,
                source_hash=source_hash,
            )
        )

    entity_frame = predictions_to_frame(entity_rows)
    if entity_frame.empty:
        return {
            "contract": asdict(active_contract),
            "modelId": model_id,
            "target": target,
            "entityMetrics": {},
            "officialTotalMetrics": summarize_predictions(entity_frame),
            "predictions": [],
        }

    expected_entities = set(map(str, entity_models))
    fold_keys = ["origin_month", "target_month", "horizon"]
    counts = entity_frame.groupby(fold_keys)["entity"].nunique()
    common_keys = counts[counts == len(expected_entities)].index
    common = entity_frame.set_index(fold_keys).loc[common_keys].reset_index()
    total = (
        common.groupby(fold_keys, as_index=False)
        .agg(actual=("actual", "sum"), prediction=("prediction", "sum"))
    )

    entity_metrics = {
        entity: summarize_predictions(group)
        for entity, group in entity_frame.groupby("entity", sort=True)
    }
    return {
        "contract": asdict(active_contract),
        "modelId": model_id,
        "target": target,
        "entityMetrics": entity_metrics,
        "officialTotalMetrics": summarize_predictions(total),
        "predictions": entity_frame.to_dict(orient="records"),
    }


def evaluate_prediction_frame(
    frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    prediction_col: str = "prediction",
) -> dict[str, Any]:
    """Evaluate held-out anchor, allocation, unit-revenue, or nowcast rows."""

    renamed = frame.rename(columns={actual_col: "actual", prediction_col: "prediction"})
    return summarize_predictions(renamed)


def run_nowcast_backtest(
    frame: pd.DataFrame,
    *,
    cutoff_weights: Mapping[int, float],
    cutoff_col: str = "cutoff_day",
    actual_col: str = "actual",
    premonth_col: str = "premonth_forecast",
    mtd_projection_col: str = "mtd_completion_projection",
) -> dict[str, Any]:
    """Evaluate precomputed leakage-safe cutoff observations.

    The caller must construct each historical MTD completion projection using
    observations available on that cutoff day only.
    """

    required = {cutoff_col, actual_col, premonth_col, mtd_projection_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing nowcast columns: {sorted(missing)}")

    working = frame.copy()
    working["weight"] = working[cutoff_col].map(
        {int(day): float(weight) for day, weight in cutoff_weights.items()}
    )
    if working["weight"].isna().any():
        missing_days = sorted(working.loc[working["weight"].isna(), cutoff_col].unique().tolist())
        raise ValueError(f"No MTD weight registered for cutoff day(s): {missing_days}")
    working["prediction"] = (
        (1.0 - working["weight"]) * pd.to_numeric(working[premonth_col], errors="coerce")
        + working["weight"] * pd.to_numeric(working[mtd_projection_col], errors="coerce")
    )
    working["actual"] = pd.to_numeric(working[actual_col], errors="coerce")
    return {
        "overall": summarize_predictions(working),
        "byCutoff": {
            str(int(day)): summarize_predictions(group)
            for day, group in working.groupby(cutoff_col, sort=True)
        },
        "rows": working.to_dict(orient="records"),
    }


def summarize_predictions(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "actual" not in frame or "prediction" not in frame:
        return _empty_metrics()

    actual = pd.to_numeric(frame["actual"], errors="coerce")
    prediction = pd.to_numeric(frame["prediction"], errors="coerce")
    valid = actual.notna() & prediction.notna()
    total_rows = int(len(frame))
    valid_rows = int(valid.sum())
    if valid_rows == 0:
        metrics = _empty_metrics()
        metrics["rowCount"] = total_rows
        return metrics

    actual_values = actual[valid].astype(float).to_numpy()
    predicted_values = prediction[valid].astype(float).to_numpy()
    errors = predicted_values - actual_values
    denominator = float(np.abs(actual_values).sum())
    wape = float(np.abs(errors).sum() / denominator) if denominator > 0 else None
    bias_percentage = float(errors.sum() / denominator) if denominator > 0 else None
    positive_actual = np.abs(actual_values) > 0
    fold_wapes = np.abs(errors[positive_actual]) / np.abs(actual_values[positive_actual])

    return {
        "wape": wape,
        "accuracy": max(0.0, 1.0 - wape) if wape is not None else None,
        "mae": float(np.mean(np.abs(errors))),
        "signedBias": float(np.mean(errors)),
        "biasPercentage": bias_percentage,
        "foldWapeStandardDeviation": (
            float(np.std(fold_wapes, ddof=0)) if len(fold_wapes) else None
        ),
        "predictionCoverage": float(valid_rows / total_rows) if total_rows else 0.0,
        "foldCount": valid_rows,
        "rowCount": total_rows,
        "actualTotal": float(actual_values.sum()),
        "predictionTotal": float(predicted_values.sum()),
    }


def select_champion(
    candidates: Mapping[str, Mapping[str, Any]],
    *,
    tie_band_wape: float = 0.01,
    complexity: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Apply the governed WAPE/bias/stability/complexity selection rule."""

    eligible = {
        name: metrics
        for name, metrics in candidates.items()
        if metrics.get("wape") is not None and metrics.get("foldCount", 0) > 0
    }
    if not eligible:
        return {"champion": None, "reason": "No eligible candidates.", "eligible": []}

    minimum_wape = min(float(metrics["wape"]) for metrics in eligible.values())
    tied = {
        name: metrics
        for name, metrics in eligible.items()
        if float(metrics["wape"]) <= minimum_wape + tie_band_wape
    }
    complexity_map = dict(MODEL_COMPLEXITY)
    complexity_map.update(complexity or {})
    champion = min(
        tied,
        key=lambda name: (
            _absolute_metric_or_infinity(tied[name], "biasPercentage"),
            _metric_or_infinity(tied[name], "foldWapeStandardDeviation"),
            -float(tied[name].get("predictionCoverage") or 0.0),
            complexity_map.get(name, 99),
            name,
        ),
    )
    return {
        "champion": champion,
        "reason": (
            f"{len(tied)} candidate(s) were within {tie_band_wape:.4f} WAPE of the empirical best; "
            "tie-breaks used absolute bias, stability, coverage, then complexity."
        ),
        "eligible": sorted(eligible),
        "tieSet": sorted(tied),
        "minimumWape": minimum_wape,
    }


def predictions_to_frame(predictions: Sequence[FoldPrediction]) -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in predictions])


def expected_fold_counts(
    observed_months: int,
    contract: BacktestContract | None = None,
) -> dict[str, int]:
    active_contract = contract or BacktestContract()
    counts = {
        str(horizon): max(
            0,
            observed_months - active_contract.minimum_training_months - horizon + 1,
        )
        for horizon in active_contract.horizons
    }
    counts["combined"] = sum(counts.values())
    return counts


def self_test() -> dict[str, Any]:
    contract = BacktestContract()
    months = pd.period_range("2023-01", periods=42, freq="M")
    values = pd.Series(
        [100.0 + 2.0 * index + 8.0 * np.sin(2.0 * np.pi * index / 12.0) for index in range(42)],
        index=months,
    )
    rows = run_series_backtest(
        values,
        model_id="naive_last",
        target="self_test",
        level="total",
        entity="TOTAL",
        contract=contract,
    )
    frame = predictions_to_frame(rows)
    observed = {
        str(horizon): int((frame["horizon"] == horizon).sum())
        for horizon in contract.horizons
    }
    observed["combined"] = int(len(frame))
    expected = expected_fold_counts(42, contract)
    if observed != expected:
        raise AssertionError(f"Fold counts differ: observed={observed}, expected={expected}")
    metrics = summarize_predictions(frame)
    if metrics["foldCount"] != 51 or metrics["wape"] is None:
        raise AssertionError(f"Metric self-test failed: {metrics}")
    return {
        "status": "pass",
        "contractVersion": contract.version,
        "foldCounts": observed,
        "metrics": metrics,
    }


def _working_day_adjusted_seasonal(
    history: Sequence[float],
    *,
    training_months: Sequence[pd.Period],
    target_months: Sequence[pd.Period],
    working_days: Mapping[str, float],
) -> list[float]:
    values = [max(float(value), 0.0) for value in history]
    months = list(training_months)
    predictions: list[float] = []
    for target_month in target_months:
        if len(values) >= 12:
            seasonal_value = values[-12]
            prior_month = target_month - 12
            current_days = float(working_days.get(str(target_month), 0.0) or 0.0)
            prior_days = float(working_days.get(str(prior_month), 0.0) or 0.0)
            ratio = current_days / prior_days if current_days > 0 and prior_days > 0 else 1.0
            prediction = seasonal_value * ratio
        else:
            prediction = values[-1] if values else 0.0
        prediction = max(float(prediction), 0.0)
        predictions.append(prediction)
        values.append(prediction)
        months.append(target_month)
    return predictions


def _empty_metrics() -> dict[str, Any]:
    return {
        "wape": None,
        "accuracy": None,
        "mae": None,
        "signedBias": None,
        "biasPercentage": None,
        "foldWapeStandardDeviation": None,
        "predictionCoverage": 0.0,
        "foldCount": 0,
        "rowCount": 0,
        "actualTotal": 0.0,
        "predictionTotal": 0.0,
    }


def _metric_or_infinity(metrics: Mapping[str, Any], name: str) -> float:
    value = metrics.get(name)
    return float(value) if value is not None else float("inf")


def _absolute_metric_or_infinity(metrics: Mapping[str, Any], name: str) -> float:
    value = metrics.get(name)
    return abs(float(value)) if value is not None else float("inf")
