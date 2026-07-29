from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ForecastDiagnostics:
    model_name: str
    history_months: int
    confidence: str
    mae: float | None
    wape: float | None
    bias: float | None
    selection_basis: str | None = None
    preprocessing: str = "raw"
    adjusted_months: int = 0


@dataclass(frozen=True)
class ForecastModelSpec:
    name: str
    min_history: int
    family: str


def prepare_forecast_rows(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    part_value: str,
) -> pd.DataFrame:
    working = df.copy()
    working = working.assign(
        __date=date_series.loc[working.index],
        __part=working[part_col].fillna("").astype(str),
        __qty=pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0),
    )
    working = working[working["__part"] == part_value].copy()
    working = working[working["__date"].notna()]
    if working.empty:
        return working

    latest_date = working["__date"].max()
    month_end = latest_date + pd.offsets.MonthEnd(0)
    if latest_date.normalize() < month_end.normalize() and latest_date.day <= 27:
        latest_month = latest_date.to_period("M").to_timestamp()
        working = working[working["__date"].dt.to_period("M").dt.to_timestamp() != latest_month]

    return working


def build_monthly_part_series(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    part_value: str,
) -> pd.DataFrame:
    working = prepare_forecast_rows(df, part_col, qty_col, date_series, part_value)
    if working.empty:
        return pd.DataFrame(columns=["month", "actual"])

    working["month"] = working["__date"].dt.to_period("M").dt.to_timestamp()
    grouped = working.groupby("month", dropna=True)["__qty"].sum().sort_index()
    month_index = pd.date_range(grouped.index.min(), grouped.index.max(), freq="MS")
    series = grouped.reindex(month_index, fill_value=0.0)
    return pd.DataFrame({"month": series.index, "actual": series.values})


MODEL_SPECS = [
    ForecastModelSpec(name="naive_last", min_history=2, family="baseline"),
    ForecastModelSpec(name="mean", min_history=2, family="baseline"),
    ForecastModelSpec(name="weighted_moving_average", min_history=3, family="recent"),
    ForecastModelSpec(name="trailing_12_mean", min_history=12, family="recent"),
    ForecastModelSpec(name="trend_adjusted_moving_average", min_history=6, family="trend"),
    ForecastModelSpec(name="damped_trend", min_history=6, family="trend"),
    ForecastModelSpec(name="log_linear_trend", min_history=6, family="trend"),
    ForecastModelSpec(name="seasonal_naive", min_history=18, family="seasonal"),
    ForecastModelSpec(name="seasonal_mean", min_history=18, family="seasonal"),
    ForecastModelSpec(name="ets_additive", min_history=24, family="seasonal"),
    ForecastModelSpec(name="croston_sba", min_history=8, family="intermittent"),
]


def candidate_models(history: list[float], use_seasonality: bool = True) -> list[str]:
    values = [max(float(value), 0.0) for value in history]
    zero_share = _history_zero_share(values)
    models: list[str] = []

    for spec in MODEL_SPECS:
        if len(values) < spec.min_history:
            continue
        if spec.family == "seasonal" and not use_seasonality:
            continue
        if spec.family == "seasonal" and zero_share >= 0.45:
            continue
        if spec.family == "intermittent" and zero_share < 0.2:
            continue
        models.append(spec.name)

    if not models:
        return ["mean"]
    return models


def clean_training_history(history: list[float]) -> tuple[list[float], int]:
    cleaned: list[float] = []
    adjusted_points = 0

    for idx, raw_value in enumerate(history):
        value = max(float(raw_value), 0.0)
        trailing = cleaned[max(0, idx - 6):idx]
        if len(trailing) < 3:
            cleaned.append(value)
            continue

        baseline = float(pd.Series(trailing).median())
        mad = float((pd.Series(trailing) - baseline).abs().median())
        spread = max(mad * 3.0, baseline * 0.7, 1.0)
        lower = max(0.0, baseline - spread)
        upper = baseline + spread

        if value < lower:
            value = lower + (value - lower) * 0.4
            adjusted_points += 1
        elif value > upper:
            value = upper + (value - upper) * 0.4
            adjusted_points += 1

        cleaned.append(max(0.0, value))

    return cleaned, adjusted_points


def preprocess_history(history: list[float], preprocessing: str) -> tuple[list[float], int]:
    if preprocessing == "cleaned":
        return clean_training_history(history)
    return [max(float(value), 0.0) for value in history], 0


def choose_model(history: list[float]) -> str:
    best_model, _, _ = select_best_model(history)
    return best_model


def forecast_history(history: list[float], horizon: int, model_name: str | None = None) -> list[float]:
    chosen = model_name or choose_model(history)
    values = [max(float(value), 0.0) for value in history]
    forecasts: list[float] = []

    if not values:
        return [0.0] * horizon
    if chosen == "ets_additive":
        return _ets_additive_forecast(values, horizon)

    for _ in range(horizon):
        prediction = _forecast_next_value(values, chosen)
        prediction = max(float(prediction), 0.0)
        forecasts.append(prediction)
        values.append(prediction)

    return forecasts


def backtest_history(
    history: list[float],
    model_name: str,
    preprocessing: str = "raw",
) -> ForecastDiagnostics:
    if len(history) < 5:
        return ForecastDiagnostics(
            model_name=model_name,
            history_months=len(history),
            confidence="Low",
            mae=None,
            wape=None,
            bias=None,
            selection_basis="Not enough history for rolling backtest.",
            preprocessing=preprocessing,
        )

    mae, wape, bias = _rolling_backtest(history, model_name, preprocessing=preprocessing)
    if mae is None:
        return ForecastDiagnostics(
            model_name=model_name,
            history_months=len(history),
            confidence="Low",
            mae=None,
            wape=None,
            bias=None,
            selection_basis="Rolling backtest did not produce enough evaluation points.",
            preprocessing=preprocessing,
        )

    confidence = _score_confidence(history, wape=wape, bias=bias)
    _, adjusted_months = preprocess_history(history, preprocessing)

    return ForecastDiagnostics(
        model_name=model_name,
        history_months=len(history),
        confidence=confidence,
        mae=float(mae),
        wape=float(wape) if wape is not None else None,
        bias=float(bias) if bias is not None else None,
        selection_basis="Single-model rolling backtest.",
        preprocessing=preprocessing,
        adjusted_months=adjusted_months,
    )


