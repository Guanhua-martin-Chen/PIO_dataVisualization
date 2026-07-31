from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from pio_platform.backtest_harness import (
    BacktestContract,
    audit_fold_coverage,
    expected_fold_counts,
    normalize_monthly_series,
    summarize_predictions,
)
from pio_platform.ets_experiments import (
    VALIDATED_HMA_REVENUE_SPEC,
    forecast_ets_candidate,
)
from pio_platform.forecasting import forecast_history


TREE_META_SELECTOR_ID = "tree_meta_selector_v1"
ELASTIC_NET_RESIDUAL_ID = "elastic_net_anchor_residual_v1"
ML_CHALLENGER_IDS = frozenset(
    {TREE_META_SELECTOR_ID, ELASTIC_NET_RESIDUAL_ID}
)
ARTIFACT_VERSION = "pio-ml-challenger-v2-preregistered"
OFFICIAL_ANCHORS = ("HMA", "GMA", "KUS")
REFERENCE_METHODS = {
    "HMA": VALIDATED_HMA_REVENUE_SPEC.model_id,
    "GMA": "naive_last",
    "KUS": "working_day_adjusted_seasonal",
}
TREE_CANDIDATE_METHODS = (
    "reference_anchor",
    "naive_last",
    "seasonal_naive",
    "trailing_12_mean",
)
TREE_ALTERNATIVE_METHODS = tuple(
    method for method in TREE_CANDIDATE_METHODS if method != "reference_anchor"
)
TREE_ANCHOR_WEIGHTS = (0.7, 0.8, 0.9)
SAFE_MIN_WAPE_GAIN = 0.005
ELASTIC_ALPHA_GRID = (0.001, 0.01, 0.05, 0.1, 0.2, 0.5)
ELASTIC_L1_RATIO_GRID = (0.25, 0.5, 0.75)
ELASTIC_RESIDUAL_CLIPS = (0.05, 0.10, 0.15)
INNER_VALIDATION_ORIGINS = 6
FEATURE_NAMES = (
    "log_anchor",
    "log_lag1",
    "log_lag2",
    "log_lag3",
    "log_lag12",
    "log_rolling3_mean",
    "log_rolling6_mean",
    "trend6_scaled",
    "volatility6",
    "seasonal_ratio",
    "zero_share12",
    "working_day_ratio",
    "known_working_days_scaled",
    "entity_gma",
    "entity_kus",
    "kus_working_day_ratio",
    "kus_seasonal_ratio",
    "hma_trend6_scaled",
    "hma_month_sin",
    "hma_month_cos",
    "gma_month_sin",
    "gma_month_cos",
    "kus_month_sin",
    "kus_month_cos",
    "hma_horizon_scaled",
    "gma_horizon_scaled",
    "kus_horizon_scaled",
)
FEATURE_AVAILABILITY = (
    {
        "features": [
            "log_lag1",
            "log_lag2",
            "log_lag3",
            "log_lag12",
            "log_rolling3_mean",
            "log_rolling6_mean",
            "trend6_scaled",
            "volatility6",
            "seasonal_ratio",
            "zero_share12",
        ],
        "knownAt": "forecast origin",
        "source": "completed target history only",
    },
    {
        "features": [
            "hma_month_sin", "hma_month_cos",
            "gma_month_sin", "gma_month_cos",
            "kus_month_sin", "kus_month_cos",
            "hma_horizon_scaled", "gma_horizon_scaled", "kus_horizon_scaled",
        ],
        "knownAt": "forecast origin",
        "source": "Brand x target-month and Brand x horizon interactions",
    },
    {
        "features": [
            "working_day_ratio", "known_working_days_scaled",
            "kus_working_day_ratio",
        ],
        "knownAt": "forecast origin",
        "source": "supplied future Working_Days calendar",
    },
    {
        "features": ["log_anchor"],
        "knownAt": "forecast origin",
        "source": "governed statistical anchor forecast",
    },
    {
        "features": ["entity_gma", "entity_kus"],
        "knownAt": "static",
        "source": "official HMA/GMA/KUS anchor identity",
    },
    {
        "features": ["kus_seasonal_ratio", "hma_trend6_scaled"],
        "knownAt": "forecast origin",
        "source": "Brand-specific completed-history interactions",
    },
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = PROJECT_ROOT / "config" / "ml_challengers"


def train_ml_challengers(
    revenue: pd.DataFrame,
    working_days: Mapping[str, float],
    *,
    source_hash: str,
    training_cutoff: str,
    contract: BacktestContract | None = None,
) -> dict[str, dict[str, Any]]:
    """Train and evaluate both PR E challengers on nested rolling-origin folds.

    The complete statistical-candidate prediction grid is deterministic and
    may be precomputed. Every outer model fit filters labels and residuals to
    targets strictly earlier than that outer origin.
    """

    active_contract = contract or BacktestContract()
    panel = _prepare_panel(revenue)
    observed_months = len(next(iter(panel.values())))
    if observed_months <= active_contract.minimum_training_months:
        raise ValueError("ML challengers require more completed months than the minimum training window.")
    started = time.perf_counter()
    examples = _precompute_examples(
        panel,
        working_days,
        minimum_training_months=active_contract.minimum_training_months,
        horizons=active_contract.horizons,
    )
    tree_rows: list[dict[str, Any]] = []
    elastic_rows: list[dict[str, Any]] = []
    max_horizon = max(active_contract.horizons)
    months = next(iter(panel.values())).index

    for training_end in range(active_contract.minimum_training_months, observed_months):
        eligible_training = [
            item for item in examples if int(item["targetPosition"]) < training_end
        ]
        tree_model = _fit_tree_model(eligible_training)
        elastic_model = _fit_elastic_model(eligible_training)
        origin_month = str(months[training_end - 1])
        for horizon in active_contract.horizons:
            target_position = training_end + horizon - 1
            if target_position >= observed_months:
                continue
            target_month = months[target_position]
            for entity in OFFICIAL_ANCHORS:
                series = panel[entity]
                history = series.iloc[:training_end]
                candidate_predictions = _candidate_predictions(
                    history,
                    entity=entity,
                    horizon=horizon,
                    target_month=target_month,
                    working_days=working_days,
                )
                features = _feature_vector(
                    history,
                    entity=entity,
                    horizon=horizon,
                    target_month=target_month,
                    working_days=working_days,
                    anchor_prediction=candidate_predictions["reference_anchor"],
                )
                tree_prediction, tree_method, tree_fallback = _predict_tree(
                    tree_model,
                    features,
                    candidate_predictions,
                )
                elastic_prediction, elastic_fallback = _predict_elastic(
                    elastic_model,
                    features,
                    anchor_prediction=candidate_predictions["reference_anchor"],
                )
                actual = float(series.iloc[target_position])
                common = {
                    "target": "pio_revenue",
                    "level": "anchor_brand",
                    "entity": entity,
                    "origin_month": origin_month,
                    "target_month": str(target_month),
                    "horizon": int(horizon),
                    "actual": actual,
                    "training_months": int(training_end),
                    "source_hash": source_hash,
                    "contract_version": active_contract.version,
                    "error": None,
                }
                tree_rows.append(
                    {
                        **common,
                        "model_id": TREE_META_SELECTOR_ID,
                        "prediction": tree_prediction,
                        "backtest_model": (
                            f"{TREE_META_SELECTOR_ID}:{tree_method}"
                            + (":cold_start_anchor" if tree_fallback else "")
                        ),
                    }
                )
                elastic_rows.append(
                    {
                        **common,
                        "model_id": ELASTIC_NET_RESIDUAL_ID,
                        "prediction": elastic_prediction,
                        "backtest_model": (
                            ELASTIC_NET_RESIDUAL_ID
                            + (":cold_start_anchor" if elastic_fallback else "")
                        ),
                    }
                )

    final_tree = _fit_tree_model(examples)
    final_elastic = _fit_elastic_model(examples)
    elapsed = time.perf_counter() - started
    artifacts = {
        TREE_META_SELECTOR_ID: _build_artifact(
            model_id=TREE_META_SELECTOR_ID,
            model=final_tree,
            predictions=tree_rows,
            source_hash=source_hash,
            training_cutoff=training_cutoff,
            contract=active_contract,
            observed_months=observed_months,
            training_seconds=elapsed,
        ),
        ELASTIC_NET_RESIDUAL_ID: _build_artifact(
            model_id=ELASTIC_NET_RESIDUAL_ID,
            model=final_elastic,
            predictions=elastic_rows,
            source_hash=source_hash,
            training_cutoff=training_cutoff,
            contract=active_contract,
            observed_months=observed_months,
            training_seconds=elapsed,
        ),
    }
    return artifacts


def save_ml_challenger_artifacts(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    output_dir: Path = DEFAULT_ARTIFACT_DIR,
    compact: bool = True,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model_id in sorted(artifacts):
        path = output_dir / f"{model_id}.json"
        payload = (
            _deployment_artifact(artifacts[model_id])
            if compact
            else dict(artifacts[model_id])
        )
        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        written.append(path)
    clear_ml_artifact_cache()
    return written


@lru_cache(maxsize=8)
def _load_artifact_cached(
    model_id: str,
    source_hash: str,
    artifact_dir: str,
) -> dict[str, Any]:
    path = Path(artifact_dir) / f"{model_id}.json"
    if not path.exists():
        raise ValueError(
            f"{model_id} is not pretrained. Run scripts/train_ml_challengers.py first."
        )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("artifactVersion") != ARTIFACT_VERSION:
        raise ValueError(f"{model_id} artifact version is unsupported.")
    if artifact.get("modelId") != model_id:
        raise ValueError(f"{model_id} artifact identity does not match its filename.")
    registered_hash = str(artifact.get("sourceHash", "")).lower()
    if not source_hash or registered_hash != str(source_hash).lower():
        raise ValueError(
            f"{model_id} was pretrained for a different source. "
            "Retrain it offline; Forecast Center never trains during page load."
        )
    if artifact.get("status") != "challenger":
        raise ValueError(f"{model_id} must remain registered as a challenger.")
    return artifact


def load_ml_challenger_artifact(
    model_id: str,
    source_hash: str,
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    if model_id not in ML_CHALLENGER_IDS:
        raise ValueError(f"Unsupported ML challenger: {model_id}")
    return _load_artifact_cached(
        model_id,
        str(source_hash).lower(),
        str(artifact_dir.resolve()),
    )


def clear_ml_artifact_cache() -> None:
    _load_artifact_cached.cache_clear()


def forecast_with_ml_challenger(
    artifact: Mapping[str, Any],
    series: pd.Series,
    *,
    entity: str,
    horizon: int,
    working_days: Mapping[str, float],
) -> dict[str, Any]:
    model_id = str(artifact["modelId"])
    normalized = normalize_monthly_series(series)
    if normalized.empty:
        raise ValueError("ML challenger cannot forecast an empty series.")
    forecasts: list[float] = []
    selected_methods: list[str] = []
    fallback_modes: list[str] = []
    model = dict(artifact["model"])
    for step in range(1, horizon + 1):
        target_month = normalized.index[-1] + step
        candidate_predictions = _candidate_predictions(
            normalized,
            entity=entity,
            horizon=step,
            target_month=target_month,
            working_days=working_days,
        )
        features = _feature_vector(
            normalized,
            entity=entity,
            horizon=step,
            target_month=target_month,
            working_days=working_days,
            anchor_prediction=candidate_predictions["reference_anchor"],
        )
        if model_id == TREE_META_SELECTOR_ID:
            prediction, method, fallback = _predict_tree(
                model,
                features,
                candidate_predictions,
            )
            selected_methods.append(method)
        elif model_id == ELASTIC_NET_RESIDUAL_ID:
            prediction, fallback = _predict_elastic(
                model,
                features,
                anchor_prediction=candidate_predictions["reference_anchor"],
            )
            selected_methods.append("reference_anchor_plus_log_residual")
        else:
            raise ValueError(f"Unsupported ML challenger artifact: {model_id}")
        forecasts.append(prediction)
        fallback_modes.append("statistical_anchor" if fallback else "pretrained_artifact")
    return {
        "model": model_id,
        "preprocessing": "artifact_features",
        "forecast": forecasts,
        "wape": artifact["evaluation"]["officialTotalMetrics"].get("wape"),
        "selectionNote": (
            f"{model_id} loaded a CPU-trained artifact for the exact source hash. "
            "No training occurred during this Forecast Center request."
        ),
        "coefficients": {
            "artifactVersion": artifact["artifactVersion"],
            "trainingCutoff": artifact["trainingCutoff"],
            "selectedMethodsByHorizon": selected_methods,
            "runtime": artifact["runtime"],
            "fallbackModes": fallback_modes,
        },
    }


def artifact_entity_backtest(
    artifact: Mapping[str, Any],
    entity: str,
) -> dict[str, Any]:
    evaluation = artifact["evaluation"]
    rows = [
        dict(row)
        for row in evaluation.get("predictions", [])
        if str(row.get("entity")) == str(entity)
    ]
    if rows:
        metrics = summarize_predictions(pd.DataFrame(rows))
    else:
        metrics = dict(evaluation["entityMetrics"][str(entity)]["combined"])
    recent_h1 = sorted(
        [row for row in rows if int(row.get("horizon", 0)) == 1],
        key=lambda row: (str(row.get("target_month", "")), str(row.get("origin_month", ""))),
    )[-6:]
    return {
        "model": str(artifact["modelId"]),
        "points": int(metrics["foldCount"]),
        "actualSum": float(metrics["actualTotal"]),
        "absoluteErrorSum": (
            float(metrics["wape"]) * float(metrics["actualTotal"])
            if metrics["wape"] is not None
            else 0.0
        ),
        "wape": metrics["wape"],
        "mae": metrics["mae"],
        "bias": metrics["biasPercentage"],
        "rows": recent_h1,
    }


def artifact_residual_rows(
    artifact: Mapping[str, Any],
    entity: str,
) -> list[dict[str, Any]]:
    predictions = artifact["evaluation"].get("predictions", [])
    if not predictions:
        return _synthetic_residual_rows(artifact, entity)
    return [
        {
            "origin_month": str(row["origin_month"]),
            "target_month": str(row["target_month"]),
            "horizon": int(row["horizon"]),
            "actual": float(row["actual"]),
            "prediction": float(row["prediction"]),
            "entity": str(row["entity"]),
            "backtest_model": str(row["backtest_model"]),
        }
        for row in predictions
        if str(row.get("entity")) == str(entity)
    ]


def _synthetic_residual_rows(
    artifact: Mapping[str, Any],
    entity: str,
) -> list[dict[str, Any]]:
    """Return calibration-equivalent rows without exposing Brand actual totals."""

    return [
        {
            "origin_month": str(row["origin_month"]),
            "target_month": str(row["target_month"]),
            "horizon": int(row["horizon"]),
            "actual": float(row["absoluteResidual"]),
            "prediction": 0.0,
            "entity": str(row["entity"]),
            "backtest_model": str(artifact["modelId"]),
            "residualOnly": True,
        }
        for row in artifact["evaluation"].get("calibrationRows", [])
        if str(row.get("entity")) == str(entity)
    ]


def _deployment_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(artifact, ensure_ascii=False, allow_nan=False))
    evaluation = dict(payload["evaluation"])
    predictions = evaluation.pop("predictions", [])
    evaluation["calibrationRows"] = [
        {
            "entity": str(row["entity"]),
            "origin_month": str(row["origin_month"]),
            "target_month": str(row["target_month"]),
            "horizon": int(row["horizon"]),
            "absoluteResidual": abs(
                float(row["actual"]) - float(row["prediction"])
            ),
        }
        for row in predictions
    ]
    evaluation["privacyNote"] = (
        "Deployment artifacts omit Brand-month actual and prediction totals; "
        "only held-out absolute residuals required for interval calibration remain."
    )
    payload["evaluation"] = evaluation
    return payload


def _prepare_panel(revenue: pd.DataFrame) -> dict[str, pd.Series]:
    required = {"month", "entity", "value"}
    missing = required - set(revenue.columns)
    if missing:
        raise ValueError(f"Revenue panel is missing columns: {sorted(missing)}")
    source = revenue[revenue["entity"].astype(str).isin(OFFICIAL_ANCHORS)].copy()
    if source.empty:
        raise ValueError("Revenue panel has no HMA/GMA/KUS observations.")
    months = pd.PeriodIndex(source["month"].astype(str), freq="M")
    common_start = months.min()
    common_end = months.max()
    panel: dict[str, pd.Series] = {}
    for entity in OFFICIAL_ANCHORS:
        entity_source = source[source["entity"].astype(str) == entity]
        panel[entity] = normalize_monthly_series(
            entity_source,
            month_col="month",
            value_col="value",
            start_month=str(common_start),
            end_month=str(common_end),
        )
    lengths = {len(series) for series in panel.values()}
    if len(lengths) != 1:
        raise ValueError("ML panel anchors do not share one synchronized month index.")
    return panel


def _precompute_examples(
    panel: Mapping[str, pd.Series],
    working_days: Mapping[str, float],
    *,
    minimum_training_months: int,
    horizons: Sequence[int],
) -> list[dict[str, Any]]:
    months = next(iter(panel.values())).index
    observed_months = len(months)
    examples: list[dict[str, Any]] = []
    for training_end in range(minimum_training_months, observed_months):
        origin_month = str(months[training_end - 1])
        for horizon in horizons:
            target_position = training_end + int(horizon) - 1
            if target_position >= observed_months:
                continue
            target_month = months[target_position]
            for entity in OFFICIAL_ANCHORS:
                series = panel[entity]
                history = series.iloc[:training_end]
                candidates = _candidate_predictions(
                    history,
                    entity=entity,
                    horizon=int(horizon),
                    target_month=target_month,
                    working_days=working_days,
                )
                actual = float(series.iloc[target_position])
                anchor_absolute_error = abs(
                    actual - float(candidates["reference_anchor"])
                )
                candidate_improvements = {
                    method: (
                        anchor_absolute_error
                        - abs(actual - float(candidates[method]))
                    )
                    for method in TREE_ALTERNATIVE_METHODS
                }
                features = _feature_vector(
                    history,
                    entity=entity,
                    horizon=int(horizon),
                    target_month=target_month,
                    working_days=working_days,
                    anchor_prediction=candidates["reference_anchor"],
                )
                examples.append(
                    {
                        "features": features,
                        "candidatePredictions": dict(candidates),
                        "candidateDollarImprovements": candidate_improvements,
                        "residualTarget": (
                            math.log1p(actual)
                            - math.log1p(candidates["reference_anchor"])
                        ),
                        "anchorPrediction": candidates["reference_anchor"],
                        "actual": actual,
                        "originMonth": origin_month,
                        "targetMonth": str(target_month),
                        "targetPosition": int(target_position),
                        "entity": entity,
                        "horizon": int(horizon),
                    }
                )
    return examples


def _candidate_predictions(
    history: pd.Series,
    *,
    entity: str,
    horizon: int,
    target_month: pd.Period,
    working_days: Mapping[str, float],
) -> dict[str, float]:
    values = [max(float(value), 0.0) for value in history.tolist()]
    reference = _reference_anchor_prediction(
        values,
        entity=entity,
        horizon=horizon,
        training_months=history.index.tolist(),
        target_month=target_month,
        working_days=working_days,
    )
    output = {"reference_anchor": reference}
    for method in TREE_CANDIDATE_METHODS:
        if method == "reference_anchor":
            continue
        output[method] = max(
            float(forecast_history(values, horizon, method)[-1]),
            0.0,
        )
    return output


def _reference_anchor_prediction(
    history: Sequence[float],
    *,
    entity: str,
    horizon: int,
    training_months: Sequence[pd.Period],
    target_month: pd.Period,
    working_days: Mapping[str, float],
) -> float:
    normalized_entity = str(entity).upper()
    if normalized_entity == "HMA":
        forecast, _ = forecast_ets_candidate(
            history,
            horizon,
            VALIDATED_HMA_REVENUE_SPEC,
        )
        return max(float(forecast[-1]), 0.0)
    if normalized_entity == "GMA":
        return max(float(forecast_history(history, horizon, "naive_last")[-1]), 0.0)
    if normalized_entity == "KUS":
        values = [max(float(value), 0.0) for value in history]
        months = list(training_months)
        predictions: list[float] = []
        for step in range(1, horizon + 1):
            step_month = months[-1] + step
            if len(values) >= 12:
                prior_month = step_month - 12
                current_days = float(working_days.get(str(step_month), 0.0) or 0.0)
                prior_days = float(working_days.get(str(prior_month), 0.0) or 0.0)
                ratio = (
                    current_days / prior_days
                    if current_days > 0 and prior_days > 0
                    else 1.0
                )
                prediction = values[-12] * ratio
            else:
                prediction = values[-1]
            predictions.append(max(float(prediction), 0.0))
            values.append(predictions[-1])
        return predictions[-1]
    raise ValueError(f"Unsupported official anchor: {entity}")


def _feature_vector(
    history: pd.Series,
    *,
    entity: str,
    horizon: int,
    target_month: pd.Period,
    working_days: Mapping[str, float],
    anchor_prediction: float,
) -> list[float]:
    values = np.asarray([max(float(value), 0.0) for value in history], dtype=float)

    def lag(offset: int) -> float:
        return float(values[-offset]) if len(values) >= offset else float(values[0])

    recent6 = values[-6:] if len(values) >= 6 else values
    recent12 = values[-12:] if len(values) >= 12 else values
    rolling3 = float(np.mean(values[-3:]))
    rolling6 = float(np.mean(recent6))
    if len(recent6) >= 2:
        x = np.arange(len(recent6), dtype=float)
        slope = float(np.polyfit(x, np.log1p(recent6), 1)[0])
    else:
        slope = 0.0
    volatility = float(np.std(np.log1p(recent6), ddof=0)) if len(recent6) else 0.0
    seasonal_ratio = lag(1) / max(lag(12), 1.0)
    zero_share = float(np.mean(recent12 <= 0.0)) if len(recent12) else 0.0
    month_angle = 2.0 * math.pi * (int(target_month.month) - 1) / 12.0
    working_day_value = float(working_days.get(str(target_month), 0.0) or 0.0)
    prior_year_month = target_month - 12
    prior_year_working_days = float(
        working_days.get(str(prior_year_month), 0.0) or 0.0
    )
    working_day_ratio = (
        working_day_value / prior_year_working_days
        if working_day_value > 0 and prior_year_working_days > 0
        else 1.0
    )
    normalized_entity = str(entity).upper()
    is_hma = 1.0 if normalized_entity == "HMA" else 0.0
    is_gma = 1.0 if normalized_entity == "GMA" else 0.0
    is_kus = 1.0 if normalized_entity == "KUS" else 0.0
    month_sin = math.sin(month_angle)
    month_cos = math.cos(month_angle)
    horizon_scaled = float(horizon) / 3.0
    trend_scaled = float(np.clip(slope, -1.0, 1.0))
    features = [
        math.log1p(max(anchor_prediction, 0.0)),
        math.log1p(lag(1)),
        math.log1p(lag(2)),
        math.log1p(lag(3)),
        math.log1p(lag(12)),
        math.log1p(rolling3),
        math.log1p(rolling6),
        trend_scaled,
        volatility,
        float(np.clip(seasonal_ratio, 0.0, 5.0)),
        zero_share,
        float(np.clip(working_day_ratio, 0.5, 1.5)),
        working_day_value / 23.0,
        is_gma,
        is_kus,
        is_kus * float(np.clip(working_day_ratio, 0.5, 1.5)),
        is_kus * float(np.clip(seasonal_ratio, 0.0, 5.0)),
        is_hma * trend_scaled,
        is_hma * month_sin,
        is_hma * month_cos,
        is_gma * month_sin,
        is_gma * month_cos,
        is_kus * month_sin,
        is_kus * month_cos,
        is_hma * horizon_scaled,
        is_gma * horizon_scaled,
        is_kus * horizon_scaled,
    ]
    return [float(value) if np.isfinite(value) else 0.0 for value in features]


def _fit_tree_model(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(examples) < 12:
        return {
            "kind": "cold_start_reference_anchor",
            "tree": _tree_leaf_policy(examples),
            "candidateMethods": list(TREE_CANDIDATE_METHODS),
            "featureNames": list(FEATURE_NAMES),
            "maxDepth": 2,
            "minSamplesLeaf": 6,
            "minimumWapeGain": SAFE_MIN_WAPE_GAIN,
            "allowedAnchorWeights": [1.0, *TREE_ANCHOR_WEIGHTS],
            "trainingExamples": len(examples),
        }
    X = np.asarray([item["features"] for item in examples], dtype=float)
    tree = _build_tree_node(
        X,
        list(examples),
        depth=0,
        max_depth=2,
        min_samples_leaf=6,
    )
    return {
        "kind": "safe_anchor_blend_tree",
        "tree": tree,
        "candidateMethods": list(TREE_CANDIDATE_METHODS),
        "featureNames": list(FEATURE_NAMES),
        "maxDepth": 2,
        "minSamplesLeaf": 6,
        "minimumWapeGain": SAFE_MIN_WAPE_GAIN,
        "allowedAnchorWeights": [1.0, *TREE_ANCHOR_WEIGHTS],
        "objective": (
            "minimize pooled dollar absolute error relative to the validated anchor"
        ),
        "trainingExamples": len(examples),
    }


def _build_tree_node(
    X: np.ndarray,
    examples: Sequence[Mapping[str, Any]],
    *,
    depth: int,
    max_depth: int,
    min_samples_leaf: int,
) -> dict[str, Any]:
    parent_policy = _tree_leaf_policy(examples)
    if (
        depth >= max_depth
        or len(examples) < 2 * min_samples_leaf
    ):
        return parent_policy
    parent_loss = float(parent_policy["policyAbsoluteError"])
    best: tuple[float, int, float, np.ndarray] | None = None
    for feature_index in range(X.shape[1]):
        unique = np.unique(X[:, feature_index])
        if len(unique) <= 1:
            continue
        thresholds = (unique[:-1] + unique[1:]) / 2.0
        if len(thresholds) > 24:
            indexes = np.linspace(0, len(thresholds) - 1, 24).round().astype(int)
            thresholds = thresholds[indexes]
        for threshold in thresholds:
            left_mask = X[:, feature_index] <= threshold
            left_count = int(left_mask.sum())
            right_count = len(examples) - left_count
            if left_count < min_samples_leaf or right_count < min_samples_leaf:
                continue
            left_examples = [
                examples[index] for index in np.flatnonzero(left_mask)
            ]
            right_examples = [
                examples[index] for index in np.flatnonzero(~left_mask)
            ]
            split_loss = (
                float(_tree_leaf_policy(left_examples)["policyAbsoluteError"])
                + float(_tree_leaf_policy(right_examples)["policyAbsoluteError"])
            )
            gain = parent_loss - split_loss
            candidate = (gain, feature_index, float(threshold), left_mask)
            if best is None or (
                gain > best[0] + 1e-12
                or (
                    abs(gain - best[0]) <= 1e-12
                    and (feature_index, float(threshold)) < (best[1], best[2])
                )
            ):
                best = candidate
    if best is None or best[0] <= 1e-12:
        return parent_policy
    _, feature_index, threshold, left_mask = best
    left_examples = [examples[index] for index in np.flatnonzero(left_mask)]
    right_examples = [examples[index] for index in np.flatnonzero(~left_mask)]
    return {
        "featureIndex": int(feature_index),
        "featureName": FEATURE_NAMES[feature_index],
        "threshold": float(threshold),
        "samples": len(examples),
        "parentPolicy": parent_policy,
        "dollarAbsoluteErrorGain": float(best[0]),
        "left": _build_tree_node(
            X[left_mask],
            left_examples,
            depth=depth + 1,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
        ),
        "right": _build_tree_node(
            X[~left_mask],
            right_examples,
            depth=depth + 1,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
        ),
    }


def _tree_leaf_policy(
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not examples:
        return {
            "leaf": "reference_anchor",
            "alternativeMethod": "reference_anchor",
            "anchorWeight": 1.0,
            "samples": 0,
            "anchorAbsoluteError": 0.0,
            "policyAbsoluteError": 0.0,
            "predictedWapeGain": 0.0,
            "positiveImprovementShare": 0.0,
            "safeSwitchActivated": False,
        }
    actuals = np.asarray([float(item["actual"]) for item in examples], dtype=float)
    anchors = np.asarray(
        [float(item["anchorPrediction"]) for item in examples], dtype=float
    )
    denominator = float(np.abs(actuals).sum())
    anchor_error = float(np.abs(actuals - anchors).sum())
    selected_method = "reference_anchor"
    selected_weight = 1.0
    selected_error = anchor_error
    for method in TREE_ALTERNATIVE_METHODS:
        alternatives = np.asarray(
            [
                float(item["candidatePredictions"][method])
                for item in examples
            ],
            dtype=float,
        )
        for anchor_weight in TREE_ANCHOR_WEIGHTS:
            predictions = (
                float(anchor_weight) * anchors
                + (1.0 - float(anchor_weight)) * alternatives
            )
            error = float(np.abs(actuals - predictions).sum())
            if (
                error < selected_error - 1e-12
                or (
                    abs(error - selected_error) <= 1e-12
                    and (
                        -float(anchor_weight),
                        TREE_ALTERNATIVE_METHODS.index(method),
                    )
                    < (
                        -float(selected_weight),
                        (
                            TREE_ALTERNATIVE_METHODS.index(selected_method)
                            if selected_method in TREE_ALTERNATIVE_METHODS
                            else len(TREE_ALTERNATIVE_METHODS)
                        ),
                    )
                )
            ):
                selected_method = method
                selected_weight = float(anchor_weight)
                selected_error = error
    predicted_gain = (
        (anchor_error - selected_error) / denominator
        if denominator > 0
        else 0.0
    )
    safe_switch = (
        selected_method != "reference_anchor"
        and predicted_gain > SAFE_MIN_WAPE_GAIN
    )
    if not safe_switch:
        selected_method = "reference_anchor"
        selected_weight = 1.0
        selected_error = anchor_error
        predicted_gain = 0.0
    improvements = [
        float(item.get("candidateDollarImprovements", {}).get(selected_method, 0.0))
        for item in examples
    ]
    return {
        "leaf": (
            "reference_anchor"
            if selected_method == "reference_anchor"
            else "anchor_blend"
        ),
        "alternativeMethod": selected_method,
        "anchorWeight": selected_weight,
        "samples": len(examples),
        "anchorAbsoluteError": anchor_error,
        "policyAbsoluteError": selected_error,
        "predictedWapeGain": float(predicted_gain),
        "positiveImprovementShare": float(
            np.mean(np.asarray(improvements) > 0.0)
        ),
        "safeSwitchActivated": safe_switch,
    }


def _predict_tree(
    model: Mapping[str, Any],
    features: Sequence[float],
    candidate_predictions: Mapping[str, float],
) -> tuple[float, str, bool]:
    fallback = model.get("kind") == "cold_start_reference_anchor"
    node = dict(model["tree"])
    while "leaf" not in node:
        feature_index = int(node["featureIndex"])
        branch = "left" if float(features[feature_index]) <= float(node["threshold"]) else "right"
        node = dict(node[branch])
    method = str(node.get("alternativeMethod", "reference_anchor"))
    anchor_weight = float(node.get("anchorWeight", 1.0))
    if method not in candidate_predictions:
        fallback = True
        method = "reference_anchor"
        anchor_weight = 1.0
    elif method == "reference_anchor":
        method = "reference_anchor"
        anchor_weight = 1.0
    anchor = float(candidate_predictions["reference_anchor"])
    alternative = float(candidate_predictions[method])
    prediction = anchor_weight * anchor + (1.0 - anchor_weight) * alternative
    method_label = (
        "reference_anchor"
        if method == "reference_anchor"
        else f"{anchor_weight:.1f}_anchor+{1.0-anchor_weight:.1f}_{method}"
    )
    return max(float(prediction), 0.0), method_label, fallback


def _fit_elastic_model(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(examples) < 18:
        return _zero_elastic_model(
            examples,
            kind="cold_start_reference_anchor",
            selection="cold_start_anchor",
        )
    unique_origins = sorted({str(item["originMonth"]) for item in examples})
    validation_origins = (
        set(unique_origins[-INNER_VALIDATION_ORIGINS:])
        if len(unique_origins) >= INNER_VALIDATION_ORIGINS + 2
        else set()
    )
    train_examples = [
        item for item in examples if str(item["originMonth"]) not in validation_origins
    ]
    validation_examples = [
        item for item in examples if str(item["originMonth"]) in validation_origins
    ]
    if len(train_examples) < 18 or not validation_examples:
        train_examples = list(examples)
        validation_examples = []
    selected = (0.5, 0.75, 0.05)
    best_score = float("inf")
    anchor_score = float("inf")
    if validation_examples:
        anchor_score = _official_total_wape(
            validation_examples,
            [float(item["anchorPrediction"]) for item in validation_examples],
        )
        for alpha in ELASTIC_ALPHA_GRID:
            for l1_ratio in ELASTIC_L1_RATIO_GRID:
                fitted = _fit_coordinate_descent(
                    train_examples,
                    alpha=alpha,
                    l1_ratio=l1_ratio,
                    residual_clip=ELASTIC_RESIDUAL_CLIPS[0],
                )
                for clip in ELASTIC_RESIDUAL_CLIPS:
                    candidate = dict(fitted)
                    candidate["residualClip"] = [-float(clip), float(clip)]
                    predictions = [
                        _predict_elastic(
                            candidate,
                            item["features"],
                            anchor_prediction=float(item["anchorPrediction"]),
                        )[0]
                        for item in validation_examples
                    ]
                    score = _official_total_wape(
                        validation_examples,
                        predictions,
                    )
                    candidate_key = (
                        score,
                        -float(alpha),
                        -float(l1_ratio),
                        float(clip),
                    )
                    selected_key = (
                        best_score,
                        -float(selected[0]),
                        -float(selected[1]),
                        float(selected[2]),
                    )
                    if candidate_key < selected_key:
                        best_score = score
                        selected = (float(alpha), float(l1_ratio), float(clip))
    if (
        not validation_examples
        or not np.isfinite(best_score)
        or not np.isfinite(anchor_score)
        or anchor_score - best_score <= SAFE_MIN_WAPE_GAIN
    ):
        model = _zero_elastic_model(
            examples,
            kind="zero_residual_correction",
            selection=(
                "no_correction_won_last_six_synchronized_origins"
                if validation_examples
                else "no_correction_due_to_short_inner_history"
            ),
        )
        model["validationWape"] = (
            None if not validation_examples else float(anchor_score)
        )
        model["bestCorrectionValidationWape"] = (
            None if not validation_examples else float(best_score)
        )
        model["validationWapeGain"] = (
            None
            if not validation_examples
            else float(anchor_score - best_score)
        )
        return model
    model = _fit_coordinate_descent(
        examples,
        alpha=selected[0],
        l1_ratio=selected[1],
        residual_clip=selected[2],
    )
    model["trainingExamples"] = len(examples)
    model["hyperparameterSelection"] = (
        "last_six_synchronized_origins_official_total_wape"
    )
    model["validationWape"] = float(best_score)
    model["anchorValidationWape"] = float(anchor_score)
    model["validationWapeGain"] = float(anchor_score - best_score)
    return model


def _fit_coordinate_descent(
    examples: Sequence[Mapping[str, Any]],
    *,
    alpha: float,
    l1_ratio: float,
    residual_clip: float,
) -> dict[str, Any]:
    X = np.asarray([item["features"] for item in examples], dtype=float)
    y = np.asarray([float(item["residualTarget"]) for item in examples], dtype=float)
    weights = np.asarray(
        [max(float(item["actual"]), 0.0) for item in examples],
        dtype=float,
    )
    if float(weights.sum()) <= 0:
        weights = np.ones(len(examples), dtype=float)
    weights = weights / float(weights.sum())
    means = np.average(X, axis=0, weights=weights)
    scales = np.sqrt(np.average((X - means) ** 2, axis=0, weights=weights))
    scales = np.where(scales > 1e-12, scales, 1.0)
    standardized = (X - means) / scales
    intercept = float(np.average(y, weights=weights))
    centered_y = y - intercept
    coefficients = np.zeros(standardized.shape[1], dtype=float)
    fitted = np.zeros(len(centered_y), dtype=float)
    column_norms = np.sum(weights[:, None] * standardized**2, axis=0)
    for _ in range(80):
        previous = coefficients.copy()
        for feature_index in range(standardized.shape[1]):
            feature_values = standardized[:, feature_index]
            old_coefficient = coefficients[feature_index]
            residual = centered_y - fitted + feature_values * old_coefficient
            rho = float(np.sum(weights * feature_values * residual))
            denominator = (
                float(column_norms[feature_index])
                + alpha * (1.0 - l1_ratio)
            )
            new_coefficient = (
                _soft_threshold(rho, alpha * l1_ratio) / denominator
                if denominator > 0
                else 0.0
            )
            coefficients[feature_index] = new_coefficient
            fitted += feature_values * (new_coefficient - old_coefficient)
        if float(np.max(np.abs(coefficients - previous))) < 1e-6:
            break
    return {
        "kind": "global_elastic_net_log_residual",
        "featureNames": list(FEATURE_NAMES),
        "alpha": float(alpha),
        "l1Ratio": float(l1_ratio),
        "intercept": intercept,
        "coefficients": coefficients.tolist(),
        "featureMeans": means.tolist(),
        "featureScales": scales.tolist(),
        "residualClip": [-float(residual_clip), float(residual_clip)],
        "sampleWeighting": "actual_revenue_normalized",
    }


def _zero_elastic_model(
    examples: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    selection: str,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "featureNames": list(FEATURE_NAMES),
        "alpha": None,
        "l1Ratio": None,
        "intercept": 0.0,
        "coefficients": [0.0] * len(FEATURE_NAMES),
        "featureMeans": [0.0] * len(FEATURE_NAMES),
        "featureScales": [1.0] * len(FEATURE_NAMES),
        "residualClip": [0.0, 0.0],
        "sampleWeighting": "actual_revenue_normalized",
        "trainingExamples": len(examples),
        "hyperparameterSelection": selection,
    }


def _official_total_wape(
    examples: Sequence[Mapping[str, Any]],
    predictions: Sequence[float],
) -> float:
    if not examples or len(examples) != len(predictions):
        return float("inf")
    frame = pd.DataFrame(
        [
            {
                "originMonth": str(item["originMonth"]),
                "targetMonth": str(item["targetMonth"]),
                "horizon": int(item["horizon"]),
                "entity": str(item["entity"]),
                "actual": float(item["actual"]),
                "prediction": float(prediction),
            }
            for item, prediction in zip(examples, predictions, strict=True)
        ]
    )
    keys = ["originMonth", "targetMonth", "horizon"]
    counts = frame.groupby(keys)["entity"].nunique()
    common_keys = counts[counts == len(OFFICIAL_ANCHORS)].index
    if len(common_keys) == 0:
        return float("inf")
    common = frame.set_index(keys).loc[common_keys].reset_index()
    totals = common.groupby(keys, as_index=False).agg(
        actual=("actual", "sum"),
        prediction=("prediction", "sum"),
    )
    denominator = float(np.abs(totals["actual"]).sum())
    if denominator <= 0:
        return float("inf")
    return float(np.abs(totals["prediction"] - totals["actual"]).sum() / denominator)


def _soft_threshold(value: float, threshold: float) -> float:
    if value > threshold:
        return value - threshold
    if value < -threshold:
        return value + threshold
    return 0.0


def _predict_elastic(
    model: Mapping[str, Any],
    features: Sequence[float],
    *,
    anchor_prediction: float,
) -> tuple[float, bool]:
    fallback = model.get("kind") == "cold_start_reference_anchor"
    if fallback:
        return max(float(anchor_prediction), 0.0), True
    feature_values = np.asarray(features, dtype=float)
    means = np.asarray(model["featureMeans"], dtype=float)
    scales = np.asarray(model["featureScales"], dtype=float)
    coefficients = np.asarray(model["coefficients"], dtype=float)
    standardized = (feature_values - means) / np.where(scales > 0, scales, 1.0)
    residual = float(model["intercept"]) + float(standardized @ coefficients)
    lower, upper = [float(value) for value in model.get("residualClip", [-0.5, 0.5])]
    residual = float(np.clip(residual, lower, upper))
    prediction = math.expm1(math.log1p(max(float(anchor_prediction), 0.0)) + residual)
    return max(float(prediction), 0.0), False


def _build_artifact(
    *,
    model_id: str,
    model: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    source_hash: str,
    training_cutoff: str,
    contract: BacktestContract,
    observed_months: int,
    training_seconds: float,
) -> dict[str, Any]:
    frame = pd.DataFrame(predictions)
    fold_keys = ["origin_month", "target_month", "horizon"]
    counts = frame.groupby(fold_keys)["entity"].nunique()
    common_keys = counts[counts == len(OFFICIAL_ANCHORS)].index
    common = frame.set_index(fold_keys).loc[common_keys].reset_index()
    official_total = (
        common.groupby(fold_keys, as_index=False)
        .agg(actual=("actual", "sum"), prediction=("prediction", "sum"))
    )
    expected = expected_fold_counts(observed_months, contract)
    fold_audit = audit_fold_coverage(
        common,
        expected_entities=set(OFFICIAL_ANCHORS),
        expected_horizon_counts=expected,
    )
    entity_metrics = {
        str(entity): {
            "combined": summarize_predictions(group),
            "byHorizon": {
                str(horizon): summarize_predictions(
                    group[group["horizon"].astype(int) == int(horizon)]
                )
                for horizon in contract.horizons
            },
        }
        for entity, group in common.groupby("entity", sort=True)
    }
    horizon_metrics = {
        str(horizon): summarize_predictions(
            official_total[official_total["horizon"].astype(int) == int(horizon)]
        )
        for horizon in contract.horizons
    }
    official_metrics = summarize_predictions(official_total)
    return {
        "artifactVersion": ARTIFACT_VERSION,
        "modelId": model_id,
        "displayName": (
            "Tree Meta-Selector v1"
            if model_id == TREE_META_SELECTOR_ID
            else "Elastic Net Anchor Residual v1"
        ),
        "status": "challenger",
        "productionDefault": False,
        "target": "pio_revenue",
        "level": "official_total_from_brand_anchors",
        "sourceHash": str(source_hash).lower(),
        "trainingCutoff": str(training_cutoff)[:7],
        "contract": asdict(contract),
        "featureNames": list(FEATURE_NAMES),
        "featureAvailability": list(FEATURE_AVAILABILITY),
        "excludedFeatures": [
            "target-month actual PIO",
            "same-month realized Wholesale",
            "same-month realized Fleet",
            "partial-month July actual",
            "reference workbook forecast values",
        ],
        "preregisteredTuning": {
            "runPolicy": "one frozen implementation followed by one complete outer backtest",
            "safeMinimumWapeGain": SAFE_MIN_WAPE_GAIN,
            "treeAnchorWeights": [1.0, *TREE_ANCHOR_WEIGHTS],
            "elasticAlphaGrid": list(ELASTIC_ALPHA_GRID),
            "elasticL1RatioGrid": list(ELASTIC_L1_RATIO_GRID),
            "elasticResidualClips": list(ELASTIC_RESIDUAL_CLIPS),
            "elasticNoCorrectionCandidate": True,
            "innerValidationOrigins": INNER_VALIDATION_ORIGINS,
            "selectionMetric": "Official Total dollar WAPE",
        },
        "nestedEvaluation": {
            "outerSplit": "expanding rolling-origin H1/H2/H3",
            "innerLabels": (
                "candidate dollar-error improvements and residual targets whose "
                "target month is strictly earlier than the outer origin"
            ),
            "globalPanel": "HMA/GMA/KUS synchronized by origin",
            "randomSplit": False,
            "failedFoldPolicy": "retain every fold; cold start falls back to governed anchor",
        },
        "model": dict(model),
        "evaluation": {
            "officialTotalMetrics": official_metrics,
            "horizonMetrics": horizon_metrics,
            "entityMetrics": entity_metrics,
            "foldAudit": fold_audit,
            "predictions": [dict(row) for row in predictions],
        },
        "runtime": {
            "framework": "numpy",
            "accelerator": "cpu",
            "gpuRequired": False,
            "trainingSecondsForBothModels": float(training_seconds),
            "inferenceMode": "load JSON artifact; never train on page open",
        },
        "reproducibility": {
            "randomSeed": None,
            "deterministic": True,
            "observedCompletedMonths": int(observed_months),
            "officialAnchors": list(OFFICIAL_ANCHORS),
        },
        "promotionDecision": {
            "status": "not_promoted",
            "reason": (
                "PR E models remain challengers until common-fold performance, "
                "bias, stability, coverage, and the 0.005 simplicity tie band are reviewed."
            ),
        },
    }
