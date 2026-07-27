from __future__ import annotations

import math
import time
import warnings
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.special import inv_boxcox
from scipy.stats import boxcox
from statsmodels.tsa.holtwinters import ExponentialSmoothing, Holt, SimpleExpSmoothing

from pio_platform.backtest_harness import (
    BacktestContract,
    expected_fold_counts,
    normalize_monthly_series,
    summarize_predictions,
)
from pio_platform.forecasting import forecast_history, preprocess_history


STANDARD_STRUCTURES: tuple[tuple[str, str | None, bool, str | None], ...] = (
    ("ses", None, False, None),
    ("holt_add", "additive", False, None),
    ("holt_damped_add", "additive", True, None),
    ("hw_add_add", "additive", False, "additive"),
    ("hw_damped_add_add", "additive", True, "additive"),
)
INITIALIZATION_METHODS = ("estimated", "heuristic", "legacy-heuristic")
TRANSFORMS = ("raw", "log1p", "boxcox")
TRAINING_WINDOWS = ("expanding", "rolling_24", "rolling_30", "rolling_36")
PREPROCESSING_MODES = ("raw", "anomaly_softened")


@dataclass(frozen=True)
class EtsCandidateSpec:
    model_id: str
    implementation: str
    trend: str | None
    damped_trend: bool
    seasonality: str | None
    initialization_method: str
    smoothing_parameter_selection: str
    transform: str
    training_window: str
    preprocessing: str
    optimized: bool = True
    remove_bias: bool = False
    seasonal_periods: int | None = None

    @property
    def complexity(self) -> int:
        score = 1
        score += 1 if self.trend else 0
        score += 1 if self.damped_trend else 0
        score += 2 if self.seasonality else 0
        score += 1 if self.transform != "raw" else 0
        score += 1 if self.preprocessing != "raw" else 0
        return score


VALIDATED_HMA_REVENUE_SPEC = EtsCandidateSpec(
    model_id="hw_add_add__heuristic__bias_on__log1p__rolling_24__robust_winsorized",
    implementation="statsmodels_holtwinters",
    trend="additive",
    damped_trend=False,
    seasonality="additive",
    initialization_method="heuristic",
    smoothing_parameter_selection="optimized_sse",
    transform="log1p",
    training_window="rolling_24",
    preprocessing="robust_winsorized",
    optimized=True,
    remove_bias=True,
    seasonal_periods=12,
)

VALIDATED_REFERENCE_PORTFOLIO: dict[str, Any] = {
    "contractVersion": "pio-backtest-v1",
    "sourceHash": "f44048f30632e6f1d77d5336d2d313b4855e9d1cec95577b4a50f1c8f33c2c47",
    "trainingCutoff": "2026-06",
    "backtestHorizons": [1, 2, 3],
    "foldCount": 51,
    "wapeScope": "official total after summing HMA/GMA/KUS on common origin-horizon rows",
    "implementationStatus": "validated_implementation",
    "officialTotal": {
        "wape": 0.06893887801948267,
        "accuracy": 0.9310611219805174,
        "biasPercentage": 0.010737313740393228,
        "foldWapeStandardDeviation": 0.056316697141294746,
    },
    "brandMetrics": {
        "HMA": {"wape": 0.09892838286573653, "accuracy": 0.9010716171342634},
        "GMA": {"wape": 0.1476762011872328, "accuracy": 0.8523237988127672},
        "KUS": {"wape": 0.09628249299559685, "accuracy": 0.9037175070044031},
    },
    "brandMethods": {
        "HMA": VALIDATED_HMA_REVENUE_SPEC.model_id,
        "GMA": "naive_last",
        "KUS": "working_day_adjusted_seasonal",
    },
}


def repository_baselines() -> list[EtsCandidateSpec]:
    return [
        EtsCandidateSpec(
            model_id="repository_ets_additive__raw__expanding__raw",
            implementation="repository_fixed_ets_additive",
            trend="additive",
            damped_trend=False,
            seasonality="additive",
            seasonal_periods=12,
            initialization_method="repository_first_two_seasons",
            smoothing_parameter_selection="fixed_alpha_0.35_beta_0.10_gamma_0.25",
            transform="raw",
            training_window="expanding",
            preprocessing="raw",
            optimized=False,
            remove_bias=False,
        ),
        EtsCandidateSpec(
            model_id="legacy_damped_trend__raw__expanding__raw",
            implementation="repository_damped_trend",
            trend="additive",
            damped_trend=True,
            seasonality=None,
            initialization_method="repository_recent_8_months",
            smoothing_parameter_selection="fixed_alpha_0.45_beta_0.20_phi_0.80",
            transform="raw",
            training_window="expanding",
            preprocessing="raw",
            optimized=False,
            remove_bias=False,
        ),
    ]