def select_best_model(
    history: list[float],
    use_seasonality: bool = True,
) -> tuple[str, list[dict[str, Any]], ForecastDiagnostics]:
    models = candidate_models(history, use_seasonality=use_seasonality)
    scores: list[dict[str, Any]] = []
    _, adjusted_points = clean_training_history(history)
    preprocessing_modes = ["raw"]
    if adjusted_points > 0:
        preprocessing_modes.append("cleaned")

    for preprocessing in preprocessing_modes:
        _, preprocessing_adjusted = preprocess_history(history, preprocessing)
        for model_name in models:
            mae, wape, bias = _rolling_backtest(history, model_name, preprocessing=preprocessing)
            scores.append(
                {
                    "model": model_name,
                    "label": f"{model_name} ({preprocessing})",
                    "preprocessing": preprocessing,
                    "adjustedMonths": preprocessing_adjusted,
                    "mae": float(mae) if mae is not None else None,
                    "wape": float(wape) if wape is not None else None,
                    "bias": float(bias) if bias is not None else None,
                }
            )

    ranked = sorted(
        scores,
        key=lambda item: (
            float("inf") if item["wape"] is None else item["wape"],
            float("inf") if item["mae"] is None else item["mae"],
            abs(item["bias"]) if item["bias"] is not None else float("inf"),
        ),
    )
    best = ranked[0]
    confidence = _score_confidence(history, wape=best["wape"], bias=best["bias"])
    if len(preprocessing_modes) > 1:
        basis = (
            f"Selected by rolling backtest across {len(models)} baselines under raw and anomaly-softened histories. "
            f"Chosen path: {best['preprocessing']}. Candidate anomaly adjustments were detected on {adjusted_points} month(s)."
        )
    else:
        basis = f"Selected by rolling backtest across {len(models)} candidate baselines."
    diagnostics = ForecastDiagnostics(
        model_name=best["model"],
        history_months=len(history),
        confidence=confidence,
        mae=best["mae"],
        wape=best["wape"],
        bias=best["bias"],
        selection_basis=basis,
        preprocessing=best["preprocessing"],
        adjusted_months=best["adjustedMonths"],
    )
    return best["model"], ranked, diagnostics


def forecast_band(
    history: list[float],
    forecast_values: list[float],
    diagnostics: ForecastDiagnostics,
) -> list[dict[str, float]]:
    if diagnostics.mae is not None:
        base_error = diagnostics.mae
    else:
        series = pd.Series(history, dtype="float64")
        base_error = float(series.diff().abs().dropna().mean()) if len(series) > 1 else float(series.mean() * 0.2)

    bands: list[dict[str, float]] = []
    for step, value in enumerate(forecast_values, start=1):
        spread = max(base_error, value * 0.12) * (step ** 0.5)
        lower = max(0.0, value - 1.28 * spread)
        upper = value + 1.28 * spread
        bands.append({
            "forecast": float(value),
            "lower": float(lower),
            "upper": float(upper),
        })
    return bands


def build_forecast_narrative(
    history: list[float],
    forecast_values: list[float],
    diagnostics: ForecastDiagnostics,
    regime: dict[str, Any] | None = None,
    forecast_risk: str | None = None,
) -> list[str]:
    if not history:
        return ["No usable history was found for the selected part."]

    notes: list[str] = []
    last_actual = history[-1]
    next_forecast = forecast_values[0] if forecast_values else 0.0
    delta = next_forecast - last_actual
    if last_actual > 0:
        pct = (delta / last_actual) * 100
        direction = "above" if delta >= 0 else "below"
        notes.append(f"Next month is projected {abs(pct):.1f}% {direction} the latest actual month.")
    else:
        notes.append("Latest actual month is zero, so the forecast is anchored to the recent average pattern.")

    if len(history) >= 6:
        recent_3 = sum(history[-3:]) / min(3, len(history))
        prior_window = history[-6:-3] if len(history) >= 6 else history[:-3]
        if prior_window:
            prior_3 = sum(prior_window) / len(prior_window)
            if prior_3 > 0:
                trend_pct = ((recent_3 - prior_3) / prior_3) * 100
                notes.append(f"Recent 3-month demand is running {trend_pct:+.1f}% versus the prior 3-month window.")

    if diagnostics.model_name == "seasonal_naive":
        notes.append("The baseline uses last year's same-month pattern because the series is long enough to expose seasonality.")
    elif diagnostics.model_name == "seasonal_mean":
        notes.append("The baseline averages the same calendar month from prior years, which is useful when seasonality exists but single-month repeats are noisy.")
    elif diagnostics.model_name == "log_linear_trend":
        notes.append("The baseline fits a log-space trend over recent months, which helps when demand is decaying or ramping non-linearly.")
    elif diagnostics.model_name == "damped_trend":
        notes.append("The baseline carries forward the recent trend, but damps it so the forecast does not overreact to one sharp month.")
    elif diagnostics.model_name == "trend_adjusted_moving_average":
        notes.append("The baseline blends recent demand with the short-term slope, so it reacts faster to acceleration or deceleration.")
    elif diagnostics.model_name == "croston_sba":
        notes.append("The baseline is designed for intermittent demand, separating demand size from demand timing and correcting for over-forecast bias.")
    elif diagnostics.model_name == "trailing_12_mean":
        notes.append("The baseline uses the trailing 12-month average to stabilize parts with repeatable annual demand but noisy recent months.")
    elif diagnostics.model_name == "naive_last":
        notes.append("The baseline carries the latest month forward because the short history favors a very low-complexity assumption.")
    elif diagnostics.model_name == "weighted_moving_average":
        notes.append("The baseline leans on the latest three months, with more weight on the most recent month.")
    else:
        notes.append("History is still sparse, so the forecast uses a low-complexity average baseline.")

    if diagnostics.preprocessing == "cleaned" and diagnostics.adjusted_months > 0:
        notes.append(f"Anomaly softening was applied to {diagnostics.adjusted_months} month(s) because raw spikes or drops hurt backtest stability.")

    if regime and regime.get("code") in {"structural_drop", "structural_ramp"}:
        notes.append(f"The current series shape looks like a {regime['label'].lower()}, so the forecast should be treated as a short-horizon baseline.")
    elif forecast_risk == "High":
        notes.append("Recent behavior is unstable enough that planner review matters more than the point forecast itself.")

    notes.append(f"Model confidence is {diagnostics.confidence.lower()} based on history depth and backtest stability.")
    return notes[:4]


def build_watchlist(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    limit: int = 8,
) -> list[dict[str, Any]]:
    working = df.copy()
    working = working.assign(
        __date=date_series.loc[working.index],
        __part=working[part_col].fillna("").astype(str),
        __qty=pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0),
    )
    working = working[working["__date"].notna()]
    if working.empty:
        return []

    working["month"] = working["__date"].dt.to_period("M").dt.to_timestamp()
    ranked_parts = (
        working.groupby("__part", dropna=True)["__qty"]
        .sum()
        .sort_values(ascending=False)
        .head(30)
        .index
        .tolist()
    )

    watchlist: list[dict[str, Any]] = []
    for part_value in ranked_parts:
        series_df = build_monthly_part_series(working, "__part", "__qty", working["__date"], part_value)
        history = series_df["actual"].astype(float).tolist()
        if len(history) < 4:
            continue
        model_name, _, diagnostics = select_best_model(history)
        forecast_input, _ = preprocess_history(history, diagnostics.preprocessing)
        next_month = forecast_history(forecast_input, 1, model_name=model_name)[0]
        last_month = history[-1]
        delta_pct = ((next_month - last_month) / last_month * 100) if last_month else None
        watchlist.append(
            {
                "part": part_value,
                "latestActual": float(last_month),
                "nextForecast": float(next_month),
                "deltaPct": float(delta_pct) if delta_pct is not None else None,
                "confidence": diagnostics.confidence,
            }
        )

    watchlist.sort(
        key=lambda item: (
            0 if item["deltaPct"] is None else abs(item["deltaPct"]),
            item["nextForecast"],
        ),
        reverse=True,
    )
    return watchlist[:limit]


def classify_forecast_tier(
    diagnostics: ForecastDiagnostics,
    regime: dict[str, Any],
    forecast_risk: str,
    history: list[float],
) -> dict[str, Any]:
    wape = diagnostics.wape
    bias_abs = abs(diagnostics.bias) if diagnostics.bias is not None else None
    history_months = len(history)
    volatility = regime.get("volatility")

    if (
        history_months < 6
        or forecast_risk == "High"
        or regime["code"] in {"structural_drop", "structural_ramp", "sparse_history"}
        or wape is None
        or wape > 0.45
    ):
        return {
            "label": "Do not auto-plan",
            "code": "do_not_auto_plan",
            "priority": 3,
            "reason": "Series is structurally unstable, sparse, or too inaccurate for automatic planning.",
        }

    if (
        history_months >= 12
        and wape <= 0.22
        and (bias_abs is None or bias_abs <= 0.18)
        and regime["code"] == "stable"
        and forecast_risk == "Low"
        and (volatility is None or volatility <= 0.85)
    ):
        return {
            "label": "Planner-ready",
            "code": "planner_ready",
            "priority": 1,
            "reason": "Backtest error, bias, and regime shape are stable enough for baseline planning use.",
        }

    return {
        "label": "Needs planner review",
        "code": "needs_review",
        "priority": 2,
        "reason": "Forecast is directionally usable, but planner review is still needed before committing demand.",
    }


def forecast_reliability_score(
    diagnostics: ForecastDiagnostics,
    regime: dict[str, Any],
    forecast_risk: str,
    history: list[float],
) -> float:
    history_score = min(len(history) / 18.0, 1.0) * 22.0
    wape_score = 0.0 if diagnostics.wape is None else max(0.0, 1.0 - min(diagnostics.wape, 1.0)) * 38.0
    bias_abs = abs(diagnostics.bias) if diagnostics.bias is not None else 1.0
    bias_score = max(0.0, 1.0 - min(bias_abs, 1.0)) * 14.0
    confidence_score = {"High": 14.0, "Medium": 8.0, "Low": 2.0}.get(diagnostics.confidence, 0.0)
    regime_penalty = {
        "stable": 0.0,
        "declining": 4.0,
        "accelerating": 4.0,
        "volatile": 7.0,
        "structural_drop": 18.0,
        "structural_ramp": 16.0,
        "sparse_history": 15.0,
    }.get(regime["code"], 6.0)
    risk_penalty = {"Low": 0.0, "Medium": 7.0, "High": 18.0}.get(forecast_risk, 10.0)
    score = history_score + wape_score + bias_score + confidence_score - regime_penalty - risk_penalty
    return round(max(0.0, min(score, 100.0)), 1)


def build_forecast_portfolio(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    part_description_col: str | None = None,
    scan_limit: int = 60,
    top_n: int = 18,
) -> dict[str, Any]:
    working = df.copy()
    working = working.assign(
        __date=date_series.loc[working.index],
        __part=working[part_col].fillna("").astype(str),
        __qty=pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0),
    )
    working = working[working["__date"].notna()]
    if working.empty:
        return {
            "summary": {
                "scannedParts": 0,
                "plannerReadyCount": 0,
                "reviewCount": 0,
                "doNotAutoPlanCount": 0,
                "plannerReadyShare": 0.0,
            },
            "records": [],
            "recommendedPart": None,
        }

    part_totals = (
        working.groupby("__part", dropna=True)["__qty"]
        .sum()
        .sort_values(ascending=False)
    )
    ranked_parts = part_totals.head(scan_limit).index.tolist()
    total_ranked_qty = float(part_totals.head(scan_limit).sum()) or 0.0

    records: list[dict[str, Any]] = []
    for part_value in ranked_parts:
        series_df = build_monthly_part_series(working, "__part", "__qty", working["__date"], part_value)
        history = series_df["actual"].astype(float).tolist()
        if len(history) < 4:
            continue

        model_name, _, diagnostics = select_best_model(history)
        forecast_input, _ = preprocess_history(history, diagnostics.preprocessing)
        next_forecast = forecast_history(forecast_input, 1, model_name=model_name)[0]
        anomalies = detect_series_anomalies(series_df)
        regime = classify_series_regime(history)
        forecast_risk = _forecast_risk_label(diagnostics, regime, anomalies)
        tier = classify_forecast_tier(diagnostics, regime, forecast_risk, history)
        reliability_score = forecast_reliability_score(diagnostics, regime, forecast_risk, history)
        latest_actual = float(history[-1]) if history else 0.0
        delta_pct = _safe_pct(next_forecast - latest_actual, latest_actual)
        total_qty = float(part_totals.get(part_value, 0.0))
        qty_share = (total_qty / total_ranked_qty) if total_ranked_qty else 0.0

        description = None
        if part_description_col and part_description_col in working.columns:
            desc_series = (
                working.loc[working["__part"] == part_value, part_description_col]
                .dropna()
                .astype(str)
            )
            if not desc_series.empty:
                description = desc_series.mode().iloc[0]

        records.append(
            {
                "part": str(part_value),
                "partDescription": description,
                "historyMonths": len(history),
                "latestActual": latest_actual,
                "nextForecast": float(next_forecast),
                "deltaPct": float(delta_pct) if delta_pct is not None else None,
                "confidence": diagnostics.confidence,
                "forecastRisk": forecast_risk,
                "regime": regime["label"],
                "regimeCode": regime["code"],
                "wape": diagnostics.wape,
                "bias": diagnostics.bias,
                "modelName": diagnostics.model_name,
                "preprocessing": diagnostics.preprocessing,
                "reliabilityTier": tier["label"],
                "reliabilityCode": tier["code"],
                "reliabilityPriority": tier["priority"],
                "reliabilityReason": tier["reason"],
                "reliabilityScore": reliability_score,
                "totalQuantity": total_qty,
                "quantityShare": float(qty_share),
            }
        )

    records.sort(
        key=lambda item: (
            item["reliabilityPriority"],
            -item["reliabilityScore"],
            -item["totalQuantity"],
        )
    )
    recommended = next(
        (
            item["part"]
            for item in records
            if item["reliabilityCode"] == "planner_ready"
        ),
        None,
    )
    if not recommended:
        recommended = next(
            (
                item["part"]
                for item in records
                if item["reliabilityCode"] == "needs_review"
            ),
            records[0]["part"] if records else None,
        )

    planner_ready_qty = sum(item["totalQuantity"] for item in records if item["reliabilityCode"] == "planner_ready")

    return {
        "summary": {
            "scannedParts": len(records),
            "plannerReadyCount": sum(1 for item in records if item["reliabilityCode"] == "planner_ready"),
            "reviewCount": sum(1 for item in records if item["reliabilityCode"] == "needs_review"),
            "doNotAutoPlanCount": sum(1 for item in records if item["reliabilityCode"] == "do_not_auto_plan"),
            "plannerReadyShare": float(planner_ready_qty / total_ranked_qty) if total_ranked_qty else 0.0,
        },
        "records": records[:top_n],
        "recommendedPart": recommended,
    }