def build_candidate_grid(
    *,
    preprocessing_modes: Iterable[str] = PREPROCESSING_MODES,
) -> list[EtsCandidateSpec]:
    candidates: list[EtsCandidateSpec] = []
    for structure, trend, damped, seasonality in STANDARD_STRUCTURES:
        for initialization in INITIALIZATION_METHODS:
            for remove_bias in (False, True):
                for transform in TRANSFORMS:
                    for training_window in TRAINING_WINDOWS:
                        for preprocessing in preprocessing_modes:
                            model_id = "__".join(
                                (
                                    structure,
                                    initialization.replace("-", "_"),
                                    f"bias_{'on' if remove_bias else 'off'}",
                                    transform,
                                    training_window,
                                    preprocessing,
                                )
                            )
                            candidates.append(
                                EtsCandidateSpec(
                                    model_id=model_id,
                                    implementation="statsmodels_holtwinters",
                                    trend=trend,
                                    damped_trend=damped,
                                    seasonality=seasonality,
                                    seasonal_periods=12 if seasonality else None,
                                    initialization_method=initialization,
                                    smoothing_parameter_selection="optimized_sse",
                                    transform=transform,
                                    training_window=training_window,
                                    preprocessing=preprocessing,
                                    optimized=True,
                                    remove_bias=remove_bias,
                                )
                            )
    return candidates


def run_ets_candidate(
    series: pd.Series,
    spec: EtsCandidateSpec,
    *,
    contract: BacktestContract | None = None,
    source_hash: str = "",
) -> dict[str, Any]:
    active_contract = contract or BacktestContract()
    monthly = normalize_monthly_series(series)
    expected = expected_fold_counts(len(monthly), active_contract)
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    origin_diagnostics: list[dict[str, Any]] = []
    warning_messages: list[str] = []
    failed_origins = 0

    for training_end in range(active_contract.minimum_training_months, len(monthly)):
        origin_month = monthly.index[training_end - 1]
        available = monthly.iloc[:training_end]
        training = _apply_training_window(available, spec.training_window)
        prepared, adjusted_months = _preprocess(training.to_numpy(dtype=float), spec.preprocessing)
        target_count = min(max(active_contract.horizons), len(monthly) - training_end)
        fold_warnings: list[str] = []
        fold_error: str | None = None
        parameters: dict[str, Any] = {}
        forecasts: np.ndarray | None = None

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                forecasts, parameters = _fit_and_forecast(prepared, target_count, spec)
            except Exception as exc:  # candidate failures are governed output, not skipped folds
                fold_error = f"{type(exc).__name__}: {exc}"
            fold_warnings = [
                f"{type(item.message).__name__}: {item.message}" for item in caught
            ]

        warning_messages.extend(fold_warnings)
        if fold_error is not None:
            failed_origins += 1

        origin_diagnostics.append(
            {
                "originMonth": str(origin_month),
                "availableTrainingMonths": int(training_end),
                "modelTrainingMonths": int(len(training)),
                "trainingStart": str(training.index.min()),
                "trainingEnd": str(training.index.max()),
                "adjustedMonths": int(adjusted_months),
                "parameters": parameters,
                "warnings": fold_warnings,
                "error": fold_error,
            }
        )

        for horizon in active_contract.horizons:
            target_position = training_end + horizon - 1
            if target_position >= len(monthly):
                continue
            prediction = (
                float(forecasts[horizon - 1])
                if forecasts is not None and horizon <= len(forecasts)
                else None
            )
            rows.append(
                {
                    "model_id": spec.model_id,
                    "origin_month": str(origin_month),
                    "target_month": str(monthly.index[target_position]),
                    "horizon": int(horizon),
                    "actual": float(monthly.iloc[target_position]),
                    "prediction": max(prediction, 0.0) if prediction is not None else None,
                    "available_training_months": int(training_end),
                    "model_training_months": int(len(training)),
                    "training_start": str(training.index.min()),
                    "training_end": str(training.index.max()),
                    "source_hash": source_hash,
                    "contract_version": active_contract.version,
                    "error": fold_error,
                }
            )

    prediction_frame = pd.DataFrame(rows)
    combined_metrics = summarize_predictions(prediction_frame)
    horizon_metrics = {
        str(horizon): summarize_predictions(
            prediction_frame[prediction_frame["horizon"] == horizon]
        )
        for horizon in active_contract.horizons
    }
    failed_folds = int(prediction_frame["prediction"].isna().sum())
    coverage = float(combined_metrics.get("predictionCoverage") or 0.0)

    return {
        "modelId": spec.model_id,
        "spec": asdict(spec),
        "complexity": spec.complexity,
        "horizonMetrics": horizon_metrics,
        "combinedMetrics": combined_metrics,
        "expectedFoldCount": int(expected["combined"]),
        "failedFoldCount": failed_folds,
        "failedOriginCount": failed_origins,
        "convergenceWarningCount": len(warning_messages),
        "convergenceWarnings": sorted(set(warning_messages)),
        "predictionCoverage": coverage,
        "runtimeSeconds": float(time.perf_counter() - started),
        "originDiagnostics": origin_diagnostics,
        "predictions": rows,
    }