def classify_series_regime(history: list[float]) -> dict[str, Any]:
    values = [max(float(value), 0.0) for value in history]
    if len(values) < 4:
        return {
            "label": "Sparse history",
            "code": "sparse_history",
            "severity": "Medium",
            "structural": False,
            "latestChangePct": None,
            "trendShiftPct": None,
            "volatility": None,
        }

    series = pd.Series(values, dtype="float64")
    latest = values[-1]
    previous = values[-2]
    recent_window = values[-3:]
    recent_avg = float(pd.Series(recent_window).mean())
    prior_window = values[-6:-3] if len(values) >= 6 else values[:-3]
    prior_avg = float(pd.Series(prior_window).mean()) if prior_window else 0.0
    overall_median = float(series.median()) if len(series) else 0.0
    latest_change_pct = _safe_pct(latest - previous, previous)
    trend_shift_pct = _safe_pct(recent_avg - prior_avg, prior_avg) if prior_avg > 0 else None
    volatility = float(series.std(ddof=0) / series.mean()) if series.mean() > 0 else None

    if (
        prior_avg > 0
        and recent_avg <= prior_avg * 0.45
        and latest <= prior_avg * 0.25
        and previous <= prior_avg * 0.45
    ):
        return {
            "label": "Structural drop",
            "code": "structural_drop",
            "severity": "High",
            "structural": True,
            "latestChangePct": latest_change_pct,
            "trendShiftPct": trend_shift_pct,
            "volatility": volatility,
        }

    if (
        prior_avg > 0
        and recent_avg >= prior_avg * 1.8
        and latest >= max(prior_avg * 1.6, overall_median * 1.5)
    ):
        return {
            "label": "Structural ramp",
            "code": "structural_ramp",
            "severity": "High",
            "structural": True,
            "latestChangePct": latest_change_pct,
            "trendShiftPct": trend_shift_pct,
            "volatility": volatility,
        }

    if prior_avg > 0 and recent_avg <= prior_avg * 0.7:
        return {
            "label": "Declining",
            "code": "declining",
            "severity": "Medium",
            "structural": False,
            "latestChangePct": latest_change_pct,
            "trendShiftPct": trend_shift_pct,
            "volatility": volatility,
        }

    if prior_avg > 0 and recent_avg >= prior_avg * 1.35:
        return {
            "label": "Accelerating",
            "code": "accelerating",
            "severity": "Medium",
            "structural": False,
            "latestChangePct": latest_change_pct,
            "trendShiftPct": trend_shift_pct,
            "volatility": volatility,
        }

    if volatility is not None and volatility >= 0.95:
        return {
            "label": "Volatile",
            "code": "volatile",
            "severity": "Medium",
            "structural": False,
            "latestChangePct": latest_change_pct,
            "trendShiftPct": trend_shift_pct,
            "volatility": volatility,
        }

    return {
        "label": "Stable",
        "code": "stable",
        "severity": "Low",
        "structural": False,
        "latestChangePct": latest_change_pct,
        "trendShiftPct": trend_shift_pct,
        "volatility": volatility,
    }


def build_anomaly_center(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    brand_col: str | None = None,
    model_col: str | None = None,
    part_description_col: str | None = None,
    wholesale_df: pd.DataFrame | None = None,
    wholesale_long_df: pd.DataFrame | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    working = df.copy()
    working = working.assign(
        __date=date_series.loc[working.index],
        __part=working[part_col].fillna("").astype(str),
        __qty=pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0),
    )
    working = working[working["__date"].notna()]
    if working.empty:
        return {
            "summary": {
                "scannedParts": 0,
                "surfacedAlerts": 0,
                "structuralBreaks": 0,
                "highRiskForecasts": 0,
                "lowConfidenceForecasts": 0,
            },
            "regimeBreakdown": [],
            "records": [],
        }

    wholesale_long = wholesale_long_df.copy() if wholesale_long_df is not None else None
    if wholesale_long is not None and not wholesale_long.empty:
        required_columns = {"model", "month", "wholesale"}
        if not required_columns.issubset(wholesale_long.columns):
            wholesale_long = None
        else:
            wholesale_long["month"] = pd.to_datetime(wholesale_long["month"], errors="coerce")
            wholesale_long["wholesale"] = pd.to_numeric(wholesale_long["wholesale"], errors="coerce")
            wholesale_long = wholesale_long.dropna(subset=["month", "wholesale"])
    if wholesale_long is None and wholesale_df is not None and model_col and model_col in df.columns:
        date_values = pd.Series(date_series).dropna()
        if not date_values.empty:
            wholesale_long = prepare_wholesale_long(wholesale_df, start_year=int(date_values.min().year))

    ranked_parts = (
        working.groupby("__part", dropna=True)["__qty"]
        .sum()
        .sort_values(ascending=False)
        .head(60)
        .index
        .tolist()
    )

    records: list[dict[str, Any]] = []
    for part_value in ranked_parts:
        part_working = working[working["__part"].astype(str) == str(part_value)].copy()
        if part_working.empty:
            continue
        series_df = build_monthly_part_series(working, "__part", "__qty", working["__date"], part_value)
        history = series_df["actual"].astype(float).tolist()
        if len(history) < 4:
            continue

        model_name, _, diagnostics = select_best_model(history)
        forecast_input, _ = preprocess_history(history, diagnostics.preprocessing)
        next_forecast = forecast_history(forecast_input, 1, model_name=model_name)[0]
        anomalies = detect_series_anomalies(series_df, limit=2)
        change_analysis = explain_latest_change(
            working,
            part_col="__part",
            qty_col="__qty",
            date_series=working["__date"],
            part_value=part_value,
            brand_col=brand_col,
            model_col=model_col,
        )
        regime = classify_series_regime(history)
        wholesale_signal = None
        if wholesale_long is not None and model_col:
            wholesale_signal = build_wholesale_signal_model(
                part_working=part_working,
                model_col=model_col,
                wholesale_long=wholesale_long,
            )
        score = _anomaly_priority_score(history, diagnostics, anomalies, regime)
        forecast_risk = _forecast_risk_label(diagnostics, regime, anomalies, wholesale_signal)

        description = None
        if part_description_col and part_description_col in working.columns:
            desc_series = (
                working.loc[working["__part"] == part_value, part_description_col]
                .dropna()
                .astype(str)
            )
            if not desc_series.empty:
                description = desc_series.mode().iloc[0]

        latest_actual = float(history[-1])
        previous_actual = float(history[-2]) if len(history) >= 2 else 0.0
        delta_pct = _safe_pct(latest_actual - previous_actual, previous_actual)
        recent_avg = float(pd.Series(history[-3:]).mean()) if history else 0.0
        forecast_delta_pct = _safe_pct(next_forecast - latest_actual, latest_actual)

        evidence = _build_anomaly_evidence(
            history=history,
            diagnostics=diagnostics,
            anomalies=anomalies,
            change_analysis=change_analysis,
            regime=regime,
            next_forecast=next_forecast,
            wholesale_signal=wholesale_signal,
        )
        if score < 0.32 and forecast_risk == "Low" and regime["label"] == "Stable":
            continue

        records.append(
            {
                "part": part_value,
                "partDescription": description,
                "historyMonths": len(history),
                "latestMonth": series_df["month"].iloc[-1].strftime("%Y-%m"),
                "previousMonth": series_df["month"].iloc[-2].strftime("%Y-%m") if len(series_df) >= 2 else None,
                "latestActual": latest_actual,
                "previousActual": previous_actual,
                "deltaPct": float(delta_pct) if delta_pct is not None else None,
                "recent3MonthAverage": recent_avg,
                "nextForecast": float(next_forecast),
                "forecastDeltaPct": float(forecast_delta_pct) if forecast_delta_pct is not None else None,
                "anomalyScore": round(score, 3),
                "regime": regime["label"],
                "regimeCode": regime["code"],
                "regimeSeverity": regime["severity"],
                "forecastRisk": forecast_risk,
                "confidence": diagnostics.confidence,
                "wape": diagnostics.wape,
                "bias": diagnostics.bias,
                "modelName": diagnostics.model_name,
                "preprocessing": diagnostics.preprocessing,
                "adjustedMonths": diagnostics.adjusted_months,
                "evidence": evidence,
                "anomalies": anomalies,
                "wholesaleSignal": wholesale_signal,
                "brandDrivers": change_analysis["brandDrivers"][:3] if change_analysis else [],
                "modelDrivers": change_analysis["modelDrivers"][:3] if change_analysis else [],
            }
        )

    records.sort(
        key=lambda item: (
            item["anomalyScore"],
            0 if item["forecastRisk"] == "High" else 1 if item["forecastRisk"] == "Medium" else 2,
            item["latestActual"],
        ),
        reverse=True,
    )
    surfaced = records[:limit]

    regime_breakdown = (
        pd.Series([item["regime"] for item in surfaced], dtype="object")
        .value_counts()
        .reset_index()
        .to_dict("records")
        if surfaced
        else []
    )

    return {
        "summary": {
            "scannedParts": len(records),
            "surfacedAlerts": len(surfaced),
            "structuralBreaks": sum(1 for item in records if item["regimeCode"] in {"structural_drop", "structural_ramp"}),
            "highRiskForecasts": sum(1 for item in records if item["forecastRisk"] == "High"),
            "lowConfidenceForecasts": sum(1 for item in records if item["confidence"] == "Low"),
        },
        "regimeBreakdown": [
            {"label": item["index"], "count": int(item["count"])}
            for item in regime_breakdown
        ],
        "records": surfaced,
    }


def _anomaly_priority_score(
    history: list[float],
    diagnostics: ForecastDiagnostics,
    anomalies: list[dict[str, Any]],
    regime: dict[str, Any],
) -> float:
    latest = history[-1] if history else 0.0
    previous = history[-2] if len(history) >= 2 else 0.0
    latest_change = min(abs(_safe_pct(latest - previous, previous) or 0.0) / 100, 2.5)
    wape_component = min(diagnostics.wape if diagnostics.wape is not None else 0.0, 1.5)
    anomaly_component = 0.35 if any(item["severity"] == "High" for item in anomalies) else 0.18 if anomalies else 0.0
    regime_component = {
        "structural_drop": 0.45,
        "structural_ramp": 0.4,
        "declining": 0.22,
        "accelerating": 0.2,
        "volatile": 0.18,
        "sparse_history": 0.16,
        "stable": 0.0,
    }.get(regime["code"], 0.0)
    confidence_component = 0.2 if diagnostics.confidence == "Low" else 0.08 if diagnostics.confidence == "Medium" else 0.0
    return float(latest_change * 0.45 + wape_component * 0.35 + anomaly_component + regime_component + confidence_component)


def _forecast_risk_label(
    diagnostics: ForecastDiagnostics,
    regime: dict[str, Any],
    anomalies: list[dict[str, Any]],
    wholesale_signal: dict[str, Any] | None = None,
) -> str:
    bias_abs = abs(diagnostics.bias) if diagnostics.bias is not None else None
    if (
        diagnostics.confidence == "Low"
        or (diagnostics.wape is not None and diagnostics.wape >= 0.55)
        or regime["code"] in {"structural_drop", "structural_ramp"}
        or (wholesale_signal and wholesale_signal.get("unexplainedResidualPct") is not None and abs(wholesale_signal["unexplainedResidualPct"]) >= 45)
    ):
        return "High"
    if (
        not anomalies
        and regime["code"] == "stable"
        and diagnostics.wape is not None
        and diagnostics.wape <= 0.22
        and (bias_abs is None or bias_abs <= 0.2)
    ):
        return "Low"
    if (
        anomalies
        or regime["code"] in {"declining", "accelerating", "volatile"}
        or (diagnostics.wape is not None and diagnostics.wape > 0.22)
        or (bias_abs is not None and bias_abs > 0.2)
    ):
        return "Medium"
    return "Low"