def forecast_ets_candidate(
    history: Sequence[float],
    horizon: int,
    spec: EtsCandidateSpec = VALIDATED_HMA_REVENUE_SPEC,
) -> tuple[list[float], dict[str, Any]]:
    values = pd.Series(
        np.maximum(np.asarray(history, dtype=float), 0.0),
        index=pd.RangeIndex(len(history)),
    )
    training = _apply_training_window(values, spec.training_window)
    prepared, adjusted_months = _preprocess(
        training.to_numpy(dtype=float),
        spec.preprocessing,
    )
    forecasts, parameters = _fit_and_forecast(prepared, horizon, spec)
    return forecasts.tolist(), {
        "modelTrainingMonths": int(len(training)),
        "adjustedMonths": int(adjusted_months),
        "parameters": parameters,
    }


def audit_candidate_result(
    result: dict[str, Any],
    *,
    contract: BacktestContract | None = None,
) -> dict[str, Any]:
    active_contract = contract or BacktestContract()
    rows = result.get("predictions", [])
    violations: list[str] = []
    horizon_counts = {str(horizon): 0 for horizon in active_contract.horizons}
    fold_keys: set[tuple[str, str, int]] = set()

    for row in rows:
        horizon = int(row["horizon"])
        horizon_counts[str(horizon)] += 1
        origin = pd.Period(row["origin_month"], freq="M")
        target = pd.Period(row["target_month"], freq="M")
        training_end = pd.Period(row["training_end"], freq="M")
        if target != origin + horizon:
            violations.append(
                f"target mismatch: origin={origin}, horizon={horizon}, target={target}"
            )
        if training_end > origin:
            violations.append(
                f"training after origin: trainingEnd={training_end}, origin={origin}"
            )
        key = (str(origin), str(target), horizon)
        if key in fold_keys:
            violations.append(f"duplicate fold key: {key}")
        fold_keys.add(key)

    horizon_counts["combined"] = len(rows)
    return {
        "status": "pass" if not violations else "fail",
        "violations": violations,
        "horizonCounts": horizon_counts,
        "foldKeyCount": len(fold_keys),
    }


def select_ets_champion(
    candidate_results: Sequence[dict[str, Any]],
    *,
    tie_band_wape: float = 0.01,
) -> dict[str, Any]:
    eligible = [
        item
        for item in candidate_results
        if item.get("spec", {}).get("implementation") == "statsmodels_holtwinters"
        and item.get("combinedMetrics", {}).get("wape") is not None
        and float(item.get("predictionCoverage") or 0.0) == 1.0
        and item.get("failedFoldCount") == 0
    ]
    if not eligible:
        return {"champion": None, "reason": "No full-coverage standard ETS candidate."}

    minimum_wape = min(float(item["combinedMetrics"]["wape"]) for item in eligible)
    tied = [
        item
        for item in eligible
        if float(item["combinedMetrics"]["wape"]) <= minimum_wape + tie_band_wape
    ]
    champion = min(
        tied,
        key=lambda item: (
            abs(_metric_or_infinity(item, "biasPercentage")),
            _metric_or_infinity(item, "foldWapeStandardDeviation"),
            -float(item.get("predictionCoverage") or 0.0),
            int(item.get("complexity", 99)),
            str(item["modelId"]),
        ),
    )
    empirical_best = min(
        eligible,
        key=lambda item: (
            float(item["combinedMetrics"]["wape"]),
            str(item["modelId"]),
        ),
    )
    return {
        "champion": champion["modelId"],
        "empiricalBest": empirical_best["modelId"],
        "minimumWape": minimum_wape,
        "tieBandWape": tie_band_wape,
        "tieSet": sorted(item["modelId"] for item in tied),
        "eligibleCount": len(eligible),
        "reason": (
            "Full-coverage candidates within the WAPE tie band were ranked by "
            "absolute bias, fold-WAPE standard deviation, coverage, then complexity."
        ),
    }