def _build_anomaly_evidence(
    history: list[float],
    diagnostics: ForecastDiagnostics,
    anomalies: list[dict[str, Any]],
    change_analysis: dict[str, Any] | None,
    regime: dict[str, Any],
    next_forecast: float,
    wholesale_signal: dict[str, Any] | None = None,
) -> list[str]:
    evidence = [f"Regime classified as {regime['label'].lower()} based on the latest six-month shape."]
    if change_analysis and change_analysis.get("deltaPct") is not None:
        evidence.append(
            f"Latest month moved {change_analysis['deltaPct']:+.1f}% versus the prior month."
        )
    elif len(history) >= 2:
        evidence.append(
            f"Latest month moved by {history[-1] - history[-2]:+,.0f} units versus the prior month."
        )

    recent_avg = float(pd.Series(history[-3:]).mean()) if history else 0.0
    if recent_avg > 0 and history:
        evidence.append(f"Latest actual month closed at {history[-1] / recent_avg * 100:.0f}% of the recent 3-month average.")

    if wholesale_signal:
        if wholesale_signal.get("modelWape") is not None:
            evidence.append(
                f"Wholesale-linked model strength is {str(wholesale_signal['relationshipStrength']).lower()} with WAPE {(wholesale_signal['modelWape'] * 100):.1f}%."
            )
        if wholesale_signal.get("wholesaleDeltaPct") is not None:
            evidence.append(
                f"Wholesale exposure moved {wholesale_signal['wholesaleDeltaPct']:+.1f}% in the latest month."
            )
        if wholesale_signal.get("unexplainedResidualPct") is not None and abs(wholesale_signal["unexplainedResidualPct"]) >= 20:
            evidence.append(
                f"After accounting for wholesale and recent lags, residual demand is still {wholesale_signal['unexplainedResidualPct']:+.1f}% versus the model expectation."
            )

    if anomalies:
        top_anomaly = anomalies[0]
        if top_anomaly["deltaPct"] is not None:
            evidence.append(
                f"Top anomaly month {top_anomaly['month']} deviated {top_anomaly['deltaPct']:+.1f}% versus its rolling baseline."
            )

    if diagnostics.wape is not None:
        evidence.append(f"Backtest WAPE is {(diagnostics.wape * 100):.1f}%, so forecast reliability is {diagnostics.confidence.lower()}.")

    forecast_delta_pct = _safe_pct(next_forecast - (history[-1] if history else 0.0), history[-1] if history else 0.0)
    if forecast_delta_pct is not None:
        evidence.append(f"Baseline forecast points to {forecast_delta_pct:+.1f}% versus the latest actual month.")

    return evidence[:5]


def _safe_pct(delta: float, base: float) -> float | None:
    if not base:
        return None
    return (delta / base) * 100


def prepare_wholesale_long(wholesale_df: pd.DataFrame, start_year: int) -> pd.DataFrame:
    month_map = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }
    working = wholesale_df.copy()
    brand_col = next((col for col in working.columns if str(col).strip().lower() == "brand"), None)
    model_col = next((col for col in working.columns if str(col).strip().lower() == "model"), None)
    if not brand_col or not model_col:
        return pd.DataFrame(columns=["brand", "model", "month", "wholesale"])

    working[brand_col] = working[brand_col].ffill()
    records: list[dict[str, Any]] = []
    pattern = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?: \((\d+)\))?$")
    for column in working.columns:
        match = pattern.match(str(column).strip())
        if not match:
            continue
        month_name = match.group(1)
        group_index = int(match.group(2) or "1")
        year = start_year + group_index - 1
        month_value = pd.Timestamp(year=year, month=month_map[month_name], day=1)
        subset = working[[brand_col, model_col, column]].copy()
        subset.columns = ["brand", "model", "wholesale"]
        subset["month"] = month_value
        subset["brand"] = subset["brand"].fillna("").astype(str).str.strip()
        subset["model"] = subset["model"].fillna("").astype(str).str.strip()
        subset["wholesale"] = pd.to_numeric(subset["wholesale"], errors="coerce")
        subset = subset[subset["model"] != ""]
        subset = subset[subset["wholesale"].notna()]
        records.extend(subset.to_dict("records"))

    if not records:
        return pd.DataFrame(columns=["brand", "model", "month", "wholesale"])
    result = pd.DataFrame(records)
    result["month"] = pd.to_datetime(result["month"])
    result["wholesale"] = pd.to_numeric(result["wholesale"], errors="coerce")
    return result