def compact_candidate_summary(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["combinedMetrics"]
    horizon_metrics = result["horizonMetrics"]
    return {
        "modelId": result["modelId"],
        "spec": result["spec"],
        "h1Wape": horizon_metrics["1"]["wape"],
        "h2Wape": horizon_metrics["2"]["wape"],
        "h3Wape": horizon_metrics["3"]["wape"],
        "combinedWape": metrics["wape"],
        "accuracy": metrics["accuracy"],
        "mae": metrics["mae"],
        "signedBias": metrics["signedBias"],
        "biasPercentage": metrics["biasPercentage"],
        "foldWapeStandardDeviation": metrics["foldWapeStandardDeviation"],
        "predictionCoverage": metrics["predictionCoverage"],
        "foldCount": metrics["foldCount"],
        "failedFoldCount": result["failedFoldCount"],
        "convergenceWarningCount": result["convergenceWarningCount"],
        "runtimeSeconds": result["runtimeSeconds"],
        "complexity": result["complexity"],
    }


def _apply_training_window(series: pd.Series, training_window: str) -> pd.Series:
    if training_window == "expanding":
        return series
    if training_window.startswith("rolling_"):
        months = int(training_window.split("_", maxsplit=1)[1])
        return series.iloc[-months:]
    raise ValueError(f"Unsupported training window: {training_window}")


def _preprocess(values: np.ndarray, preprocessing: str) -> tuple[np.ndarray, int]:
    clean = np.maximum(np.asarray(values, dtype=float), 0.0)
    if preprocessing == "raw":
        return clean, 0
    if preprocessing == "anomaly_softened":
        prepared, adjusted = preprocess_history(clean.tolist(), "cleaned")
        return np.asarray(prepared, dtype=float), int(adjusted)
    if preprocessing == "robust_winsorized":
        median = float(np.median(clean))
        mad = float(np.median(np.abs(clean - median)))
        if mad <= 0:
            return clean, 0
        lower = max(0.0, median - 4.5 * mad)
        upper = median + 4.5 * mad
        clipped = np.clip(clean, lower, upper)
        return clipped, int(np.count_nonzero(~np.isclose(clipped, clean)))
    raise ValueError(f"Unsupported preprocessing: {preprocessing}")


def _fit_and_forecast(
    values: np.ndarray,
    horizon: int,
    spec: EtsCandidateSpec,
) -> tuple[np.ndarray, dict[str, Any]]:
    if horizon < 1:
        return np.asarray([], dtype=float), {}

    if spec.implementation == "repository_fixed_ets_additive":
        forecasts = forecast_history(values.tolist(), horizon, "ets_additive")
        return np.asarray(forecasts, dtype=float), {
            "smoothing_level": 0.35,
            "smoothing_trend": 0.10,
            "smoothing_seasonal": 0.25,
            "seasonal_periods": 12,
        }
    if spec.implementation == "repository_damped_trend":
        forecasts = forecast_history(values.tolist(), horizon, "damped_trend")
        return np.asarray(forecasts, dtype=float), {
            "smoothing_level": 0.45,
            "smoothing_trend": 0.20,
            "damping_trend": 0.80,
            "recent_window": 8,
        }

    transformed = np.asarray(values, dtype=float)
    boxcox_lambda: float | None = None
    if spec.transform == "log1p":
        transformed = np.log1p(transformed)
    elif spec.transform == "boxcox":
        if np.any(transformed <= 0):
            raise ValueError("Box-Cox requires strictly positive fold training values.")
        transformed, boxcox_lambda = boxcox(transformed)
    elif spec.transform != "raw":
        raise ValueError(f"Unsupported transform: {spec.transform}")

    common = {"initialization_method": spec.initialization_method}
    if spec.seasonality:
        model = ExponentialSmoothing(
            transformed,
            trend="add",
            damped_trend=spec.damped_trend,
            seasonal="add",
            seasonal_periods=spec.seasonal_periods or 12,
            use_boxcox=False,
            **common,
        )
    elif spec.trend:
        model = Holt(
            transformed,
            damped_trend=spec.damped_trend,
            **common,
        )
    else:
        model = SimpleExpSmoothing(transformed, **common)

    fit_kwargs: dict[str, Any] = {
        "optimized": spec.optimized,
        "remove_bias": spec.remove_bias,
        "use_brute": False,
    }
    fitted = model.fit(**fit_kwargs)
    forecasts = np.asarray(fitted.forecast(horizon), dtype=float)
    if spec.transform == "log1p":
        forecasts = np.expm1(forecasts)
    elif spec.transform == "boxcox":
        forecasts = inv_boxcox(forecasts, boxcox_lambda)
    forecasts = np.maximum(forecasts, 0.0)
    parameters = _json_safe(dict(fitted.params))
    if boxcox_lambda is not None:
        parameters["boxcox_lambda"] = float(boxcox_lambda)
    mle_retvals = getattr(fitted, "mle_retvals", None)
    if mle_retvals is not None:
        parameters["optimizer"] = _json_safe(mle_retvals)
    return forecasts, parameters


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if value is None or isinstance(value, (str, int)):
        return value
    return str(value)


def _metric_or_infinity(result: dict[str, Any], metric: str) -> float:
    value = result.get("combinedMetrics", {}).get(metric)
    if value is None:
        return float("inf")
    return float(value)