def build_wholesale_signal_model(
    part_working: pd.DataFrame,
    model_col: str,
    wholesale_long: pd.DataFrame,
) -> dict[str, Any] | None:
    if model_col not in part_working.columns or wholesale_long.empty:
        return None

    subset = part_working.copy()
    subset["month"] = subset["__date"].dt.to_period("M").dt.to_timestamp()
    grouped = (
        subset.groupby(["month", model_col], dropna=True)["__qty"]
        .sum()
        .reset_index()
    )
    if grouped.empty:
        return None

    grouped["__model_key"] = _normalize_model_key(grouped[model_col])
    wholesale_working = wholesale_long.copy()
    wholesale_working["__model_key"] = _normalize_model_key(wholesale_working["model"])
    merged = grouped.merge(
        wholesale_working,
        how="left",
        on=["month", "__model_key"],
    )
    merged["wholesale"] = pd.to_numeric(merged["wholesale"], errors="coerce")
    merged = merged[merged["wholesale"].notna()].copy()
    if merged.empty:
        return None

    merged["month_total"] = merged.groupby("month")["__qty"].transform("sum")
    merged["weight"] = np.where(merged["month_total"] > 0, merged["__qty"] / merged["month_total"], 0.0)
    monthly = (
        merged.assign(weighted_wholesale=merged["wholesale"] * merged["weight"])
        .groupby("month", dropna=True)
        .agg(actual=("month_total", "first"), wholesale_signal=("weighted_wholesale", "sum"))
        .reset_index()
        .sort_values("month")
    )
    if len(monthly) < 7:
        return None

    monthly["lag1"] = monthly["actual"].shift(1)
    monthly["lag2"] = monthly["actual"].shift(2)
    monthly["rolling3"] = monthly["actual"].shift(1).rolling(3, min_periods=2).mean()
    monthly["wholesale_change"] = monthly["wholesale_signal"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    monthly["time_idx"] = np.arange(len(monthly), dtype=float)
    feature_cols = ["lag1", "lag2", "rolling3", "wholesale_signal", "wholesale_change", "time_idx"]

    predictions: list[float | None] = [None] * len(monthly)
    wholesale_effects: list[float | None] = [None] * len(monthly)
    min_train = 5
    for idx in range(len(monthly)):
        row = monthly.iloc[idx]
        if idx < min_train or row[feature_cols].isna().any():
            continue
        train = monthly.iloc[:idx].dropna(subset=feature_cols + ["actual"])
        if len(train) < min_train:
            continue
        X_train = _design_matrix(train[feature_cols])
        y_train = train["actual"].to_numpy(dtype=float)
        weights = _fit_ridge(X_train, y_train)
        x_row = _design_matrix(pd.DataFrame([row[feature_cols].to_dict()]))
        pred = float((x_row @ weights).item())
        predictions[idx] = max(pred, 0.0)

        feature_only = row[feature_cols].to_dict()
        baseline_wholesale = float(train["wholesale_signal"].mean()) if len(train) else float(row["wholesale_signal"])
        feature_only["wholesale_signal"] = baseline_wholesale
        feature_only["wholesale_change"] = 0.0
        x_counter = _design_matrix(pd.DataFrame([feature_only]))
        counter_pred = float((x_counter @ weights).item())
        wholesale_effects[idx] = max(pred - counter_pred, 0.0) if pred >= counter_pred else min(pred - counter_pred, 0.0)

    monthly["predicted"] = predictions
    monthly["wholesale_effect"] = wholesale_effects
    evaluated = monthly[monthly["predicted"].notna()].copy()
    if evaluated.empty:
        return None

    actual_sum = float(evaluated["actual"].sum())
    error_sum = float((evaluated["predicted"] - evaluated["actual"]).abs().sum())
    model_wape = (error_sum / actual_sum) if actual_sum else None

    latest = monthly.iloc[-1]
    if pd.isna(latest["predicted"]):
        return None
    unexplained_residual_pct = _safe_pct(float(latest["actual"] - latest["predicted"]), float(latest["predicted"]))
    wholesale_delta_pct = _safe_pct(
        float(latest["wholesale_signal"] - monthly.iloc[-2]["wholesale_signal"]),
        float(monthly.iloc[-2]["wholesale_signal"]),
    ) if len(monthly) >= 2 else None

    return {
        "available": True,
        "latestWholesale": float(latest["wholesale_signal"]),
        "wholesaleDeltaPct": float(wholesale_delta_pct) if wholesale_delta_pct is not None else None,
        "expectedFromModel": float(latest["predicted"]),
        "modelWape": float(model_wape) if model_wape is not None else None,
        "unexplainedResidualPct": float(unexplained_residual_pct) if unexplained_residual_pct is not None else None,
        "wholesaleContribution": float(latest["wholesale_effect"]) if pd.notna(latest["wholesale_effect"]) else None,
        "relationshipStrength": _relationship_strength(float(model_wape) if model_wape is not None else None),
    }


def _normalize_model_key(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )


def _design_matrix(frame: pd.DataFrame) -> np.ndarray:
    values = frame.to_numpy(dtype=float)
    intercept = np.ones((len(frame), 1), dtype=float)
    return np.hstack([intercept, values])


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    eye = np.eye(X.shape[1], dtype=float)
    eye[0, 0] = 0.0
    return np.linalg.pinv(X.T @ X + alpha * eye) @ X.T @ y


def _relationship_strength(model_wape: float | None) -> str:
    if model_wape is None:
        return "Unavailable"
    if model_wape <= 0.2:
        return "Strong"
    if model_wape <= 0.4:
        return "Moderate"
    return "Weak"


def _forecast_next_value(values: list[float], model_name: str) -> float:
    if model_name == "naive_last":
        return values[-1]

    if model_name == "seasonal_naive" and len(values) >= 12:
        return values[-12]

    if model_name == "seasonal_mean" and len(values) >= 12:
        seasonal_values = values[-12::-12]
        if seasonal_values:
            return float(sum(seasonal_values) / len(seasonal_values))
        return _weighted_recent_average(values[-3:])

    if model_name == "trailing_12_mean":
        window = values[-12:] if len(values) >= 12 else values
        return float(sum(window) / len(window))

    if model_name == "croston_sba":
        return _croston_sba_forecast(values)

    if model_name == "log_linear_trend":
        recent = values[-6:] if len(values) >= 6 else values
        if len(recent) < 3:
            return _weighted_recent_average(recent)
        x = np.arange(len(recent), dtype=float)
        y = np.log1p(np.array(recent, dtype=float))
        design = np.vstack([x, np.ones(len(x), dtype=float)]).T
        slope, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
        projected = np.expm1(slope * len(recent) + intercept)
        return max(0.0, float(projected))

    if model_name == "trend_adjusted_moving_average":
        recent = values[-6:] if len(values) >= 6 else values
        if len(recent) <= 2:
            return _weighted_recent_average(recent)
        base = _weighted_recent_average(recent[-3:])
        trend = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
        return max(0.0, base + trend)

    if model_name == "damped_trend":
        recent = values[-8:] if len(values) >= 8 else values
        if len(recent) <= 2:
            return _weighted_recent_average(recent)
        level = recent[0]
        trend = recent[1] - recent[0]
        alpha = 0.45
        beta = 0.2
        phi = 0.8
        for value in recent[1:]:
            prev_level = level
            level = alpha * value + (1 - alpha) * (level + phi * trend)
            trend = beta * (level - prev_level) + (1 - beta) * phi * trend
        return max(0.0, level + phi * trend)

    if model_name == "weighted_moving_average":
        recent = values[-3:]
        return _weighted_recent_average(recent)

    window = values[-6:] if len(values) >= 6 else values
    return sum(window) / len(window)


def _weighted_recent_average(recent: list[float]) -> float:
    if len(recent) == 1:
        return recent[-1]
    if len(recent) == 2:
        return recent[-1] * 0.65 + recent[-2] * 0.35
    return recent[-1] * 0.6 + recent[-2] * 0.3 + recent[-3] * 0.1


def _croston_sba_forecast(values: list[float]) -> float:
    recent = [max(float(value), 0.0) for value in values]
    if not recent:
        return 0.0
    non_zero = [value for value in recent if value > 0]
    if len(non_zero) < 2:
        return _weighted_recent_average(recent[-3:]) if len(recent) >= 2 else recent[-1]

    alpha = 0.2
    demand = non_zero[0]
    interval = 1.0
    gap = 1

    for value in recent[1:]:
        if value > 0:
            demand = alpha * value + (1 - alpha) * demand
            interval = alpha * gap + (1 - alpha) * interval
            gap = 1
        else:
            gap += 1

    if interval <= 0:
        return 0.0
    return max(0.0, (1 - alpha / 2.0) * (demand / interval))


def _ets_additive_forecast(values: list[float], horizon: int, season_length: int = 12) -> list[float]:
    """Additive Holt-Winters level + trend + seasonality.

    Fixed smoothing coefficients keep the model deterministic; rolling WAPE
    determines whether it is preferable to simpler candidates.
    """
    clean = np.asarray([max(float(value), 0.0) for value in values], dtype=float)
    if len(clean) < season_length * 2:
        fallback = clean.tolist()
        result: list[float] = []
        for _ in range(horizon):
            prediction = max(0.0, float(_forecast_next_value(fallback, "damped_trend")))
            result.append(prediction)
            fallback.append(prediction)
        return result

    first = clean[:season_length]
    second = clean[season_length : season_length * 2]
    level = float(np.mean(first))
    trend = float((np.mean(second) - np.mean(first)) / season_length)
    seasonals = [float(first[index] - level) for index in range(season_length)]
    alpha, beta, gamma = 0.35, 0.10, 0.25

    for index, value in enumerate(clean):
        season_index = index % season_length
        previous_level = level
        previous_season = seasonals[season_index]
        level = alpha * (float(value) - previous_season) + (1.0 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1.0 - beta) * trend
        seasonals[season_index] = gamma * (float(value) - level) + (1.0 - gamma) * previous_season

    return [
        max(
            0.0,
            float(level + step * trend + seasonals[(len(clean) + step - 1) % season_length]),
        )
        for step in range(1, horizon + 1)
    ]


def _history_zero_share(history: list[float]) -> float:
    if not history:
        return 0.0
    zero_count = sum(1 for value in history if float(value) <= 0.0)
    return zero_count / len(history)


def _rolling_backtest(
    history: list[float],
    model_name: str,
    preprocessing: str = "raw",
) -> tuple[float | None, float | None, float | None]:
    holdout = min(6, max(3, len(history) // 4))
    start = max(3, len(history) - holdout)
    actuals: list[float] = []
    predictions: list[float] = []

    for idx in range(start, len(history)):
        train = history[:idx]
        if len(train) < 2:
            continue
        train_processed, _ = preprocess_history(train, preprocessing)
        predictions.append(forecast_history(train_processed, 1, model_name=model_name)[0])
        actuals.append(history[idx])

    if not actuals:
        return None, None, None

    error_sum = sum(abs(pred - actual) for pred, actual in zip(predictions, actuals))
    actual_sum = sum(actuals)
    mae = error_sum / len(actuals)
    wape = (error_sum / actual_sum) if actual_sum else None
    bias = ((sum(predictions) - actual_sum) / actual_sum) if actual_sum else None
    return float(mae), float(wape) if wape is not None else None, float(bias) if bias is not None else None


def _score_confidence(history: list[float], wape: float | None, bias: float | None) -> str:
    if wape is None:
        return "Low"

    series = pd.Series(history, dtype="float64")
    non_zero = series.replace(0, pd.NA).dropna()
    mean_level = float(non_zero.mean()) if not non_zero.empty else float(series.mean()) if len(series) else 0.0
    volatility = float(series.std(ddof=0) / mean_level) if mean_level > 0 else 1.5
    bias_abs = abs(bias) if bias is not None else 1.0

    if len(history) >= 18 and wape <= 0.25 and volatility <= 0.8 and bias_abs <= 0.2:
        return "High"
    if len(history) >= 12 and wape <= 0.45 and volatility <= 1.25 and bias_abs <= 0.45:
        return "Medium"
    return "Low"


def detect_series_anomalies(series_df: pd.DataFrame, limit: int = 4) -> list[dict[str, Any]]:
    if series_df.empty or len(series_df) < 5:
        return []

    working = series_df.copy()
    working["rolling_median"] = working["actual"].rolling(window=6, min_periods=3).median()
    residual = (working["actual"] - working["rolling_median"]).abs()
    working["mad"] = residual.rolling(window=6, min_periods=3).median()
    working["score"] = ((working["actual"] - working["rolling_median"]).abs() / working["mad"].replace(0, pd.NA)).fillna(0.0)

    anomalies = working[working["score"] >= 2.0].copy()
    if anomalies.empty:
        return []

    results: list[dict[str, Any]] = []
    for row in anomalies.sort_values("score", ascending=False).head(limit).to_dict("records"):
        baseline = row["rolling_median"]
        actual = row["actual"]
        delta_pct = None
        if baseline not in (None, 0) and pd.notna(baseline):
            delta_pct = ((actual - baseline) / baseline) * 100
        results.append(
            {
                "month": pd.Timestamp(row["month"]).strftime("%Y-%m"),
                "actual": float(actual),
                "baseline": float(baseline) if pd.notna(baseline) else None,
                "deltaPct": float(delta_pct) if delta_pct is not None else None,
                "severity": "High" if row["score"] >= 3.5 else "Medium",
            }
        )
    return results


def explain_latest_change(
    df: pd.DataFrame,
    part_col: str,
    qty_col: str,
    date_series: pd.Series,
    part_value: str,
    brand_col: str | None = None,
    model_col: str | None = None,
) -> dict[str, Any] | None:
    working = prepare_forecast_rows(df, part_col, qty_col, date_series, part_value)
    if working.empty:
        return None

    working["month"] = working["__date"].dt.to_period("M").dt.to_timestamp()
    monthly = working.groupby("month", dropna=True)["__qty"].sum().sort_index()
    if len(monthly) < 2:
        return None

    latest_month = monthly.index[-1]
    previous_month = monthly.index[-2]
    latest_value = float(monthly.iloc[-1])
    previous_value = float(monthly.iloc[-2])
    delta = latest_value - previous_value
    delta_pct = ((delta / previous_value) * 100) if previous_value else None

    notes: list[str] = []
    direction_word = "up" if delta >= 0 else "down"
    if delta_pct is not None:
        notes.append(
            f"{latest_month.strftime('%Y-%m')} is {abs(delta_pct):.1f}% {direction_word} versus {previous_month.strftime('%Y-%m')}."
        )
    else:
        notes.append(
            f"{latest_month.strftime('%Y-%m')} moved by {delta:,.0f} units versus {previous_month.strftime('%Y-%m')}."
        )

    recent_mean = monthly.tail(6).mean()
    if recent_mean > 0:
        notes.append(f"Latest month closed at {latest_value / recent_mean * 100:.0f}% of the recent 6-month average.")

    brand_changes = _build_contribution_changes(working, latest_month, previous_month, "__qty", brand_col)
    model_changes = _build_contribution_changes(working, latest_month, previous_month, "__qty", model_col)

    if brand_changes:
        top_brand = brand_changes[0]
        notes.append(
            f"Brand mix shift is led by {top_brand['name']}, contributing {top_brand['delta']:+,.0f} units month over month."
        )
    if model_changes:
        top_model = model_changes[0]
        notes.append(
            f"Model mix shift is led by {top_model['name']}, contributing {top_model['delta']:+,.0f} units month over month."
        )

    return {
        "latestMonth": latest_month.strftime("%Y-%m"),
        "previousMonth": previous_month.strftime("%Y-%m"),
        "latestActual": latest_value,
        "previousActual": previous_value,
        "delta": float(delta),
        "deltaPct": float(delta_pct) if delta_pct is not None else None,
        "notes": notes[:4],
        "brandDrivers": brand_changes[:4],
        "modelDrivers": model_changes[:4],
    }


def _build_contribution_changes(
    working: pd.DataFrame,
    latest_month: pd.Timestamp,
    previous_month: pd.Timestamp,
    qty_col: str,
    dimension_col: str | None,
) -> list[dict[str, Any]]:
    if not dimension_col or dimension_col not in working.columns:
        return []

    latest = (
        working.loc[working["month"] == latest_month]
        .groupby(dimension_col, dropna=True)[qty_col]
        .sum()
    )
    previous = (
        working.loc[working["month"] == previous_month]
        .groupby(dimension_col, dropna=True)[qty_col]
        .sum()
    )

    aligned = pd.concat([latest.rename("latest"), previous.rename("previous")], axis=1).fillna(0.0)
    if aligned.empty:
        return []

    aligned["delta"] = aligned["latest"] - aligned["previous"]
    aligned = aligned[aligned["delta"] != 0].copy()
    if aligned.empty:
        return []

    ranked = aligned.reindex(aligned["delta"].abs().sort_values(ascending=False).index)
    return [
        {
            "name": str(index),
            "latest": float(row["latest"]),
            "previous": float(row["previous"]),
            "delta": float(row["delta"]),
        }
        for index, row in ranked.head(5).iterrows()
    ]
