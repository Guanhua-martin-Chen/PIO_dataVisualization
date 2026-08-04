from __future__ import annotations

from collections import Counter, OrderedDict
from copy import deepcopy
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from pio_platform.hierarchical_forecasting import (
    build_hierarchical_forecast,
    rolling_origin_residuals,
)
from pio_platform.ets_experiments import VALIDATED_REFERENCE_PORTFOLIO
from pio_platform.backtest_harness import (
    calibrate_held_out_intervals,
    expected_fold_counts,
    summarize_predictions,
)
from pio_platform.fact_table import (
    OFFICIAL_ANCHORS,
    build_kus_channel_baskets,
    normalize_anchor_brand,
)
from pio_platform.model_entities import build_model_lifecycle, normalize_model_name
from pio_platform.ml_challengers import ML_CHALLENGER_IDS, load_ml_challenger_artifact


FORECAST_CENTER_METRICS = {"quantity", "revenue", "wholesale_quantity"}
FORECAST_CENTER_LEVELS = {"brand", "model", "plc", "model_plc"}
FORECAST_CENTER_SURFACES = {
    "all",
    "brand",
    "model",
    "plc",
    "model_plc",
    "exceptions",
    "validation",
    "intervals",
    "allocation_accuracy",
    "leaderboard",
}
BRAND_NAMES = {
    "HMA": "Hyundai Motor America",
    "GMA": "Genesis Motor America",
    "KUS": "Kia US",
}
METRIC_COLUMNS = {"quantity": "installationQuantity", "revenue": "pioRevenue"}
METRIC_LABELS = {
    "quantity": "PIO Quantity",
    "revenue": "PIO Revenue",
    "wholesale_quantity": "Wholesale Quantity",
}
_CACHE_LIMIT = 16
_RESIDUAL_CACHE: OrderedDict[str, dict[str, list[dict[str, Any]]]] = OrderedDict()
_GOVERNANCE_DIAGNOSTIC_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


def build_forecast_center(
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    wholesale_long: pd.DataFrame | None,
    *,
    metric: str,
    level: str,
    surface: str = "all",
    horizon: int = 3,
    use_working_days: bool = True,
    use_seasonality: bool = True,
    tariff_impact_pct: float = 0.0,
    model_strategy: str = "auto",
    min_monthly_volume: float = 5.0,
    top_n: int = 10,
    latest_sales_month_is_complete: bool = False,
    latest_sales_date: pd.Timestamp | None = None,
    include_all_records: bool = False,
    source_hash: str = "",
    evaluation_scope_eligible: bool = False,
    evaluation_scope_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if metric not in FORECAST_CENTER_METRICS:
        raise ValueError(f"Unsupported Forecast Center metric: {metric}")
    if level not in FORECAST_CENTER_LEVELS:
        raise ValueError(f"Unsupported Forecast Center level: {level}")
    if surface not in FORECAST_CENTER_SURFACES:
        raise ValueError(f"Unsupported Forecast Center surface: {surface}")
    if metric == "wholesale_quantity" and level in {"plc", "model_plc"}:
        raise ValueError("Wholesale Quantity is available at Brand and Model levels only.")
    if horizon < 1 or horizon > 12:
        raise ValueError("Forecast horizon must be between 1 and 12 months.")
    if (
        model_strategy == "reference_portfolio"
        or model_strategy in ML_CHALLENGER_IDS
    ) and metric != "revenue":
        raise ValueError(f"{model_strategy} is available only for Revenue.")

    working_day_map = _working_day_map(working_days)
    if metric == "wholesale_quantity":
        source = _prepare_wholesale_facts(wholesale_long, working_days)
        anchor_source = source
        latest_source_date = pd.Timestamp(latest_sales_date) if latest_sales_date is not None and pd.notna(latest_sales_date) else None
        latest_month_complete = latest_sales_month_is_complete
        check_latest_volume = True
    else:
        source = _prepare_pio_anchor_facts(facts)
        target_column = METRIC_COLUMNS[metric]
        if target_column not in source.columns:
            return _empty_payload(metric, level, surface, horizon, top_n)
        source["installationQuantity"] = pd.to_numeric(
            source["installationQuantity"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0)
        source["pioRevenue"] = pd.to_numeric(
            source["pioRevenue"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0)
        anchor_source = source.copy()
        anchor_source["installationQuantity"] = pd.to_numeric(
            source[target_column],
            errors="coerce",
        ).fillna(0.0).clip(lower=0)
        latest_source_date = pd.Timestamp(latest_sales_date) if latest_sales_date is not None and pd.notna(latest_sales_date) else None
        latest_month_complete = latest_sales_month_is_complete
        check_latest_volume = True

    if source.empty:
        return _empty_payload(metric, level, surface, horizon, top_n)

    anchor = build_hierarchical_forecast(
        anchor_source,
        working_days,
        level="brand",
        horizon=horizon,
        use_working_days=(
            True
            if model_strategy == "reference_portfolio"
            or model_strategy in ML_CHALLENGER_IDS
            else use_working_days
        ),
        use_seasonality=(
            True
            if model_strategy == "reference_portfolio"
            or model_strategy in ML_CHALLENGER_IDS
            else use_seasonality
        ),
        tariff_impact_pct=tariff_impact_pct if metric != "wholesale_quantity" else 0.0,
        min_monthly_volume=0.0,
        model_strategy=model_strategy,
        target_metric=metric,
        limit=len(OFFICIAL_ANCHORS),
        latest_month_is_complete=latest_month_complete,
        check_latest_volume=check_latest_volume,
        source_hash=source_hash,
    )
    brand_records = _decorate_brand_anchor(
        anchor,
        anchor_source,
        metric=metric,
        latest_source_date=latest_source_date,
        working_day_map=working_day_map,
    )
    latest_complete_month = anchor["summary"].get("latestCompleteMonth")
    if not latest_complete_month:
        return _empty_payload(metric, level, surface, horizon, top_n)
    needs_model = include_all_records or surface in {
        "all", "model", "plc", "model_plc", "exceptions"
    }
    needs_plc = include_all_records or surface in {"all", "plc", "model_plc", "exceptions"}
    needs_validation = surface in {"all", "validation", "intervals"}
    needs_intervals = surface in {"all", "intervals"}
    needs_allocation_accuracy = surface in {"all", "allocation_accuracy"}
    needs_exceptions = surface in {"all", "exceptions"}

    diagnostic_scope_key = ""
    residual_cache_hit = False
    if needs_validation or needs_allocation_accuracy or needs_exceptions:
        source_signature, working_day_signature = _diagnostic_source_signatures(
            source,
            working_days,
        )
        diagnostic_scope_key = _diagnostic_scope_cache_key(
            source,
            working_days,
            source_signature=source_signature,
            working_day_signature=working_day_signature,
            source_hash=source_hash,
            cutoff=str(latest_complete_month),
            metric=metric,
            model_strategy=model_strategy,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            min_monthly_volume=min_monthly_volume,
            horizon=horizon,
            tariff_impact_pct=tariff_impact_pct,
            latest_sales_date=latest_source_date,
            latest_sales_month_is_complete=latest_month_complete,
            evaluation_scope_eligible=evaluation_scope_eligible,
            evaluation_scope_metadata=evaluation_scope_metadata or {},
        )
        if needs_validation:
            residual_scope_key = _diagnostic_scope_cache_key(
                source,
                working_days,
                source_signature=source_signature,
                working_day_signature=working_day_signature,
                source_hash=source_hash,
                cutoff=str(latest_complete_month),
                metric=metric,
                model_strategy=model_strategy,
                use_working_days=use_working_days,
                use_seasonality=use_seasonality,
                min_monthly_volume=min_monthly_volume,
                horizon=3,
                tariff_impact_pct=0.0,
                latest_sales_date=None,
                latest_sales_month_is_complete=True,
                evaluation_scope_eligible=evaluation_scope_eligible,
                evaluation_scope_metadata=evaluation_scope_metadata or {},
            )
            residual_cache_hit = _attach_cached_strategy_residuals(
                brand_records,
                anchor_source,
                working_day_map,
                cache_key=residual_scope_key,
                latest_complete_month=str(latest_complete_month),
                model_strategy=model_strategy,
                use_working_days=use_working_days,
                use_seasonality=use_seasonality,
                source_hash=source_hash,
            )
    validation_gate = _registered_evidence_gate(
        metric=metric,
        model_strategy=model_strategy,
        source_hash=source_hash,
        latest_complete_month=str(latest_complete_month),
        brand_records=brand_records,
        evaluation_scope_eligible=evaluation_scope_eligible,
        evaluation_scope_metadata=evaluation_scope_metadata or {},
    )
    validation_applies = bool(validation_gate["eligible"])
    if validation_applies:
        for record in brand_records:
            brand_metric = VALIDATED_REFERENCE_PORTFOLIO["brandMetrics"].get(
                str(record.get("brand", ""))
            )
            if brand_metric:
                record["wape"] = brand_metric["wape"]
                record["accuracyPct"] = round(brand_metric["accuracy"] * 100.0, 2)
                record["backtestPoints"] = VALIDATED_REFERENCE_PORTFOLIO["foldCount"]
                record["backtestModel"] = record.get("selectedModel", "")

    model_records: list[dict[str, Any]] = []
    plc_records: list[dict[str, Any]] = []
    top_accessories: list[dict[str, Any]] = []
    if metric == "wholesale_quantity" and needs_model:
        model_records = _allocate_records(
            source,
            metric=metric,
            child_dimensions=["brand", "entityKey", "modelName"],
            parent_dimensions=["brand"],
            parent_records=brand_records,
            latest_complete_month=latest_complete_month,
            working_day_map=working_day_map,
            use_working_days=use_working_days,
            min_monthly_volume=min_monthly_volume,
        )
    elif metric != "wholesale_quantity" and needs_model:
        model_records = _allocate_records(
            source,
            metric=metric,
            child_dimensions=["brand", "entityKey", "modelName"],
            parent_dimensions=["brand"],
            parent_records=brand_records,
            latest_complete_month=latest_complete_month,
            working_day_map=working_day_map,
            use_working_days=use_working_days,
            min_monthly_volume=min_monthly_volume,
        )
        if needs_plc:
            plc_records = _allocate_records(
                source,
                metric=metric,
                child_dimensions=["brand", "entityKey", "modelName", "plc"],
                parent_dimensions=["brand", "entityKey", "modelName"],
                parent_records=model_records,
                latest_complete_month=latest_complete_month,
                working_day_map=working_day_map,
                use_working_days=use_working_days,
                min_monthly_volume=min_monthly_volume,
            )
            top_accessories = _aggregate_top_plcs(
                source,
                plc_records,
                latest_complete_month=latest_complete_month,
                top_n=top_n,
            )

    evaluation_scopes = (
        _evaluation_scopes(
            metric=metric,
            source_hash=source_hash,
            latest_complete_month=str(latest_complete_month),
            brand_records=brand_records,
            validation_gate=validation_gate,
        )
        if needs_validation
        else []
    )
    interval_summary = (
        _apply_prediction_intervals(
            brand_records,
            model_records,
            plc_records,
            evaluation_scopes=evaluation_scopes,
            validation_applies=validation_applies,
        )
        if needs_intervals
        else {
            "nominalCoverage": 0.90,
            "officialTotal": [],
            "brands": [],
            "childCoveragePolicy": "Open Prediction Intervals to calculate interval coverage.",
        }
    )
    cached_governance = (
        _GOVERNANCE_DIAGNOSTIC_CACHE.get(diagnostic_scope_key, {})
        if needs_allocation_accuracy or needs_exceptions
        else {}
    )
    governance_cache_hit = bool(cached_governance)
    cache_changed = False
    if needs_allocation_accuracy and "allocationAccuracy" not in cached_governance:
        cached_governance["allocationAccuracy"] = _allocation_accuracy_diagnostics(
            source,
            metric=metric,
            latest_complete_month=str(latest_complete_month),
            source_hash=source_hash,
        )
        cache_changed = True
    if needs_exceptions and "forecastExceptions" not in cached_governance:
        cached_governance["forecastExceptions"] = _forecast_exceptions(
            source,
            model_records,
            plc_records,
            [],
            metric=metric,
            latest_complete_month=str(latest_complete_month),
            min_monthly_volume=min_monthly_volume,
        )
        cache_changed = True
    if cache_changed:
        _cache_put(_GOVERNANCE_DIAGNOSTIC_CACHE, diagnostic_scope_key, cached_governance)
    elif cached_governance:
        _GOVERNANCE_DIAGNOSTIC_CACHE.move_to_end(diagnostic_scope_key)
    allocation_accuracy = deepcopy(cached_governance.get("allocationAccuracy", []))
    forecast_exceptions = deepcopy(cached_governance.get("forecastExceptions", []))

    if surface in {"validation", "intervals", "allocation_accuracy", "exceptions"}:
        display_records = brand_records
    elif level == "brand":
        display_records = brand_records
    elif level == "model":
        display_records = model_records
    elif level == "plc":
        display_records = top_accessories
    else:
        top_plcs = {str(record["plc"]) for record in top_accessories}
        display_records = [record for record in plc_records if str(record.get("plc", "")) in top_plcs]

    reconciliation = (
        _reconciliation_checks(brand_records, model_records, plc_records)
        if needs_model
        else {
            "status": "NOT_LOADED",
            "brandToModelMaxAbsDelta": 0.0,
            "modelToPlcMaxAbsDelta": 0.0,
            "tolerance": 0.01,
        }
    )
    allocation_routing = _allocation_routing_summary(model_records, plc_records)
    model_counts = Counter(str(record.get("selectedModel", "")) for record in brand_records)
    forecast_months = _forecast_months(brand_records)
    nowcast_months = [
        month
        for month in forecast_months
        if any(
            item.get("month") == month and item.get("forecastType") == "Nowcast"
            for record in brand_records
            for item in record.get("forecast", [])
        )
    ]
    pure_forecast_months = [month for month in forecast_months if month not in nowcast_months]
    summary = {
        "metric": metric,
        "metricLabel": METRIC_LABELS[metric],
        "unit": "USD" if metric == "revenue" else "units",
        "level": level,
        "loadedSurface": surface,
        "seriesCount": len(display_records),
        "allModelSeriesCount": len(model_records),
        "allModelPlcSeriesCount": len(plc_records),
        "topN": top_n,
        "latestCompleteMonth": latest_complete_month,
        "latestObservedMonth": anchor["summary"].get("latestObservedMonth"),
        "dataThrough": latest_source_date.date().isoformat() if latest_source_date is not None else anchor["summary"].get("latestObservedMonth"),
        "latestMonthExcluded": anchor["summary"].get("latestMonthExcluded", False),
        "latestMonthCompletenessRatio": anchor["summary"].get("latestMonthCompletenessRatio"),
        "horizon": horizon,
        "forecastMonths": forecast_months,
        "nowcastMonths": nowcast_months,
        "pureForecastMonths": pure_forecast_months,
        "periodExplanation": _period_explanation(
            latest_complete_month,
            nowcast_months,
            pure_forecast_months,
            latest_source_date,
            working_day_map,
        ),
        "weightedWape": (
            VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["wape"]
            if validation_applies
            else anchor["summary"].get("weightedWape")
        ),
        "accuracyPct": (
            round(VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["accuracy"] * 100.0, 2)
            if validation_applies
            else anchor["summary"].get("accuracyPct")
        ),
        "modelCounts": dict(model_counts),
        "brandDefinition": (
            "Official anchors are HMA, GMA, and KUS. HMA/GMA are assigned by exact dealer-wholesale "
            "model mapping across both source codes; K is used only as a KUS fallback when a model is unmatched. "
            "IONIQ model names remain separate entities."
        ),
        "anchorPolicy": _anchor_policy_summary(source, latest_source_date),
        "allocationRouting": allocation_routing,
        "businessValidation": _business_validation(
            brand_records,
            source,
            wholesale_long,
            reconciliation,
            latest_source_date,
        ),
        "reconciliation": reconciliation,
        "factors": {
            "workingDays": use_working_days,
            "seasonality": use_seasonality,
            "tariffImpactPct": float(tariff_impact_pct if metric != "wholesale_quantity" else 0.0),
            "modelStrategy": model_strategy,
            "minMonthlyVolume": float(min_monthly_volume),
        },
        "formulaCatalog": _formula_catalog(metric),
        "accuracyDefinition": anchor["summary"].get("accuracyDefinition"),
        "accuracyScope": _accuracy_scope(metric),
        "evaluationScopes": evaluation_scopes,
        "registeredEvidenceGate": validation_gate,
        "fairModelComparison": (
            _fair_model_comparison(validation_gate=validation_gate, metric=metric)
            if needs_validation
            else {
                "validationStatus": "not_loaded",
                "comparisonType": "open_method_validation",
                "rows": [],
            }
        ),
        "algorithmLeaderboard": (
            _algorithm_leaderboard(validation_gate=validation_gate, metric=metric)
            if needs_validation
            else {
                "validationStatus": "not_loaded",
                "disclosure": "Open Algorithm Leaderboard to load governed Brand-level evidence.",
                "rows": [],
            }
        ),
        "allocationAccuracy": allocation_accuracy,
        "predictionIntervals": interval_summary,
        "diagnosticCache": {
            "scopeKey": diagnostic_scope_key,
            "residualCacheHit": residual_cache_hit,
            "governanceCacheHit": governance_cache_hit,
        },
        "modelGovernance": _model_governance(
            model_strategy=model_strategy,
            source_hash=source_hash,
            latest_complete_month=latest_complete_month,
            brand_records=brand_records,
            validation_applies=validation_applies,
            validation_gate=validation_gate,
        ),
    }
    payload: dict[str, Any] = {
        "summary": summary,
        "records": display_records,
        "topAccessories": top_accessories,
        "brandRecords": brand_records,
        "forecastExceptions": forecast_exceptions,
    }
    if include_all_records:
        payload["modelRecords"] = model_records
        payload["modelPlcRecords"] = plc_records
    return payload


def build_algorithm_leaderboard_payload(
    *,
    source_hash: str,
    request_cutoff: str | None,
    filters_applied: bool,
    evaluation_scope_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build registered leaderboard evidence without loading or fitting forecast data."""

    payload = _empty_payload("revenue", "brand", "leaderboard", 3, 10)
    gate = _registered_evidence_gate(
        metric="revenue",
        model_strategy="reference_portfolio",
        source_hash=source_hash,
        latest_complete_month=request_cutoff or "",
        brand_records=[{"brand": brand} for brand in OFFICIAL_ANCHORS],
        evaluation_scope_eligible=not filters_applied,
        evaluation_scope_metadata=evaluation_scope_metadata,
    )
    payload["summary"]["registeredEvidenceGate"] = gate
    payload["summary"]["algorithmLeaderboard"] = _algorithm_leaderboard(
        validation_gate=gate,
        metric="revenue",
    )
    payload["summary"]["latestCompleteMonth"] = request_cutoff
    payload["summary"]["modelGovernance"].update(
        {
            "requestedStrategy": "reference_portfolio",
            "sourceHash": source_hash or "unavailable",
            "trainingCutoff": request_cutoff or "",
            "backtestHorizons": [1, 2, 3],
            "evaluationScopeId": gate["evaluationScopeId"],
            "validationGate": gate,
        }
    )
    return payload


def _model_governance(
    *,
    model_strategy: str,
    source_hash: str,
    latest_complete_month: str,
    brand_records: list[dict[str, Any]],
    validation_applies: bool,
    validation_gate: dict[str, Any],
) -> dict[str, Any]:
    if model_strategy == "reference_portfolio":
        status = (
            VALIDATED_REFERENCE_PORTFOLIO["implementationStatus"]
            if validation_applies
            else "validated_implementation_applied_to_unvalidated_source"
        )
        return {
            "requestedStrategy": model_strategy,
            "sourceHash": source_hash or "unavailable",
            "trainingCutoff": latest_complete_month,
            "backtestHorizons": VALIDATED_REFERENCE_PORTFOLIO["backtestHorizons"],
            "foldCount": (
                VALIDATED_REFERENCE_PORTFOLIO["foldCount"] if validation_applies else None
            ),
            "wapeScope": VALIDATED_REFERENCE_PORTFOLIO["wapeScope"],
            "accuracyProxy": (
                VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["accuracy"]
                if validation_applies
                else None
            ),
            "referenceMethodStatus": status,
            "contractVersion": VALIDATED_REFERENCE_PORTFOLIO["contractVersion"],
            "brandSpecificMethods": VALIDATED_REFERENCE_PORTFOLIO["brandMethods"],
            "evaluationScopeId": validation_gate["evaluationScopeId"],
            "validationGate": validation_gate,
        }
    return {
        "requestedStrategy": model_strategy,
        "sourceHash": source_hash or "unavailable",
        "trainingCutoff": latest_complete_month,
        "backtestHorizons": [1],
        "foldCount": sum(int(record.get("backtestPoints", 0)) for record in brand_records),
        "wapeScope": "application outer holdout across selected Brand anchors",
        "accuracyProxy": None,
        "referenceMethodStatus": "not_reference_portfolio",
        "contractVersion": None,
        "brandSpecificMethods": {
            str(record.get("brand", "")): str(record.get("selectedModel", ""))
            for record in brand_records
        },
        "evaluationScopeId": "application_recent_h1",
        "validationGate": validation_gate,
    }


def build_part_planning_records(
    facts: pd.DataFrame,
    model_plc_records: list[dict[str, Any]],
    *,
    metric: str,
    latest_complete_month: str,
) -> list[dict[str, Any]]:
    if metric not in {"quantity", "revenue"} or facts.empty or not model_plc_records:
        return []
    working = _prepare_pio_anchor_facts(facts)
    working["month"] = working["month"].astype(str).str[:7]
    working = working[working["month"] <= latest_complete_month]
    if working.empty:
        return []

    records: list[dict[str, Any]] = []
    for parent in model_plc_records:
        subset = working[
            (working["brand"].astype(str) == str(parent.get("brand", "")))
            & (working["entityKey"].astype(str) == str(parent.get("entityKey", "")))
            & (working["plc"].astype(str) == str(parent.get("plc", "")))
        ].copy()
        parent_forecasts = parent.get("forecast", [])
        if subset.empty:
            if any(float(item.get("value", 0.0)) > 0 for item in parent_forecasts):
                records.extend(_planner_review_part_records(parent))
            continue
        last_month = str(subset["month"].max())
        recent_start = (pd.Period(latest_complete_month, freq="M") - 5).strftime("%Y-%m")
        recent = subset[subset["month"] >= recent_start]
        part_stats = (
            recent.groupby(["partNumber", "partDescription"], as_index=False)
            .agg(
                recentQuantity=("installationQuantity", "sum"),
                recentRevenue=("pioRevenue", "sum"),
            )
        )
        latest_stats = (
            subset[subset["month"] == last_month]
            .groupby(["partNumber", "partDescription"], as_index=False)
            .agg(latestQuantity=("installationQuantity", "sum"), latestRevenue=("pioRevenue", "sum"))
        )
        stats = part_stats.merge(latest_stats, on=["partNumber", "partDescription"], how="outer").fillna(0.0)
        part_monthly = (
            subset.groupby(["partNumber", "partDescription", "month"], as_index=False)
            .agg(quantity=("installationQuantity", "sum"))
        )
        part_eligibility = (
            part_monthly.groupby(["partNumber", "partDescription"], as_index=False)
            .agg(
                activeMonths=("quantity", lambda values: int((values > 0).sum())),
                firstMonth=("month", "min"),
                historyQuantity=("quantity", "sum"),
            )
        )
        part_eligibility["historyMonths"] = part_eligibility["firstMonth"].map(
            lambda month: max(
                1,
                pd.Period(latest_complete_month, freq="M").ordinal - pd.Period(str(month), freq="M").ordinal + 1,
            )
        )
        part_eligibility["monthlyAverage"] = (
            part_eligibility["historyQuantity"]
            / part_eligibility["historyMonths"].clip(lower=1)
        )
        stats = stats.merge(
            part_eligibility[
                ["partNumber", "partDescription", "activeMonths", "historyMonths", "monthlyAverage"]
            ],
            on=["partNumber", "partDescription"],
            how="left",
        ).fillna(0.0)
        parent_route = str(parent.get("allocationRoute", "regular_allocation"))
        if parent_route == "new_model_proxy":
            stats["eligible"] = (stats["recentQuantity"] > 0) & (stats["monthlyAverage"] >= 5.0)
        else:
            stats["eligible"] = (stats["activeMonths"] >= 6) & (stats["monthlyAverage"] >= 5.0)
        stats["expectedUnitRevenue"] = np.where(
            stats["recentQuantity"] > 0,
            stats["recentRevenue"] / stats["recentQuantity"],
            0.0,
        )
        if metric == "quantity":
            stats["rawWeight"] = stats["latestQuantity"]
            if float(stats["rawWeight"].sum()) <= 0:
                stats["rawWeight"] = stats["recentQuantity"]
        else:
            stats["rawWeight"] = stats["latestQuantity"] * stats["expectedUnitRevenue"]
            if float(stats["rawWeight"].sum()) <= 0:
                stats["rawWeight"] = stats["recentQuantity"] * stats["expectedUnitRevenue"]
        stats.loc[~stats["eligible"], "rawWeight"] = 0.0
        if float(stats["rawWeight"].sum()) <= 0:
            if any(float(item.get("value", 0.0)) > 0 for item in parent_forecasts):
                records.extend(_planner_review_part_records(parent))
            continue
        stats["share"] = stats["rawWeight"] / float(stats["rawWeight"].sum())
        stats = stats[stats["eligible"]].copy()
        stats = stats.sort_values(
            ["rawWeight", "recentRevenue", "recentQuantity", "partNumber"],
            ascending=[False, False, False, True],
            kind="stable",
        ).reset_index(drop=True)

        for _, part in stats.iterrows():
            for forecast in parent.get("forecast", []):
                records.append(
                    {
                        "month": forecast["month"],
                        "forecastType": forecast.get("forecastType", "Forecast"),
                        "brand": parent.get("brand", ""),
                        "brandName": parent.get("brandName", ""),
                        "modelName": parent.get("modelName", ""),
                        "entityKey": parent.get("entityKey", ""),
                        "plc": parent.get("plc", ""),
                        "partNumber": str(part["partNumber"]),
                        "partDescription": str(part["partDescription"]),
                        "allocationBasisMonth": last_month,
                        "allocationShare": float(part["share"]),
                        "allocationRoute": parent_route,
                        "expectedUnitRevenue": float(part["expectedUnitRevenue"]),
                        "value": float(forecast["value"]) * float(part["share"]),
                        "lower": max(
                            0.0,
                            float(forecast.get("lower", forecast["value"]))
                            * float(part["share"]),
                        ),
                        "point": float(forecast["value"]) * float(part["share"]),
                        "upper": max(
                            float(forecast["value"]) * float(part["share"]),
                            float(forecast.get("upper", forecast["value"]))
                            * float(part["share"]),
                        ),
                        "nominalCoverage": 0.90,
                        "empiricalCoverage": None,
                        "coverageSampleCount": 0,
                        "calibrationResidualCount": 0,
                        "calibrationScopeId": "allocation_band::pis_pno",
                        "validationStatus": "unvalidated_child_interval_coverage",
                    }
                )
    return records


def _prepare_pio_anchor_facts(facts: pd.DataFrame) -> pd.DataFrame:
    working = facts.copy()
    if "anchorBrand" not in working.columns:
        working["anchorBrand"] = [
            normalize_anchor_brand("", model_name=model, source_brand=brand)
            for brand, model in zip(
                working.get("brand", pd.Series("", index=working.index)),
                working.get("modelName", pd.Series("", index=working.index)),
                strict=False,
            )
        ]
    if "anchorMappingMethod" not in working.columns:
        working["anchorMappingMethod"] = [
            "source_brand_kus"
            if normalize_model_name(brand) in {"K", "KUS"}
            else "hma_default_fallback"
            for brand in working.get("brand", pd.Series("", index=working.index))
        ]
    working["sourceBrand"] = working.get("brand", "")
    working["brand"] = working["anchorBrand"].fillna("").astype(str)
    return working[working["brand"].isin(OFFICIAL_ANCHORS)].copy()


def _planner_review_part_records(parent: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "month": forecast["month"],
            "forecastType": forecast.get("forecastType", "Forecast"),
            "brand": parent.get("brand", ""),
            "brandName": parent.get("brandName", ""),
            "modelName": parent.get("modelName", ""),
            "entityKey": parent.get("entityKey", ""),
            "plc": parent.get("plc", ""),
            "partNumber": "PLANNER_REVIEW",
            "partDescription": "Unallocated low-volume / lifecycle residual",
            "allocationBasisMonth": None,
            "allocationShare": 1.0,
            "allocationRoute": "planner_review_residual",
            "expectedUnitRevenue": float(parent.get("expectedUnitRevenue") or 0.0),
            "value": float(forecast.get("value", 0.0)),
            "lower": max(0.0, float(forecast.get("lower", forecast.get("value", 0.0)))),
            "point": float(forecast.get("value", 0.0)),
            "upper": max(
                float(forecast.get("value", 0.0)),
                float(forecast.get("upper", forecast.get("value", 0.0))),
            ),
            "nominalCoverage": 0.90,
            "empiricalCoverage": None,
            "coverageSampleCount": 0,
            "calibrationResidualCount": 0,
            "calibrationScopeId": "allocation_band::pis_pno",
            "validationStatus": "unvalidated_child_interval_coverage",
        }
        for forecast in parent.get("forecast", [])
    ]


def _decorate_brand_anchor(
    anchor: dict[str, Any],
    source: pd.DataFrame,
    *,
    metric: str,
    latest_source_date: pd.Timestamp | None,
    working_day_map: dict[str, float],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    latest_observed = str(anchor["summary"].get("latestObservedMonth") or "")
    incomplete = bool(anchor["summary"].get("latestMonthExcluded")) and latest_source_date is not None
    completion = _estimated_working_day_completion(latest_source_date, working_day_map) if incomplete else None
    current_actual = (
        source[source["month"].astype(str).str[:7] == latest_observed]
        .groupby("brand")["installationQuantity"]
        .sum()
        .to_dict()
        if latest_observed
        else {}
    )
    for raw in anchor.get("records", []):
        record = dict(raw)
        brand = str(record.get("brand", ""))
        record["brandName"] = BRAND_NAMES.get(brand, brand)
        record["metric"] = metric
        decorated_forecast: list[dict[str, Any]] = []
        for item in record.get("forecast", []):
            decorated = dict(item)
            decorated["forecastType"] = "Forecast"
            decorated["actualToDate"] = None
            decorated["workingDays"] = working_day_map.get(str(item["month"]))
            decorated["estimatedElapsedWorkingDays"] = None
            if incomplete and str(item["month"]) == latest_observed and completion is not None:
                actual = float(current_actual.get(brand, 0.0))
                baseline = float(item["value"])
                ratio = float(completion["completionRatio"])
                decorated["value"] = max(0.0, actual + (1.0 - ratio) * baseline)
                decorated["forecastType"] = "Nowcast"
                decorated["actualToDate"] = actual
                decorated["workingDays"] = completion["workingDays"]
                decorated["estimatedElapsedWorkingDays"] = completion["estimatedElapsedWorkingDays"]
                decorated["completionRatio"] = ratio
                decorated["calendarWeekdaysElapsed"] = completion["calendarWeekdaysElapsed"]
                decorated["calendarWeekdaysInMonth"] = completion["calendarWeekdaysInMonth"]
                decorated["statisticalBaseline"] = baseline
            decorated_forecast.append(decorated)
        record["forecast"] = decorated_forecast
        record["nextForecast"] = float(decorated_forecast[0]["value"]) if decorated_forecast else 0.0
        records.append(record)
    return records


def _allocate_records(
    facts: pd.DataFrame,
    *,
    metric: str,
    child_dimensions: list[str],
    parent_dimensions: list[str],
    parent_records: list[dict[str, Any]],
    latest_complete_month: str,
    working_day_map: dict[str, float],
    use_working_days: bool,
    min_monthly_volume: float,
) -> list[dict[str, Any]]:
    if facts.empty or not parent_records:
        return []
    working = facts.copy()
    working["month"] = working["month"].astype(str).str[:7]
    working = working[working["month"] <= latest_complete_month]
    if working.empty:
        return []
    for column in ["installationQuantity", "pioRevenue"]:
        if column not in working.columns:
            working[column] = 0.0
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0).clip(lower=0)
    if "lifecycleStatus" not in working.columns:
        working["lifecycleStatus"] = "Unknown"
    if "lifecycleStatusCode" not in working.columns:
        working["lifecycleStatusCode"] = working["lifecycleStatus"].map(_lifecycle_code_from_label)
    for dimension in child_dimensions:
        if dimension not in working.columns:
            working[dimension] = ""

    monthly = (
        working.groupby(child_dimensions + ["month"], as_index=False, dropna=False)
        .agg(
            installationQuantity=("installationQuantity", "sum"),
            pioRevenue=("pioRevenue", "sum"),
        )
    )
    metadata = (
        working.groupby(child_dimensions, as_index=False, dropna=False)
        .agg(
            lifecycleStatus=("lifecycleStatus", _mode_text),
            lifecycleStatusCode=("lifecycleStatusCode", _mode_text),
            historyQuantity=("installationQuantity", "sum"),
            historyRevenue=("pioRevenue", "sum"),
        )
    )
    activity = (
        monthly.groupby(child_dimensions, as_index=False, dropna=False)
        .agg(
            activeMonths=("installationQuantity", lambda values: int((values > 0).sum())),
            firstMonth=("month", "min"),
        )
    )
    metadata = metadata.merge(activity, on=child_dimensions, how="left")
    metadata["historyMonths"] = metadata["firstMonth"].map(
        lambda month: max(
            1,
            pd.Period(latest_complete_month, freq="M").ordinal - pd.Period(str(month), freq="M").ordinal + 1,
        )
    )
    metadata["monthlyAverage"] = (
        metadata["historyQuantity"] / metadata["historyMonths"].clip(lower=1)
    )
    parent_prices = _parent_unit_prices(working, parent_dimensions, latest_complete_month)
    forecast_months = _forecast_months(parent_records)
    raw_records: list[dict[str, Any]] = []
    grouped = monthly.groupby(child_dimensions[0] if len(child_dimensions) == 1 else child_dimensions, dropna=False)
    for raw_key, group in grouped:
        key_values = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        dimensions = dict(zip(child_dimensions, key_values, strict=False))
        meta_mask = pd.Series(True, index=metadata.index)
        for column, value in dimensions.items():
            meta_mask &= metadata[column].fillna("").astype(str) == str(value)
        meta = metadata.loc[meta_mask].iloc[0] if meta_mask.any() else None
        parent_key = tuple(str(dimensions.get(column, "")) for column in parent_dimensions)
        parent_price = parent_prices.get(parent_key, 0.0)
        expected_price = _expected_unit_price(group, parent_price)
        lifecycle_status = str(meta["lifecycleStatus"]) if meta is not None else "Unknown"
        lifecycle_status_code = str(meta["lifecycleStatusCode"]).lower() if meta is not None else "unknown"
        active_months = int(meta["activeMonths"]) if meta is not None else 0
        history_months = int(meta["historyMonths"]) if meta is not None else 0
        monthly_average = float(meta["monthlyAverage"]) if meta is not None else 0.0
        allocation_route = _allocation_route(
            lifecycle_status_code=lifecycle_status_code,
            lifecycle_status=lifecycle_status,
            active_months=active_months,
            history_months=history_months,
            monthly_average=monthly_average,
            min_monthly_volume=min_monthly_volume,
        )
        raw_forecast = []
        for month in forecast_months:
            if allocation_route in {"excluded_lifecycle", "excluded_low_volume"}:
                signal = 0.0
            else:
                signal = _allocation_signal(
                    group,
                    month,
                    metric=metric,
                    expected_unit_price=expected_price,
                    working_day_map=working_day_map,
                    use_working_days=use_working_days,
                    use_seasonal_blend=allocation_route == "regular_allocation",
                )
            raw_forecast.append({"month": month, "rawSignal": max(0.0, float(signal))})
        history_volume = float(meta["historyRevenue"] if metric == "revenue" else meta["historyQuantity"]) if meta is not None else 0.0
        record = {
            "seriesKey": "::".join(str(dimensions.get(column, "")) for column in child_dimensions),
            "level": "model_plc" if "plc" in child_dimensions else "model",
            "metric": metric,
            "brand": str(dimensions.get("brand", "")),
            "brandName": BRAND_NAMES.get(str(dimensions.get("brand", "")), str(dimensions.get("brand", ""))),
            "entityKey": str(dimensions.get("entityKey", "")),
            "modelName": str(dimensions.get("modelName", "")),
            "plc": str(dimensions.get("plc", "")),
            "lifecycleStatus": lifecycle_status,
            "lifecycleStatusCode": lifecycle_status_code,
            "allocationRoute": allocation_route,
            "forecastEligible": allocation_route not in {"excluded_lifecycle", "excluded_low_volume"},
            "activeMonths": active_months,
            "historyMonths": history_months,
            "monthlyAverage": monthly_average,
            "historyVolume": history_volume,
            "historyQuantity": float(meta["historyQuantity"]) if meta is not None else 0.0,
            "historyRevenue": float(meta["historyRevenue"]) if meta is not None else 0.0,
            "expectedUnitRevenue": expected_price if metric == "revenue" else None,
            "selectedModel": (
                "new_model_proxy"
                if allocation_route == "new_model_proxy"
                else "excluded"
                if allocation_route.startswith("excluded_")
                else "reconciled_allocation"
            ),
            "selectionNote": _allocation_selection_note(allocation_route, min_monthly_volume),
            "wape": None,
            "accuracyPct": None,
            "rawForecast": raw_forecast,
        }
        raw_records.append(record)

    parent_lookup = {
        tuple(str(record.get(column, "")) for column in parent_dimensions): record
        for record in parent_records
    }
    existing_children: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in raw_records:
        parent_key = tuple(str(record.get(column, "")) for column in parent_dimensions)
        existing_children.setdefault(parent_key, []).append(record)
    for parent_key, parent in parent_lookup.items():
        children = existing_children.get(parent_key, [])
        if not any(
            child.get("allocationRoute") not in {"excluded_lifecycle", "excluded_low_volume"}
            for child in children
        ):
            raw_records.append(
                _planner_review_child(
                    parent_key,
                    parent_dimensions=parent_dimensions,
                    child_dimensions=child_dimensions,
                    metric=metric,
                    forecast_months=forecast_months,
                )
            )
    for month in forecast_months:
        grouped_children: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for record in raw_records:
            parent_key = tuple(str(record.get(column, "")) for column in parent_dimensions)
            grouped_children.setdefault(parent_key, []).append(record)
        for parent_key, children in grouped_children.items():
            parent = parent_lookup.get(parent_key)
            if parent is None:
                continue
            parent_forecast = next(
                (item for item in parent.get("forecast", []) if str(item.get("month")) == month),
                None,
            )
            if parent_forecast is None:
                continue
            parent_value = float(parent_forecast.get("value", 0.0))
            eligible_children = [
                child
                for child in children
                if child.get("allocationRoute") not in {"excluded_lifecycle", "excluded_low_volume"}
            ]
            raw_values = [
                float(next(item["rawSignal"] for item in child["rawForecast"] if item["month"] == month))
                for child in children
            ]
            raw_total = float(sum(raw_values))
            if raw_total <= 0 and eligible_children:
                history_values = [
                    max(float(child["historyVolume"]), 0.0)
                    if child in eligible_children
                    else 0.0
                    for child in children
                ]
                history_total = float(sum(history_values))
                raw_values = (
                    history_values
                    if history_total > 0
                    else [1.0 if child in eligible_children else 0.0 for child in children]
                )
                raw_total = float(sum(raw_values))
            factor = parent_value / raw_total if raw_total > 0 else 0.0
            for child, raw_value in zip(children, raw_values, strict=False):
                share = raw_value / raw_total if raw_total > 0 else 0.0
                child.setdefault("forecast", []).append(
                    {
                        "month": month,
                        "value": max(0.0, raw_value * factor),
                        "forecastType": parent_forecast.get("forecastType", "Forecast"),
                        "allocationShare": share,
                        "reconciliationFactor": factor,
                        "parentForecast": parent_value,
                    }
                )
    for record in raw_records:
        record["nextForecast"] = float(record.get("forecast", [{}])[0].get("value", 0.0)) if record.get("forecast") else 0.0
        record.pop("rawForecast", None)
    return sorted(raw_records, key=lambda record: float(record.get("historyVolume", 0.0)), reverse=True)


def _allocation_route(
    *,
    lifecycle_status_code: str,
    lifecycle_status: str,
    active_months: int,
    history_months: int,
    monthly_average: float,
    min_monthly_volume: float,
) -> str:
    stopped = lifecycle_status_code in {"discontinued", "inactive"} or lifecycle_status.startswith(
        ("Discontinued through", "Inactive")
    )
    if stopped:
        return "excluded_lifecycle"
    if lifecycle_status_code in {"new", "reintroduced"} or history_months < 18:
        return "new_model_proxy" if monthly_average >= min_monthly_volume else "excluded_low_volume"
    if active_months < 6 or monthly_average < min_monthly_volume:
        return "excluded_low_volume"
    return "regular_allocation"


def _allocation_selection_note(route: str, min_monthly_volume: float) -> str:
    if route == "excluded_lifecycle":
        return "Inactive/discontinued series is held at zero and does not receive parent allocation."
    if route == "excluded_low_volume":
        return (
            f"Series is excluded from the forecast mix because average monthly quantity is below "
            f"{min_monthly_volume:g} or it lacks six active months."
        )
    if route == "new_model_proxy":
        return "New/reintroduced series uses a recent run-rate proxy and is not fitted with a seasonal/OLS model."
    if route == "planner_review_residual":
        return "No eligible child series exists; value is held in a transparent planner-review residual."
    return "Recent/seasonal quantity signal is allocated to the official parent and reconciled exactly."


def _planner_review_child(
    parent_key: tuple[str, ...],
    *,
    parent_dimensions: list[str],
    child_dimensions: list[str],
    metric: str,
    forecast_months: list[str],
) -> dict[str, Any]:
    dimensions = dict(zip(parent_dimensions, parent_key, strict=False))
    if "modelName" in child_dimensions and "modelName" not in dimensions:
        dimensions["modelName"] = "Planner review residual"
        dimensions["entityKey"] = f"{dimensions.get('brand', '')}::PLANNER_REVIEW_RESIDUAL"
    if "plc" in child_dimensions and "plc" not in dimensions:
        dimensions["plc"] = "Planner review residual"
    brand = str(dimensions.get("brand", ""))
    return {
        "seriesKey": "::".join(str(dimensions.get(column, "")) for column in child_dimensions),
        "level": "model_plc" if "plc" in child_dimensions else "model",
        "metric": metric,
        "brand": brand,
        "brandName": BRAND_NAMES.get(brand, brand),
        "entityKey": str(dimensions.get("entityKey", "")),
        "modelName": str(dimensions.get("modelName", "")),
        "plc": str(dimensions.get("plc", "")),
        "lifecycleStatus": "Planner review",
        "lifecycleStatusCode": "planner_review",
        "allocationRoute": "planner_review_residual",
        "forecastEligible": False,
        "activeMonths": 0,
        "historyMonths": 0,
        "monthlyAverage": 0.0,
        "historyVolume": 0.0,
        "historyQuantity": 0.0,
        "historyRevenue": 0.0,
        "expectedUnitRevenue": None,
        "selectedModel": "planner_review_residual",
        "selectionNote": _allocation_selection_note("planner_review_residual", 0.0),
        "wape": None,
        "accuracyPct": None,
        "rawForecast": [{"month": month, "rawSignal": 1.0} for month in forecast_months],
    }


def _aggregate_top_plcs(
    facts: pd.DataFrame,
    plc_records: list[dict[str, Any]],
    *,
    latest_complete_month: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if facts.empty or not plc_records:
        return []
    historical = facts[facts["month"].astype(str).str[:7] <= latest_complete_month].copy()
    historical["pioRevenue"] = pd.to_numeric(historical["pioRevenue"], errors="coerce").fillna(0.0)
    history_by_plc = historical.groupby("plc")["pioRevenue"].sum().to_dict()
    total_history_revenue = float(sum(max(float(value), 0.0) for value in history_by_plc.values()))
    aggregated: dict[str, dict[str, Any]] = {}
    for record in plc_records:
        plc = str(record.get("plc", ""))
        if not plc:
            continue
        item = aggregated.setdefault(
            plc,
            {
                "seriesKey": f"PLC::{plc}",
                "level": "plc",
                "plc": plc,
                "brand": "All",
                "brandName": "All brands",
                "modelName": "All models",
                "historyRevenue": float(history_by_plc.get(plc, 0.0)),
                "forecast": {},
            },
        )
        for forecast in record.get("forecast", []):
            month = str(forecast["month"])
            month_item = item["forecast"].setdefault(
                month,
                {"month": month, "value": 0.0, "forecastType": forecast.get("forecastType", "Forecast")},
            )
            month_item["value"] += float(forecast.get("value", 0.0))
    ranked = sorted(aggregated.values(), key=lambda item: float(item["historyRevenue"]), reverse=True)
    result: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked[:top_n], start=1):
        forecasts = [item["forecast"][month] for month in sorted(item["forecast"])]
        result.append(
            {
                **{key: value for key, value in item.items() if key != "forecast"},
                "rank": rank,
                "historyRevenueSharePct": (
                    float(item["historyRevenue"]) / total_history_revenue * 100.0
                    if total_history_revenue > 0
                    else 0.0
                ),
                "selectedModel": "reconciled_allocation",
                "selectionNote": "Sum of all reconciled Brand x Model x PLC records.",
                "wape": None,
                "accuracyPct": None,
                "forecast": forecasts,
                "nextForecast": float(forecasts[0]["value"]) if forecasts else 0.0,
            }
        )
    return result


def _prepare_wholesale_facts(
    wholesale_long: pd.DataFrame | None,
    working_days: pd.DataFrame | None,
) -> pd.DataFrame:
    if wholesale_long is None or wholesale_long.empty:
        return pd.DataFrame()
    working = wholesale_long.copy()
    working["month"] = working["month"].astype(str).str[:7]
    working["modelName"] = working.get("modelName", "").fillna("").astype(str).str.strip()
    if "anchorBrand" in working.columns:
        working["brand"] = working["anchorBrand"].fillna("").astype(str)
    else:
        working["brand"] = [
            normalize_anchor_brand(brand, model_name=model)
            for brand, model in zip(
                working.get("brand", pd.Series("", index=working.index)),
                working["modelName"],
                strict=False,
            )
        ]
    working = working[working["brand"].isin(BRAND_NAMES)]
    working["entityKey"] = [
        f"{brand}::{normalize_model_name(model)}"
        for brand, model in zip(working["brand"], working["modelName"], strict=False)
    ]
    working["installationQuantity"] = pd.to_numeric(working["wholesaleUnits"], errors="coerce").fillna(0.0).clip(lower=0)
    working["anchorBrand"] = working["brand"]
    working["anchorMappingMethod"] = "dealer_wholesale_exact"
    working["sourceBrand"] = working["brand"]
    working["pioRevenue"] = 0.0
    working["plc"] = ""
    working["partNumber"] = ""
    working["partDescription"] = ""
    lifecycle = build_model_lifecycle(
        working,
        pd.to_datetime(working["month"] + "-01", errors="coerce"),
        model_col="modelName",
        qty_col="installationQuantity",
        brand_col="brand",
        model_code_col="modelCode" if "modelCode" in working.columns else None,
        cutoff_year=2024,
    )
    lifecycle_frame = pd.DataFrame(lifecycle.get("records", []))
    if lifecycle_frame.empty:
        working["lifecycleStatus"] = "Active"
        working["lifecycleStatusCode"] = "active"
    else:
        lifecycle_frame = lifecycle_frame.drop_duplicates("entityKey").set_index("entityKey")
        working["lifecycleStatus"] = (
            working["entityKey"].map(lifecycle_frame["status"]).fillna("Active")
        )
        working["lifecycleStatusCode"] = (
            working["entityKey"].map(lifecycle_frame["statusCode"]).fillna("active")
        )
    if working_days is not None and not working_days.empty:
        working = working.merge(working_days[["month", "workingDays"]], on="month", how="left")
    else:
        working["workingDays"] = pd.NA
    return working


def _allocation_signal(
    group: pd.DataFrame,
    forecast_month: str,
    *,
    metric: str,
    expected_unit_price: float,
    working_day_map: dict[str, float],
    use_working_days: bool,
    use_seasonal_blend: bool = True,
) -> float:
    values_column = "installationQuantity"
    group = group.sort_values("month")
    latest_month = pd.Period(str(group["month"].max()), freq="M")
    lookback = 6 if use_seasonal_blend else 3
    recent_months = [
        (latest_month - offset).strftime("%Y-%m")
        for offset in range(lookback - 1, -1, -1)
    ]
    recent_series = group.set_index("month")[values_column].reindex(recent_months, fill_value=0.0)
    recent_base = float(recent_series.mean())
    future_days = float(working_day_map.get(forecast_month, np.mean(list(working_day_map.values())) if working_day_map else 21.0))
    recent_days = [working_day_map.get(month) for month in recent_months if working_day_map.get(month)]
    recent_day_mean = float(np.mean(recent_days)) if recent_days else future_days
    recent_adjusted = recent_base * (future_days / recent_day_mean) if use_working_days and recent_day_mean > 0 else recent_base

    forecast_month_number = int(forecast_month[-2:])
    seasonal = group[group["month"].astype(str).str[-2:].astype(int) == forecast_month_number]
    if use_seasonal_blend and len(seasonal) >= 2:
        seasonal_base = float(seasonal[values_column].mean())
        seasonal_days = [working_day_map.get(str(month)) for month in seasonal["month"] if working_day_map.get(str(month))]
        seasonal_day_mean = float(np.mean(seasonal_days)) if seasonal_days else future_days
        seasonal_adjusted = seasonal_base * (future_days / seasonal_day_mean) if use_working_days and seasonal_day_mean > 0 else seasonal_base
        raw_quantity = 0.60 * seasonal_adjusted + 0.40 * recent_adjusted
    else:
        raw_quantity = recent_adjusted
    if metric == "revenue":
        return raw_quantity * max(expected_unit_price, 0.0)
    return raw_quantity


def _expected_unit_price(group: pd.DataFrame, fallback: float) -> float:
    recent = group.sort_values("month").tail(3)
    quantity = float(recent["installationQuantity"].sum())
    revenue = float(recent["pioRevenue"].sum())
    if quantity > 0 and revenue > 0:
        return revenue / quantity
    quantity = float(group["installationQuantity"].sum())
    revenue = float(group["pioRevenue"].sum())
    return revenue / quantity if quantity > 0 and revenue > 0 else max(float(fallback), 0.0)


def _parent_unit_prices(
    facts: pd.DataFrame,
    parent_dimensions: list[str],
    latest_complete_month: str,
) -> dict[tuple[str, ...], float]:
    latest = pd.Period(latest_complete_month, freq="M")
    start = (latest - 5).strftime("%Y-%m")
    recent = facts[facts["month"].astype(str).str[:7] >= start]
    grouped = (
        recent.groupby(parent_dimensions, as_index=False, dropna=False)
        .agg(quantity=("installationQuantity", "sum"), revenue=("pioRevenue", "sum"))
    )
    prices = {}
    for _, row in grouped.iterrows():
        key = tuple(str(row[column]) for column in parent_dimensions)
        quantity = float(row["quantity"])
        prices[key] = float(row["revenue"]) / quantity if quantity > 0 else 0.0
    return prices


def _estimated_working_day_completion(
    latest_date: pd.Timestamp,
    working_day_map: dict[str, float],
) -> dict[str, float] | None:
    month = latest_date.strftime("%Y-%m")
    total_working_days = working_day_map.get(month)
    if not total_working_days or total_working_days <= 0:
        return None
    month_start = latest_date.replace(day=1).normalize()
    month_end = (month_start + pd.offsets.MonthEnd(0)).normalize()
    calendar_elapsed = len(pd.bdate_range(month_start, latest_date.normalize()))
    calendar_total = len(pd.bdate_range(month_start, month_end))
    ratio = min(1.0, max(0.0, calendar_elapsed / max(calendar_total, 1)))
    return {
        "workingDays": float(total_working_days),
        "estimatedElapsedWorkingDays": float(total_working_days) * ratio,
        "completionRatio": ratio,
        "calendarWeekdaysElapsed": float(calendar_elapsed),
        "calendarWeekdaysInMonth": float(calendar_total),
    }


def _reconciliation_checks(
    brand_records: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    plc_records: list[dict[str, Any]],
) -> dict[str, Any]:
    brand_to_model_max = _max_reconciliation_delta(brand_records, model_records, ["brand"])
    model_to_plc_max = _max_reconciliation_delta(model_records, plc_records, ["brand", "entityKey", "modelName"]) if plc_records else 0.0
    max_delta = max(brand_to_model_max, model_to_plc_max)
    return {
        "status": "PASS" if max_delta <= 0.01 else "FAIL",
        "brandToModelMaxAbsDelta": brand_to_model_max,
        "modelToPlcMaxAbsDelta": model_to_plc_max,
        "tolerance": 0.01,
    }


def _max_reconciliation_delta(
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    parent_dimensions: list[str],
) -> float:
    if not parents or not children:
        return 0.0
    child_totals: dict[tuple[tuple[str, ...], str], float] = {}
    for child in children:
        key = tuple(str(child.get(column, "")) for column in parent_dimensions)
        for forecast in child.get("forecast", []):
            item_key = (key, str(forecast["month"]))
            child_totals[item_key] = child_totals.get(item_key, 0.0) + float(forecast["value"])
    deltas = []
    for parent in parents:
        key = tuple(str(parent.get(column, "")) for column in parent_dimensions)
        for forecast in parent.get("forecast", []):
            child_value = child_totals.get((key, str(forecast["month"])), 0.0)
            deltas.append(abs(float(forecast["value"]) - child_value))
    return max(deltas, default=0.0)


def _forecast_months(records: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(item["month"])
            for record in records
            for item in record.get("forecast", [])
        }
    )


def _working_day_map(working_days: pd.DataFrame | None) -> dict[str, float]:
    if working_days is None or working_days.empty:
        return {}
    return {
        str(row["month"])[:7]: float(row["workingDays"])
        for _, row in working_days.dropna(subset=["month", "workingDays"]).iterrows()
    }


def _lifecycle_code_from_label(value: Any) -> str:
    label = str(value or "").strip().lower()
    if label.startswith("discontinued"):
        return "discontinued"
    if label.startswith("inactive"):
        return "inactive"
    if label.startswith("new"):
        return "new"
    if label.startswith("reintroduced"):
        return "reintroduced"
    if label.startswith("active"):
        return "active"
    return "unknown"


def _allocation_routing_summary(
    model_records: list[dict[str, Any]],
    plc_records: list[dict[str, Any]],
) -> dict[str, Any]:
    def counts(records: list[dict[str, Any]]) -> dict[str, int]:
        return dict(Counter(str(record.get("allocationRoute", "unknown")) for record in records))

    model_counts = counts(model_records)
    plc_counts = counts(plc_records)
    return {
        "model": model_counts,
        "plc": plc_counts,
        "excludedModelSeries": model_counts.get("excluded_low_volume", 0) + model_counts.get("excluded_lifecycle", 0),
        "excludedPlcSeries": plc_counts.get("excluded_low_volume", 0) + plc_counts.get("excluded_lifecycle", 0),
        "newModelProxySeries": model_counts.get("new_model_proxy", 0),
        "plannerReviewResiduals": (
            model_counts.get("planner_review_residual", 0)
            + plc_counts.get("planner_review_residual", 0)
        ),
    }


def _anchor_policy_summary(
    source: pd.DataFrame,
    latest_source_date: pd.Timestamp | None,
) -> dict[str, Any]:
    quantity = pd.to_numeric(source.get("installationQuantity"), errors="coerce").fillna(0.0)
    methods = source.get(
        "anchorMappingMethod",
        pd.Series("unknown", index=source.index),
    ).fillna("unknown").astype(str)
    exact_methods = {
        "dealer_wholesale_exact",
        "dealer_wholesale_volume_resolved",
        "dealer_wholesale_variant_alias",
        "source_brand_kus",
    }
    total = float(quantity.sum())
    exact = float(quantity[methods.isin(exact_methods)].sum())
    fallback = float(quantity[~methods.isin(exact_methods)].sum())
    return {
        "officialAnchors": list(OFFICIAL_ANCHORS),
        "sharedCutoff": latest_source_date.date().isoformat() if latest_source_date is not None else None,
        "dealerWholesaleQuantityCoveragePct": round(exact / total * 100.0, 2) if total > 0 else 0.0,
        "fallbackQuantitySharePct": round(fallback / total * 100.0, 2) if total > 0 else 0.0,
        "mappingMethods": dict(Counter(methods.tolist())),
        "denominatorPolicy": {
            "HMA": "Dealer / non-fleet wholesale; fleet excluded under the current business rule",
            "GMA": "Dealer / non-fleet wholesale; fleet excluded",
            "KUS": (
                "Before 2026-06: legacy Wholesale-only basket. From 2026-06: separate "
                "Wholesale and model-year-2027 Carpet Floor Mat Fleet baskets."
            ),
        },
        "fleetPolicy": (
            "Implemented from 2026-06: allocate KUS model-year-2027 Carpet Floor Mat quantity "
            "to known Fleet vehicle volume first at up to 100% penetration, retain all remaining "
            "PIO Revenue/Quantity in Wholesale, and reconcile both baskets exactly to official KUS."
        ),
        "negativeSentinelPolicy": "-1 is normalized to 0 before EDA, ratios, and forecasting.",
        "modelVariantPolicy": "Exact normalized model names are retained; IONIQ variants are not collapsed by model code.",
    }


def _business_validation(
    brand_records: list[dict[str, Any]],
    source: pd.DataFrame,
    wholesale_long: pd.DataFrame | None,
    reconciliation: dict[str, Any],
    latest_source_date: pd.Timestamp | None,
) -> list[dict[str, str]]:
    anchors = {str(record.get("brand", "")) for record in brand_records}
    governed_anchor_set = set(OFFICIAL_ANCHORS)
    anchors_are_governed = bool(anchors) and anchors.issubset(governed_anchor_set)
    checks = [
        {
            "check": "Official anchor set",
            "status": "PASS" if anchors_are_governed else "WARN",
            "detail": (
                f"Observed governed anchor scope: {', '.join(sorted(anchors))}; full governed set: HMA, GMA, KUS."
                if anchors_are_governed
                else f"Observed anchors: {', '.join(sorted(anchors)) or 'none'}; governed set: HMA, GMA, KUS."
            ),
        },
        {
            "check": "Shared cutoff",
            "status": "PASS" if latest_source_date is not None else "WARN",
            "detail": (
                f"PIO and monthly wholesale nowcast use the shared as-of date {latest_source_date.date().isoformat()}."
                if latest_source_date is not None
                else "No reliable PIO cutoff date was available."
            ),
        },
        {
            "check": "Hierarchy reconciliation",
            "status": (
                "NOT_LOADED"
                if reconciliation.get("status") == "NOT_LOADED"
                else str(reconciliation.get("status", "WARN"))
            ),
            "detail": (
                "Open a hierarchy surface to calculate parent/child reconciliation."
                if reconciliation.get("status") == "NOT_LOADED"
                else (
                    f"Maximum parent/child delta is "
                    f"{max(float(reconciliation.get('brandToModelMaxAbsDelta', 0.0)), float(reconciliation.get('modelToPlcMaxAbsDelta', 0.0))):.6f}."
                )
            ),
        },
        {
            "check": "Non-negative measures",
            "status": (
                "PASS"
                if (pd.to_numeric(source.get("installationQuantity"), errors="coerce").fillna(0.0) >= 0).all()
                else "FAIL"
            ),
            "detail": "-1 and other negative business measures are clamped to zero before modeling.",
        },
    ]
    if wholesale_long is None or wholesale_long.empty:
        checks.append(
            {
                "check": "Dealer wholesale denominator",
                "status": "WARN",
                "detail": "No usable dealer-wholesale series was available for anchor mapping or per-vehicle metrics.",
            }
        )
    else:
        checks.append(
            {
                "check": "Dealer wholesale denominator",
                "status": "PASS",
                "detail": (
                    "Dealer/non-fleet vehicle volume remains in wholesaleUnits; Fleet vehicle volume "
                    "is retained separately in fleetUnits and is never added to the Wholesale denominator."
                ),
            }
        )
    kus_baskets = build_kus_channel_baskets(source, wholesale_long)
    governed_kus_baskets = (
        kus_baskets[kus_baskets["month"].astype(str) >= "2026-06"]
        if not kus_baskets.empty
        else kus_baskets
    )
    if governed_kus_baskets.empty:
        checks.append(
            {
                "check": "KUS Wholesale/Fleet baskets",
                "status": "WARN",
                "detail": (
                    "The current filtered scope has no KUS month on or after 2026-06 "
                    "to validate the implemented channel contract."
                ),
            }
        )
    else:
        max_revenue_delta = float(
            pd.to_numeric(
                governed_kus_baskets["revenueReconciliationDelta"],
                errors="coerce",
            ).abs().max()
        )
        max_quantity_delta = float(
            pd.to_numeric(
                governed_kus_baskets["quantityReconciliationDelta"],
                errors="coerce",
            ).abs().max()
        )
        latest_basket = governed_kus_baskets.sort_values("month").iloc[-1]
        basket_pass = max_revenue_delta <= 1e-6 and max_quantity_delta <= 1e-6
        checks.append(
            {
                "check": "KUS Wholesale/Fleet baskets",
                "status": "PASS" if basket_pass else "FAIL",
                "detail": (
                    f"{latest_basket['month']}: Fleet-first allocated "
                    f"{float(latest_basket['fleetBasketQuantity']):,.0f} eligible CFM units "
                    f"against {float(latest_basket['fleetVehicleVolume']):,.0f} Fleet vehicles; "
                    f"Wholesale + Fleet Revenue delta={max_revenue_delta:.6f}, "
                    f"Quantity delta={max_quantity_delta:.6f}."
                ),
            }
        )
    fallback_methods = {"genesis_name_fallback", "hma_default_fallback"}
    fallback_rows = int(
        source.get("anchorMappingMethod", pd.Series("", index=source.index))
        .fillna("")
        .astype(str)
        .isin(fallback_methods)
        .sum()
    )
    fallback_detail = ""
    if fallback_rows:
        fallback_source = source[
            source.get("anchorMappingMethod", pd.Series("", index=source.index))
            .fillna("")
            .astype(str)
            .isin(fallback_methods)
        ].copy()
        fallback_groups = []
        for (model_name, anchor_brand), group in fallback_source.groupby(
            ["modelName", "brand"],
            dropna=False,
        ):
            positive_activity_months = int(
                group.loc[
                    (
                        pd.to_numeric(group.get("installationQuantity"), errors="coerce").fillna(0.0)
                        > 0
                    )
                    | (
                        pd.to_numeric(group.get("pioRevenue"), errors="coerce").fillna(0.0)
                        > 0
                    ),
                    "month",
                ]
                .astype(str)
                .str[:7]
                .nunique()
            )
            fallback_groups.append(
                f"{model_name} -> {anchor_brand} "
                f"(sourceBrand={','.join(sorted(group['sourceBrand'].fillna('').astype(str).unique())) or 'unknown'}; "
                f"anchorMappingMethod={','.join(sorted(group['anchorMappingMethod'].fillna('').astype(str).unique()))}; "
                f"lifecycleStatus={','.join(sorted(group['lifecycleStatus'].fillna('Unknown').astype(str).unique()))}; "
                f"positive activity months={positive_activity_months}; "
                f"{str(group['month'].min())[:7]} to {str(group['month'].max())[:7]}; "
                "exact dealer/non-fleet Wholesale model mapping is missing)"
            )
        fallback_detail = "; ".join(fallback_groups)
    checks.append(
        {
            "check": "HMA/GMA model mapping",
            "status": "PASS" if fallback_rows == 0 else "WARN",
            "detail": (
                "All PIO rows use exact dealer-wholesale/company mapping."
                if fallback_rows == 0
                else (
                    f"{fallback_rows:,} monthly fact row(s) use a documented fallback: "
                    f"{fallback_detail}."
                )
            ),
        }
    )
    return checks


def _period_explanation(
    latest_complete_month: str,
    nowcast_months: list[str],
    forecast_months: list[str],
    latest_source_date: pd.Timestamp | None,
    working_day_map: dict[str, float],
) -> str:
    parts = [f"Training uses completed months through {latest_complete_month}."]
    if nowcast_months:
        cutoff = latest_source_date.date().isoformat() if latest_source_date is not None else "the latest observed date"
        parts.append(f"{', '.join(nowcast_months)} is a full-month nowcast using actuals through {cutoff}.")
        completion = (
            _estimated_working_day_completion(latest_source_date, working_day_map)
            if latest_source_date is not None
            else None
        )
        if completion is not None:
            parts.append(
                f"Uploaded Working Days for the full month = {completion['workingDays']:.0f}; "
                f"the day-of-month cutoff is not a working-day count. Estimated elapsed business-day exposure "
                f"is {completion['estimatedElapsedWorkingDays']:.1f} of {completion['workingDays']:.0f} "
                f"({completion['calendarWeekdaysElapsed']:.0f}/{completion['calendarWeekdaysInMonth']:.0f} calendar weekdays)."
            )
    if forecast_months:
        parts.append(f"Pure forecast months: {', '.join(forecast_months)}.")
    return " ".join(parts)


def _formula_catalog(metric: str) -> list[dict[str, str]]:
    target_column = (
        "Vehicle_Wholesale_Data dealer/non-fleet monthly wholesale"
        if metric == "wholesale_quantity"
        else "PIO_Sales_Data.SumOfPIS_CRP_CFM_PRI"
        if metric == "revenue"
        else "PIO_Sales_Data.SumOfPIS_INST_QT"
    )
    formulas = [
        {
            "name": "Monthly target actual",
            "formula": f"Monthly Actual = SUM({target_column}) at the official anchor grain",
            "logic": (
                "PIO Quantity starts from the uploaded installation-quantity field; it is not wholesale volume. "
                "PIO Revenue starts from uploaded PIO revenue and is modeled directly at the brand anchor."
                if metric != "wholesale_quantity"
                else (
                    "Wholesale Quantity routing remains dealer/non-fleet volume. KUS Fleet volume is "
                    "retained in a separate basket from 2026-06 and is not added to this target."
                )
            ),
        },
        {
            "name": "Brand anchor",
            "formula": "Official Anchor Forecast = lowest independent-test WAPE eligible model forecast",
            "logic": "HMA, GMA, and KUS are forecast separately. Candidates include baselines, additive ETS, and OLS drivers when history permits.",
        },
        {
            "name": "Working-day feature",
            "formula": "x_wd = (WorkingDays - meanWorkingDays) / meanWorkingDays",
            "logic": (
                "Working Days is the workbook's full-month business-day exposure, not the calendar day number. "
                "For example, 2026-07 contains 22 full-month working days even though the current data cutoff is July 28."
            ),
        },
        {
            "name": "Current-month nowcast",
            "formula": "Nowcast = MTD Actual + (1 - Estimated WD Completion) x Statistical Full-Month Baseline",
            "logic": (
                "MTD Actual is the sum of uploaded transactions from the first day of the month through the cutoff. "
                "The incomplete month is excluded only from model fitting, then added back as actual-to-date in the nowcast."
            ),
        },
        {
            "name": "Lower-level quantity signal",
            "formula": "Raw Qty = 60% x WD-adjusted seasonal mean + 40% x WD-adjusted recent-6 mean",
            "logic": (
                "The historical input is monthly SUM(SumOfPIS_INST_QT). Raw Qty is a Model/PLC allocation signal, "
                "not wholesale and not a direct copy of one source row. If seasonal history is insufficient, recent-6 is used."
            ),
        },
        {
            "name": "Lifecycle and volume routing",
            "formula": "Stopped before current forecast year = 0; Low volume = excluded; New/Reintroduced = recent run-rate proxy",
            "logic": (
                "After at least six months of the current year are observed, a model with no positive current-year "
                "activity is inactive. Regular allocation requires at least six active months and the configured "
                "minimum average monthly quantity."
            ),
        },
        {
            "name": "Reconciliation",
            "formula": "Child Forecast = Parent Forecast x Raw Child Signal / SUM(Raw Child Signals)",
            "logic": "Model totals equal Brand; PLC totals equal Model for every forecast month.",
        },
    ]
    if metric == "revenue":
        formulas.insert(
            4,
            {
                "name": "Revenue allocation signal",
                "formula": "Raw Revenue = Raw Quantity x Expected Unit Revenue",
                "logic": (
                    "Expected Unit Revenue is PIO revenue per installed accessory unit, not revenue per wholesale vehicle. "
                    "Model/PLC uses the latest 3 completed months, then own history, then the parent's recent-6 unit revenue."
                ),
            },
        )
        formulas.insert(
            5,
            {
                "name": "Exact-part unit revenue",
                "formula": "Part Expected Unit Revenue = recent-6 PIO Revenue / recent-6 PIO Quantity",
                "logic": (
                    "The final exact-part planning allocation currently uses six completed months. "
                    "This is disclosed separately from the Model/PLC three-month unit-revenue window."
                ),
            },
        )
    if metric == "wholesale_quantity":
        formulas = [formula for formula in formulas if formula["name"] != "Revenue allocation signal"]
    return formulas


def _accuracy_scope(metric: str) -> dict[str, str]:
    metric_label = METRIC_LABELS.get(metric, metric)
    return {
        "target": metric_label,
        "evaluatedGrain": "month × selected official brand anchor(s) from HMA/GMA/KUS",
        "overallFormula": (
            "Overall Accuracy = max(0, 1 - SUM(absolute backtest error across selected governed anchors) "
            "/ SUM(actual across selected governed anchors)). It is volume-weighted, not a simple average of anchor percentages."
        ),
        "anchorFormula": "Each anchor Accuracy = max(0, 1 - anchor independent-test WAPE).",
        "childPolicy": (
            "Brand error propagates to every child. Model, PLC, and PIS_PNO allocation-only diagnostics "
            "measure the additional held-out child-share error after supplying the actual held-out parent total. "
            "They are not end-to-end forecast accuracy, and reconciliation PASS is only arithmetic consistency."
        ),
    }


def _registered_evidence_gate(
    *,
    metric: str,
    model_strategy: str,
    source_hash: str,
    latest_complete_month: str,
    brand_records: list[dict[str, Any]],
    evaluation_scope_eligible: bool,
    evaluation_scope_metadata: dict[str, Any],
    trusted_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scope_id = "governed_h123_24m_h1_18_h2_17_h3_16_official_total_51"
    observed_anchors = sorted(
        {str(record.get("brand", "")) for record in brand_records}
    )
    evidence = (
        deepcopy(trusted_evidence)
        if trusted_evidence is not None
        else deepcopy(VALIDATED_REFERENCE_PORTFOLIO.get("evaluationEvidence", {}))
    )
    required_evidence_fields = {
        "completedMonthStart",
        "completedMonthCount",
        "minimumTrainingMonths",
        "expectedFoldCounts",
        "foldKeyCount",
        "foldKeyIdentityAlgorithm",
        "foldKeyIdentity",
        "predictionCoverage",
        "fullCoverage",
        "aggregation",
        "target",
    }
    evidence_fields_complete = required_evidence_fields.issubset(evidence)
    completed_month_count = int(evidence.get("completedMonthCount", 0) or 0)
    expected_counts = expected_fold_counts(completed_month_count)
    expected_identity = _expected_fold_key_identity(
        start_month=str(evidence.get("completedMonthStart", "")),
        completed_month_count=completed_month_count,
        minimum_training_months=int(evidence.get("minimumTrainingMonths", 0) or 0),
        horizons=tuple(VALIDATED_REFERENCE_PORTFOLIO.get("backtestHorizons", [])),
    )
    checks = {
        "explicitFullScopeEligibility": evaluation_scope_eligible is True,
        "sourceHash": source_hash.lower()
        == VALIDATED_REFERENCE_PORTFOLIO["sourceHash"],
        "targetRevenue": metric == "revenue",
        "referencePortfolioRequested": model_strategy == "reference_portfolio",
        "trainingCutoff": latest_complete_month
        == VALIDATED_REFERENCE_PORTFOLIO["trainingCutoff"],
        "completeOfficialAnchors": observed_anchors == ["GMA", "HMA", "KUS"],
        "unfiltered": evaluation_scope_metadata.get("filtersApplied") is False,
        "requestCutoff": evaluation_scope_metadata.get("requestCutoff")
        == latest_complete_month,
        "requestTarget": evaluation_scope_metadata.get("target") == metric,
        "trustedEvidenceFields": evidence_fields_complete,
        "trustedContractVersion": VALIDATED_REFERENCE_PORTFOLIO.get(
            "contractVersion"
        )
        == "pio-backtest-v1",
        "trustedHorizons": VALIDATED_REFERENCE_PORTFOLIO.get("backtestHorizons")
        == [1, 2, 3],
        "trustedMinimumTraining": evidence.get("minimumTrainingMonths") == 24,
        "trustedFoldCounts": evidence.get("expectedFoldCounts")
        == expected_counts
        == {"1": 18, "2": 17, "3": 16, "combined": 51},
        "trustedFoldKeyCount": evidence.get("foldKeyCount")
        == expected_identity["foldKeyCount"]
        == 51,
        "trustedFoldKeyIdentity": evidence.get("foldKeyIdentity")
        == expected_identity["foldKeyIdentity"],
        "trustedFoldKeyAlgorithm": evidence.get("foldKeyIdentityAlgorithm")
        == "sha256_canonical_json_origin_target_horizon",
        "trustedPredictionCoverage": evidence.get("predictionCoverage") == 1.0,
        "trustedFullCoverage": evidence.get("fullCoverage") is True,
        "trustedAggregation": evidence.get("aggregation") == "Official Total",
        "trustedTarget": evidence.get("target") == "pio_revenue",
    }
    eligible = all(checks.values())
    return {
        "evaluationScopeId": scope_id,
        "eligible": eligible,
        "validationStatus": (
            "validated_reference_evidence" if eligible else "unvalidated_request_scope"
        ),
        "checks": checks,
        "observedAnchors": observed_anchors,
        "requiredAnchors": ["HMA", "GMA", "KUS"],
        "sourceHash": source_hash or "unavailable",
        "cutoff": latest_complete_month,
        "target": "PIO Revenue",
        "grain": "origin month × target month × horizon × Official Total",
        "aggregation": "Official Total",
        "coverage": "complete, unfiltered HMA/GMA/KUS",
        "contractVersion": VALIDATED_REFERENCE_PORTFOLIO["contractVersion"],
        "requestScope": evaluation_scope_metadata,
        "trustedEvidence": evidence,
    }


def _expected_fold_key_identity(
    *,
    start_month: str,
    completed_month_count: int,
    minimum_training_months: int,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    if (
        not start_month
        or completed_month_count <= minimum_training_months
        or minimum_training_months < 1
        or not horizons
    ):
        return {"foldKeyCount": 0, "foldKeyIdentity": ""}
    try:
        months = pd.period_range(
            pd.Period(start_month, freq="M"),
            periods=completed_month_count,
            freq="M",
        )
    except (TypeError, ValueError):
        return {"foldKeyCount": 0, "foldKeyIdentity": ""}
    keys = [
        {
            "originMonth": str(months[training_end - 1]),
            "targetMonth": str(months[training_end + horizon - 1]),
            "horizon": horizon,
        }
        for training_end in range(minimum_training_months, len(months))
        for horizon in horizons
        if training_end + horizon - 1 < len(months)
    ]
    return {
        "foldKeyCount": len(keys),
        "foldKeyIdentity": hashlib.sha256(
            json.dumps(
                keys, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
    }
def _diagnostic_source_signatures(
    source: pd.DataFrame,
    working_days: pd.DataFrame | None,
) -> tuple[str, str]:
    source_columns = [
        column
        for column in (
            "month",
            "brand",
            "entityKey",
            "modelName",
            "plc",
            "partNumber",
            "installationQuantity",
            "pioRevenue",
            "lifecycleStatus",
            "lifecycleStatusCode",
        )
        if column in source.columns
    ]
    source_signature = hashlib.sha256(
        pd.util.hash_pandas_object(
            source[source_columns].sort_values(source_columns[:6], kind="stable"),
            index=False,
        ).values.tobytes()
    ).hexdigest()
    if working_days is None or working_days.empty:
        working_day_signature = "none"
    else:
        wd_columns = [
            column for column in ("month", "workingDays") if column in working_days.columns
        ]
        working_day_signature = hashlib.sha256(
            pd.util.hash_pandas_object(
                working_days[wd_columns].sort_values(wd_columns, kind="stable"),
                index=False,
            ).values.tobytes()
        ).hexdigest()
    return source_signature, working_day_signature


def _diagnostic_scope_cache_key(
    source: pd.DataFrame,
    working_days: pd.DataFrame | None,
    *,
    source_signature: str | None = None,
    working_day_signature: str | None = None,
    source_hash: str,
    cutoff: str,
    metric: str,
    model_strategy: str,
    use_working_days: bool,
    use_seasonality: bool,
    min_monthly_volume: float,
    horizon: int,
    tariff_impact_pct: float,
    latest_sales_date: pd.Timestamp | None,
    latest_sales_month_is_complete: bool,
    evaluation_scope_eligible: bool,
    evaluation_scope_metadata: dict[str, Any],
) -> str:
    if source_signature is None or working_day_signature is None:
        source_signature, working_day_signature = _diagnostic_source_signatures(
            source,
            working_days,
        )
    payload = {
        "sourceHash": source_hash or "unavailable",
        "sourceSignature": source_signature,
        "cutoff": cutoff,
        "metric": metric,
        "strategy": model_strategy,
        "useWorkingDays": use_working_days,
        "useSeasonality": use_seasonality,
        "minimumMonthlyVolume": float(min_monthly_volume),
        "horizon": int(horizon),
        "tariffImpactPct": float(tariff_impact_pct),
        "latestSalesDate": (
            latest_sales_date.isoformat() if latest_sales_date is not None else None
        ),
        "latestSalesMonthIsComplete": bool(latest_sales_month_is_complete),
        "fullScopeEligible": bool(evaluation_scope_eligible),
        "requestScope": evaluation_scope_metadata,
        "workingDaySignature": working_day_signature,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _attach_cached_strategy_residuals(
    brand_records: list[dict[str, Any]],
    anchor_source: pd.DataFrame,
    working_day_map: dict[str, float],
    *,
    cache_key: str,
    latest_complete_month: str,
    model_strategy: str,
    use_working_days: bool,
    use_seasonality: bool,
    source_hash: str,
) -> bool:
    cached = _RESIDUAL_CACHE.get(cache_key)
    cache_hit = cached is not None
    if cached is None:
        cached = {}
        completed = anchor_source.copy()
        completed["month"] = completed["month"].astype(str).str[:7]
        completed = completed[completed["month"] <= latest_complete_month]
        for brand, group in completed.groupby("brand", sort=True):
            monthly = group.groupby("month")["installationQuantity"].sum()
            if monthly.empty:
                cached[str(brand)] = []
                continue
            index = pd.date_range(
                pd.Period(str(monthly.index.min()), freq="M").to_timestamp(),
                pd.Period(latest_complete_month, freq="M").to_timestamp(),
                freq="MS",
            )
            series = monthly.reindex(index.strftime("%Y-%m"), fill_value=0.0)
            series.index = index
            cached[str(brand)] = rolling_origin_residuals(
                series,
                working_day_map,
                entity=str(brand),
                use_working_days=use_working_days,
                use_seasonality=use_seasonality,
                model_strategy=model_strategy,
                source_hash=source_hash,
            )
        _cache_put(_RESIDUAL_CACHE, cache_key, cached)
    else:
        _RESIDUAL_CACHE.move_to_end(cache_key)
    for record in brand_records:
        record["rollingOriginResiduals"] = deepcopy(
            cached.get(str(record.get("brand", "")), [])
        )
    return cache_hit


def _cache_put(cache: OrderedDict, key: str, value: Any) -> None:
    cache[key] = deepcopy(value)
    cache.move_to_end(key)
    while len(cache) > _CACHE_LIMIT:
        cache.popitem(last=False)


def clear_forecast_diagnostic_caches() -> None:
    """Clear deterministic in-process diagnostic caches for tests/operations."""

    _RESIDUAL_CACHE.clear()
    _GOVERNANCE_DIAGNOSTIC_CACHE.clear()


def _evaluation_scopes(
    *,
    metric: str,
    source_hash: str,
    latest_complete_month: str,
    brand_records: list[dict[str, Any]],
    validation_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    application_rows = [
        row
        for record in brand_records
        for row in record.get("applicationRecentH1Rows", [])
    ]
    brand_prediction_rows = len(application_rows)
    entity_sets: dict[tuple[str, str, int], set[str]] = {}
    for row in application_rows:
        key = (
            str(row.get("origin_month", "")),
            str(row.get("target_month", "")),
            int(row.get("horizon", 1)),
        )
        entity_sets.setdefault(key, set()).add(str(row.get("entity", "")))
    required = {str(record.get("brand", "")) for record in brand_records}
    common_origin_rows = sum(
        1 for entities in entity_sets.values() if entities == required
    )
    return [
        {
            "evaluationScopeId": "application_recent_h1",
            "label": "Application recent H1 diagnostic",
            "validationStatus": "legacy_application_diagnostic",
            "sourceHash": source_hash or "unavailable",
            "cutoff": latest_complete_month,
            "target": METRIC_LABELS.get(metric, metric),
            "horizons": [1],
            "minimumTrainingMonths": None,
            "expectedFoldCounts": None,
            "commonOriginRows": common_origin_rows,
            "brandPredictionRows": brand_prediction_rows,
            "grain": "Brand prediction rows",
            "aggregation": "selected Brand rows; not Official Total common-fold scoring",
            "coverage": "recent 3–6 H1 points per Brand when history permits",
            "comparabilityNote": (
                "Legacy application_recent_h1 is not ranked against the governed "
                "24-month H1/H2/H3 Official Total contract."
            ),
        },
        {
            "evaluationScopeId": validation_gate["evaluationScopeId"],
            "label": "Governed H1/H2/H3 Official Total",
            "validationStatus": validation_gate["validationStatus"],
            "sourceHash": source_hash or "unavailable",
            "cutoff": latest_complete_month,
            "target": METRIC_LABELS.get(metric, metric),
            "horizons": [1, 2, 3],
            "minimumTrainingMonths": 24,
            "expectedFoldCounts": {"1": 18, "2": 17, "3": 16, "combined": 51},
            "commonOriginRows": 51 if validation_gate["eligible"] else None,
            "brandPredictionRows": 153 if validation_gate["eligible"] else None,
            "grain": "Official Total common origin-horizon rows",
            "aggregation": "sum HMA/GMA/KUS on each common fold before WAPE",
            "coverage": "complete, unfiltered HMA/GMA/KUS",
            "comparabilityNote": (
                "Only models evaluated on this exact source, cutoff, target, grain, "
                "aggregation and 51-row fold set are comparable."
            ),
        },
    ]


def _fair_model_comparison(
    *,
    validation_gate: dict[str, Any],
    metric: str,
) -> dict[str, Any]:
    comparable = metric == "revenue" and bool(validation_gate["eligible"])
    rows = []
    if comparable:
        rows = [
            {
                "modelId": "repository_additive_ets_reference_proxy",
                "label": "Repository Additive ETS reference proxy",
                "comparisonType": "isolated_hma_ets_comparison",
                "hmaMethod": "ets_additive",
                "gmaMethod": "naive_last",
                "kusMethod": "working_day_adjusted_seasonal",
                "officialTotalWape": 0.10037709985878922,
                "accuracy": 0.8996229001412108,
                "foldCount": 51,
            },
            {
                "modelId": "rebuilt_reference_portfolio_v1",
                "label": "Validated reference portfolio",
                "comparisonType": "isolated_hma_ets_comparison",
                "hmaMethod": VALIDATED_REFERENCE_PORTFOLIO["brandMethods"]["HMA"],
                "gmaMethod": "naive_last",
                "kusMethod": "working_day_adjusted_seasonal",
                "officialTotalWape": VALIDATED_REFERENCE_PORTFOLIO["officialTotal"][
                    "wape"
                ],
                "accuracy": VALIDATED_REFERENCE_PORTFOLIO["officialTotal"][
                    "accuracy"
                ],
                "foldCount": 51,
            },
        ]
    return {
        "evaluationScopeId": validation_gate["evaluationScopeId"],
        "validationStatus": (
            "validated_same_contract_comparison"
            if comparable
            else "unvalidated_not_same_contract"
        ),
        "comparisonType": "isolated_hma_ets_comparison",
        "disclosure": (
            "This isolates the HMA ETS implementation. GMA remains naive_last, "
            "KUS remains working_day_adjusted_seasonal, and the production default is unchanged."
        ),
        "sourceHash": validation_gate["sourceHash"],
        "cutoff": validation_gate["cutoff"],
        "foldCount": 51 if comparable else None,
        "aggregation": "Official Total on identical common H1/H2/H3 folds",
        "rows": rows,
    }


def _algorithm_leaderboard(
    *,
    validation_gate: dict[str, Any],
    metric: str,
) -> dict[str, Any]:
    disclosure = (
        "PIO Revenue at Brand anchors and Official Total only. H1/H2/H3 use a 24-month "
        "minimum training window and 18/17/16 = 51 common folds with 100% coverage. "
        "Brand accuracy is not Model or PLC accuracy; use Allocation Accuracy for separate "
        "allocation-only child diagnostics."
    )
    if metric != "revenue" or not validation_gate["eligible"]:
        return {
            "evaluationScopeId": validation_gate["evaluationScopeId"],
            "validationStatus": "unvalidated_not_same_contract",
            "sourceHash": validation_gate["sourceHash"],
            "cutoff": validation_gate["cutoff"],
            "target": "PIO Revenue",
            "grain": "Brand anchors + Official Total",
            "horizons": [1, 2, 3],
            "minimumTrainingMonths": 24,
            "expectedFoldCounts": {"1": 18, "2": 17, "3": 16, "combined": 51},
            "foldCount": 0,
            "coverage": 0.0,
            "aggregation": "sum HMA/GMA/KUS on each common fold before WAPE",
            "disclosure": disclosure,
            "rows": [],
        }

    rows = [
        {
            "modelId": "rebuilt_reference_portfolio_v1",
            "label": "Validated reference portfolio",
            "hmaWape": VALIDATED_REFERENCE_PORTFOLIO["brandMetrics"]["HMA"]["wape"],
            "gmaWape": VALIDATED_REFERENCE_PORTFOLIO["brandMetrics"]["GMA"]["wape"],
            "kusWape": VALIDATED_REFERENCE_PORTFOLIO["brandMetrics"]["KUS"]["wape"],
            "officialTotalWape": VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["wape"],
            "accuracy": VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["accuracy"],
            "foldCount": VALIDATED_REFERENCE_PORTFOLIO["foldCount"],
            "coverage": VALIDATED_REFERENCE_PORTFOLIO["evaluationEvidence"]["predictionCoverage"],
            "status": "validated_champion",
        }
    ]
    for model_id in ("tree_meta_selector_v1", "elastic_net_anchor_residual_v1"):
        artifact = load_ml_challenger_artifact(
            model_id,
            source_hash=validation_gate["sourceHash"],
        )
        evaluation = artifact["evaluation"]
        official_metrics = evaluation["officialTotalMetrics"]
        rows.append(
            {
                "modelId": model_id,
                "label": artifact["displayName"],
                "hmaWape": evaluation["entityMetrics"]["HMA"]["combined"]["wape"],
                "gmaWape": evaluation["entityMetrics"]["GMA"]["combined"]["wape"],
                "kusWape": evaluation["entityMetrics"]["KUS"]["combined"]["wape"],
                "officialTotalWape": official_metrics["wape"],
                "accuracy": official_metrics["accuracy"],
                "foldCount": official_metrics["foldCount"],
                "coverage": official_metrics["predictionCoverage"],
                "status": "challenger_not_promoted",
            }
        )
    rows.sort(key=lambda row: float(row["officialTotalWape"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "evaluationScopeId": validation_gate["evaluationScopeId"],
        "validationStatus": "validated_same_contract_leaderboard",
        "sourceHash": validation_gate["sourceHash"],
        "cutoff": validation_gate["cutoff"],
        "target": "PIO Revenue",
        "grain": "Brand anchors + Official Total",
        "horizons": [1, 2, 3],
        "minimumTrainingMonths": 24,
        "expectedFoldCounts": {"1": 18, "2": 17, "3": 16, "combined": 51},
        "foldCount": 51,
        "coverage": 1.0,
        "aggregation": "sum HMA/GMA/KUS on each common fold before WAPE",
        "disclosure": disclosure,
        "rows": rows,
    }


def _apply_prediction_intervals(
    brand_records: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    plc_records: list[dict[str, Any]],
    *,
    evaluation_scopes: list[dict[str, Any]],
    validation_applies: bool,
) -> dict[str, Any]:
    brand_summaries: list[dict[str, Any]] = []
    for record in brand_records:
        brand = str(record.get("brand", ""))
        points = [
            {
                "forecastMonth": item.get("month"),
                "horizon": index + 1,
                "point": item.get("value", 0.0),
                "forecastType": item.get("forecastType", "Forecast"),
            }
            for index, item in enumerate(record.get("forecast", []))
        ]
        intervals = calibrate_held_out_intervals(
            points,
            record.get("rollingOriginResiduals", []),
            calibration_scope_id=f"brand_rolling_origin_h123::{brand}",
            validation_status="validated_brand_rolling_origin",
        )
        _mark_nowcast_intervals_unvalidated(intervals)
        for item, interval in zip(record.get("forecast", []), intervals, strict=False):
            item.update(
                {
                    key: interval[key]
                    for key in (
                        "lower",
                        "point",
                        "upper",
                        "nominalCoverage",
                        "empiricalCoverage",
                        "coverageSampleCount",
                        "calibrationResidualCount",
                        "calibrationScopeId",
                        "validationStatus",
                    )
                }
            )
        brand_summaries.append(
            {
                "brand": brand,
                "validationStatus": (
                    next(
                        (
                            item["validationStatus"]
                            for item in intervals
                            if item.get("forecastType") != "Nowcast"
                        ),
                        intervals[0]["validationStatus"] if intervals else "unvalidated",
                    )
                ),
                "calibrationResidualCount": sum(
                    int(item["calibrationResidualCount"]) for item in intervals
                ),
                "empiricalCoverage": next(
                    (
                        item["empiricalCoverage"]
                        for item in intervals
                        if item["empiricalCoverage"] is not None
                    ),
                    None,
                ),
            }
        )

    total_calibration: dict[tuple[str, str, int], dict[str, float]] = {}
    total_entities: dict[tuple[str, str, int], set[str]] = {}
    for record in brand_records:
        for row in record.get("rollingOriginResiduals", []):
            key = (
                str(row.get("origin_month", "")),
                str(row.get("target_month", "")),
                int(row.get("horizon", 1)),
            )
            item = total_calibration.setdefault(key, {"actual": 0.0, "prediction": 0.0})
            item["actual"] += float(row.get("actual", 0.0))
            item["prediction"] += float(row.get("prediction", 0.0))
            total_entities.setdefault(key, set()).add(str(record.get("brand", "")))
    official_anchors_complete = {
        str(record.get("brand", "")) for record in brand_records
    } == {"HMA", "GMA", "KUS"}
    total_rows = [
        {
            "origin_month": key[0],
            "target_month": key[1],
            "horizon": key[2],
            **value,
        }
        for key, value in total_calibration.items()
        if len(total_entities.get(key, set())) == len(brand_records)
    ]
    months = sorted(
        {
            str(item.get("month", ""))
            for record in brand_records
            for item in record.get("forecast", [])
        }
    )
    total_points = [
        {
            "forecastMonth": month,
            "horizon": index + 1,
            "point": sum(
                float(item.get("value", 0.0))
                for record in brand_records
                for item in record.get("forecast", [])
                if str(item.get("month")) == month
            ),
            "forecastType": (
                "Nowcast"
                if any(
                    item.get("forecastType") == "Nowcast"
                    for record in brand_records
                    for item in record.get("forecast", [])
                    if str(item.get("month")) == month
                )
                else "Forecast"
            ),
        }
        for index, month in enumerate(months)
    ]
    total_intervals = calibrate_held_out_intervals(
        total_points,
        total_rows,
        calibration_scope_id="official_total_rolling_origin_h123",
        validation_status=(
            "validated_official_total_rolling_origin"
            if official_anchors_complete
            else "unvalidated_partial_anchor_scope"
        ),
    )
    _mark_nowcast_intervals_unvalidated(total_intervals)

    brand_lookup = {str(record.get("brand", "")): record for record in brand_records}
    for record in model_records:
        _inherit_unvalidated_child_intervals(
            record,
            brand_lookup.get(str(record.get("brand", ""))),
            scope="Model",
        )
    model_lookup = {
        (
            str(record.get("brand", "")),
            str(record.get("entityKey", "")),
            str(record.get("modelName", "")),
        ): record
        for record in model_records
    }
    for record in plc_records:
        _inherit_unvalidated_child_intervals(
            record,
            model_lookup.get(
                (
                    str(record.get("brand", "")),
                    str(record.get("entityKey", "")),
                    str(record.get("modelName", "")),
                )
            ),
            scope="PLC",
        )
    return {
        "nominalCoverage": 0.90,
        "method": "horizon-specific held-out rolling-origin absolute residual quantiles",
        "evaluationScopeId": evaluation_scopes[1]["evaluationScopeId"],
        "registeredMetricScopeValidated": validation_applies,
        "officialTotal": total_intervals,
        "brands": brand_summaries,
        "childCoveragePolicy": (
            "Model, PLC, and PIS_PNO bounds are allocation bands only and remain "
            "unvalidated until held-out child interval coverage is tested."
        ),
    }


def _mark_nowcast_intervals_unvalidated(
    intervals: list[dict[str, Any]],
) -> None:
    for interval in intervals:
        if interval.get("forecastType") != "Nowcast":
            continue
        interval.update(
            {
                "empiricalCoverage": None,
                "coverageSampleCount": 0,
                "calibrationResidualCount": 0,
                "calibrationScopeId": "nowcast_cutoff_specific_residuals_unavailable",
                "validationStatus": "unvalidated_nowcast",
            }
        )


def _inherit_unvalidated_child_intervals(
    child: dict[str, Any],
    parent: dict[str, Any] | None,
    *,
    scope: str,
) -> None:
    if parent is None:
        return
    parent_by_month = {
        str(item.get("month")): item for item in parent.get("forecast", [])
    }
    for item in child.get("forecast", []):
        parent_item = parent_by_month.get(str(item.get("month")))
        point = max(float(item.get("value", 0.0)), 0.0)
        parent_point = float(parent_item.get("point", parent_item.get("value", 0.0))) if parent_item else 0.0
        share = point / parent_point if parent_point > 0 else 0.0
        lower = max(0.0, float(parent_item.get("lower", parent_point)) * share) if parent_item else point
        upper = max(point, float(parent_item.get("upper", parent_point)) * share) if parent_item else point
        item.update(
            {
                "lower": min(lower, point),
                "point": point,
                "upper": upper,
                "nominalCoverage": 0.90,
                "empiricalCoverage": None,
                "coverageSampleCount": 0,
                "calibrationResidualCount": 0,
                "calibrationScopeId": f"allocation_band::{scope.lower()}",
                "validationStatus": "unvalidated_child_interval_coverage",
            }
        )


def _allocation_accuracy_diagnostics(
    source: pd.DataFrame,
    *,
    metric: str,
    latest_complete_month: str,
    source_hash: str,
) -> list[dict[str, Any]]:
    if metric == "wholesale_quantity":
        level_specs = [
            ("Model", ["brand", "entityKey", "modelName"], ["brand"]),
        ]
    else:
        level_specs = [
            ("Model", ["brand", "entityKey", "modelName"], ["brand"]),
            (
                "PLC",
                ["brand", "entityKey", "modelName", "plc"],
                ["brand", "entityKey", "modelName"],
            ),
            (
                "PIS_PNO",
                ["brand", "entityKey", "modelName", "plc", "partNumber"],
                ["brand", "entityKey", "modelName", "plc"],
            ),
        ]
    source_start_month, monthly_frames = _preaggregate_allocation_monthly(
        source,
        metric=metric,
        latest_complete_month=latest_complete_month,
        level_specs=level_specs,
    )
    results = [
        _allocation_accuracy_for_level(
            source,
            metric=metric,
            level=level,
            child_dimensions=child_dimensions,
            parent_dimensions=parent_dimensions,
            latest_complete_month=latest_complete_month,
            source_hash=source_hash,
            preaggregated_monthly=monthly_frames.get(level),
            source_start_month=source_start_month,
        )
        for level, child_dimensions, parent_dimensions in level_specs
    ]
    if metric == "wholesale_quantity":
        for level in ("PLC", "PIS_PNO"):
            results.append(
                {
                    "level": level,
                    "validationStatus": "not_applicable_to_wholesale",
                    "scope": "allocationOnly",
                    "grain": "not available",
                    "wape": None,
                    "accuracy": None,
                    "coverage": 0.0,
                    "rowCount": 0,
                    "foldCount": 0,
                }
            )
    return results


def _preaggregate_allocation_monthly(
    source: pd.DataFrame,
    *,
    metric: str,
    latest_complete_month: str,
    level_specs: list[tuple[str, list[str], list[str]]],
) -> tuple[str | None, dict[str, pd.DataFrame]]:
    value_column = "pioRevenue" if metric == "revenue" else "installationQuantity"
    required = {
        "month",
        "installationQuantity",
        value_column,
        *(
            dimension
            for _, child_dimensions, _ in level_specs
            for dimension in child_dimensions
        ),
    }
    if source.empty or not required.issubset(source.columns):
        return None, {}
    working = source[list(required)].copy()
    working["month"] = working["month"].astype(str).str[:7]
    working = working[working["month"] <= latest_complete_month]
    if working.empty:
        return None, {}
    working["installationQuantity"] = pd.to_numeric(
        working["installationQuantity"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    working[value_column] = pd.to_numeric(
        working[value_column], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    revenue_column = (
        "pioRevenue" if "pioRevenue" in working.columns else "installationQuantity"
    )
    return str(working["month"].min()), {
        level: (
            working.groupby(
                child_dimensions + ["month"],
                as_index=False,
                dropna=False,
            ).agg(
                actual=(value_column, "sum"),
                quantity=("installationQuantity", "sum"),
                revenue=(revenue_column, "sum"),
            )
        )
        for level, child_dimensions, _ in level_specs
    }


def _allocation_accuracy_for_level(
    source: pd.DataFrame,
    *,
    metric: str,
    level: str,
    child_dimensions: list[str],
    parent_dimensions: list[str],
    latest_complete_month: str,
    source_hash: str,
    preaggregated_monthly: pd.DataFrame | None = None,
    source_start_month: str | None = None,
) -> dict[str, Any]:
    required = set(child_dimensions + parent_dimensions + ["month", "installationQuantity"])
    value_column = "pioRevenue" if metric == "revenue" else "installationQuantity"
    required.add(value_column)
    if source.empty or not required.issubset(source.columns):
        return {
            "evaluationScopeId": f"allocation_only_h123::{metric}::{level.lower()}",
            "level": level,
            "validationStatus": "unvalidated_insufficient_columns",
            "scope": "allocationOnly",
            "grain": " × ".join(["origin", "target", "horizon", *child_dimensions]),
            "wape": None,
            "accuracy": None,
            "coverage": 0.0,
            "rowCount": 0,
            "foldCount": 0,
        }
    if preaggregated_monthly is None:
        source_start_month, monthly_frames = _preaggregate_allocation_monthly(
            source,
            metric=metric,
            latest_complete_month=latest_complete_month,
            level_specs=[(level, child_dimensions, parent_dimensions)],
        )
        monthly = monthly_frames.get(level)
    else:
        monthly = preaggregated_monthly
    if monthly is None or monthly.empty or source_start_month is None:
        return {
            "evaluationScopeId": f"allocation_only_h123::{metric}::{level.lower()}",
            "level": level,
            "validationStatus": "unvalidated_insufficient_history",
            "scope": "allocationOnly",
            "grain": " 脳 ".join(["origin", "target", "horizon", *child_dimensions]),
            "wape": None,
            "accuracy": None,
            "coverage": 0.0,
            "rowCount": 0,
            "foldCount": 0,
        }
    all_months = pd.period_range(
        pd.Period(source_start_month, freq="M"),
        pd.Period(latest_complete_month, freq="M"),
        freq="M",
    )
    entity_table = monthly[child_dimensions].drop_duplicates().reset_index(drop=True)
    entity_table["__entity_id"] = np.arange(len(entity_table))
    monthly = monthly.merge(entity_table, on=child_dimensions, how="left")
    grid = pd.MultiIndex.from_product(
        [entity_table["__entity_id"].tolist(), all_months.astype(str).tolist()],
        names=["__entity_id", "month"],
    ).to_frame(index=False)
    grid = grid.merge(entity_table, on="__entity_id", how="left")
    grid = grid.merge(
        monthly[["__entity_id", "month", "actual", "quantity", "revenue"]],
        on=["__entity_id", "month"],
        how="left",
    )
    for column in ("actual", "quantity", "revenue"):
        grid[column] = pd.to_numeric(grid[column], errors="coerce").fillna(0.0)
    first_month = (
        monthly.groupby("__entity_id")["month"].min().rename("firstMonth")
    )
    grid = grid.merge(first_month, on="__entity_id", how="left")
    grid = grid.sort_values(["__entity_id", "month"], kind="stable")
    signal_value = "revenue" if metric == "revenue" else "quantity"
    grid["recentSignal"] = (
        grid.groupby("__entity_id", sort=False)[signal_value]
        .rolling(6, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )
    grid["historySignal"] = grid.groupby("__entity_id", sort=False)[
        signal_value
    ].cumsum()
    rows: list[dict[str, Any]] = []
    fold_keys: set[tuple[str, str, int]] = set()
    parent_fold_total = 0
    parent_fold_covered = 0
    zero_signal_parent_count = 0
    zero_parent_actual_count = 0
    eligible_entity_rows = 0
    covered_entity_rows = 0
    missing_signal_rows = 0
    fold_audits: list[dict[str, Any]] = []
    for training_end in range(24, len(all_months)):
        origin = all_months[training_end - 1]
        signals = grid[
            (grid["month"] == str(origin))
            & (grid["firstMonth"] <= str(origin))
        ][child_dimensions + ["recentSignal", "historySignal"]].copy()
        signals["signal"] = signals["recentSignal"]
        signal_hash = hashlib.sha256(
            pd.util.hash_pandas_object(
                signals.sort_values(child_dimensions, kind="stable"),
                index=False,
            ).values.tobytes()
        ).hexdigest()
        for horizon in (1, 2, 3):
            target_position = training_end + horizon - 1
            if target_position >= len(all_months):
                continue
            target_month = str(all_months[target_position])
            fold_keys.add((str(origin), target_month, horizon))
            actual = monthly[monthly["month"] == target_month][
                child_dimensions + ["actual"]
            ].copy()
            union = actual.merge(
                signals[child_dimensions + ["signal", "historySignal"]],
                on=child_dimensions,
                how="outer",
                indicator="signalMerge",
            ).fillna({"actual": 0.0, "signal": 0.0, "historySignal": 0.0})
            union["signalAvailable"] = union["signalMerge"] != "left_only"
            parent_actual = (
                union.groupby(parent_dimensions, as_index=False, dropna=False)[
                    "actual"
                ]
                .sum()
                .rename(columns={"actual": "parentActual"})
            )
            signal_totals = (
                union.groupby(parent_dimensions, as_index=False, dropna=False)[
                    "signal"
                ]
                .sum()
                .rename(columns={"signal": "parentSignal"})
            )
            union = union.merge(parent_actual, on=parent_dimensions, how="left")
            union = union.merge(signal_totals, on=parent_dimensions, how="left")
            zero_signal = union["parentSignal"] <= 0
            if zero_signal.any():
                fallback_totals = (
                    union.groupby(parent_dimensions, as_index=False, dropna=False)[
                        "historySignal"
                    ]
                    .sum()
                    .rename(columns={"historySignal": "parentHistorySignal"})
                )
                union = union.merge(
                    fallback_totals, on=parent_dimensions, how="left"
                )
                use_fallback = (union["parentSignal"] <= 0) & (
                    union["parentHistorySignal"] > 0
                )
                union.loc[use_fallback, "signal"] = union.loc[
                    use_fallback, "historySignal"
                ]
                union["parentSignal"] = union.groupby(
                    parent_dimensions, dropna=False
                )["signal"].transform("sum")
            union["prediction"] = np.where(
                union["parentSignal"] > 0,
                union["parentActual"] * union["signal"] / union["parentSignal"],
                0.0,
            )
            parent_status = union[
                parent_dimensions + ["parentActual", "parentSignal"]
            ].drop_duplicates()
            parent_fold_total += int((parent_status["parentActual"] > 0).sum())
            parent_fold_covered += int(
                (
                    (parent_status["parentActual"] > 0)
                    & (parent_status["parentSignal"] > 0)
                ).sum()
            )
            zero_signal_parent_count += int(
                (
                    (parent_status["parentActual"] > 0)
                    & (parent_status["parentSignal"] <= 0)
                ).sum()
            )
            zero_parent_actual_count += int(
                (parent_status["parentActual"] <= 0).sum()
            )
            union["covered"] = union["signalAvailable"] & (
                union["parentSignal"] > 0
            )
            eligible_entity_rows += int(len(union))
            covered_entity_rows += int(union["covered"].sum())
            missing_signal_rows += int((~union["covered"]).sum())
            fold_audits.append(
                {
                    "originMonth": str(origin),
                    "targetMonth": target_month,
                    "horizon": horizon,
                    "originSignalHash": signal_hash,
                    "parentCount": int(len(parent_status)),
                    "coveredParentCount": int(
                        (parent_status["parentSignal"] > 0).sum()
                    ),
                    "entityCount": int(len(union)),
                    "coveredEntityCount": int(union["covered"].sum()),
                }
            )
            for _, child in union.iterrows():
                rows.append(
                    {
                        "origin_month": str(origin),
                        "target_month": target_month,
                        "horizon": horizon,
                        "actual": float(child["actual"]),
                        "prediction": max(float(child["prediction"]), 0.0),
                    }
                )
    metrics = summarize_predictions(pd.DataFrame(rows))
    expected = expected_fold_counts(len(all_months))
    complete_folds = len(fold_keys) == expected["combined"]
    prediction_coverage = (
        float(covered_entity_rows / eligible_entity_rows)
        if eligible_entity_rows
        else 0.0
    )
    parent_fold_coverage = (
        float(parent_fold_covered / parent_fold_total)
        if parent_fold_total
        else 0.0
    )
    sufficient_sample = len(fold_keys) >= 15 and metrics["actualTotal"] > 0
    validated = (
        bool(rows)
        and complete_folds
        and sufficient_sample
        and prediction_coverage == 1.0
        and parent_fold_coverage == 1.0
    )
    return {
        "evaluationScopeId": f"allocation_only_h123::{metric}::{level.lower()}",
        "level": level,
        "validationStatus": (
            "validated_allocation_only"
            if validated
            else "unvalidated_incomplete_coverage_or_sample"
        ),
        "scope": "allocationOnly",
        "target": METRIC_LABELS.get(metric, metric),
        "sourceHash": source_hash or "unavailable",
        "cutoff": latest_complete_month,
        "horizons": [1, 2, 3],
        "grain": " × ".join(["origin", "target", "horizon", *child_dimensions]),
        "signal": (
            "origin-known recent-six revenue-equivalent share: same-window quantity "
            "× same-window realized unit revenue (algebraically recent-six revenue), "
            "with prior-history signal fallback when the recent parent signal is zero"
            if metric == "revenue"
            else "origin-known recent-six quantity share"
        ),
        "isolationPolicy": (
            "Held-out target actual parent total is supplied only to isolate child-share error; "
            "this is not end-to-end forecast accuracy."
        ),
        "wape": metrics["wape"],
        "accuracy": metrics["accuracy"],
        "coverage": prediction_coverage,
        "predictionCoverage": prediction_coverage,
        "metricRowCoverage": metrics["predictionCoverage"],
        "parentFoldCoverage": parent_fold_coverage,
        "eligibleEntityRowCount": eligible_entity_rows,
        "coveredEntityRowCount": covered_entity_rows,
        "missingSignalRowCount": missing_signal_rows,
        "zeroSignalParentCount": zero_signal_parent_count,
        "zeroParentActualCount": zero_parent_actual_count,
        "parentFoldCount": parent_fold_total,
        "coveredParentFoldCount": parent_fold_covered,
        "rowCount": metrics["rowCount"],
        "foldCount": len(fold_keys),
        "expectedFoldCount": expected["combined"],
        "sourceScope": {
            "sourceHash": source_hash or "unavailable",
            "cutoff": latest_complete_month,
            "target": METRIC_LABELS.get(metric, metric),
            "completeMonthCount": len(all_months),
        },
        "foldAudits": fold_audits,
    }


def _legacy_forecast_exceptions(
    source: pd.DataFrame,
    model_records: list[dict[str, Any]],
    plc_records: list[dict[str, Any]],
    part_records: list[dict[str, Any]],
    *,
    metric: str,
    latest_complete_month: str,
    min_monthly_volume: float,
) -> list[dict[str, Any]]:
    exceptions: list[dict[str, Any]] = []
    forecast_month = next(
        (
            str(item.get("month"))
            for record in [*model_records, *plc_records]
            for item in record.get("forecast", [])
        ),
        latest_complete_month,
    )

    def emit(
        record: dict[str, Any],
        reason_code: str,
        severity: str,
        evidence: dict[str, Any],
        suggested_action: str,
        *,
        scope: str | None = None,
        month: str | None = None,
    ) -> None:
        resolved_scope = scope or (
            "PLC" if record.get("plc") else "Model"
        )
        series_key = str(
            record.get("seriesKey")
            or "::".join(
                str(record.get(key, ""))
                for key in ("brand", "entityKey", "plc", "partNumber")
            )
        )
        resolved_month = month or forecast_month
        exceptions.append(
            {
                "exceptionId": f"{reason_code}::{series_key}::{resolved_month}",
                "reasonCode": reason_code,
                "severity": severity,
                "scope": resolved_scope,
                "grain": (
                    "forecast month × brand × model × PLC × PIS_PNO"
                    if resolved_scope == "PIS_PNO"
                    else f"forecast month × {resolved_scope}"
                ),
                "seriesKey": series_key,
                "entityKey": str(record.get("entityKey", "")),
                "brand": str(record.get("brand", "")),
                "modelName": str(record.get("modelName", "")),
                "plc": str(record.get("plc", "")),
                "partNumber": str(record.get("partNumber", "")),
                "forecastMonth": resolved_month,
                "evidence": evidence,
                "suggestedAction": suggested_action,
            }
        )

    records = [*model_records, *plc_records]
    for record in records:
        route = str(record.get("allocationRoute", ""))
        active_months = int(record.get("activeMonths", 0) or 0)
        monthly_average = float(record.get("monthlyAverage", 0.0) or 0.0)
        if route == "excluded_lifecycle":
            emit(
                record,
                "inactive_discontinued",
                "high",
                {
                    "lifecycleStatus": record.get("lifecycleStatus"),
                    "lifecycleStatusCode": record.get("lifecycleStatusCode"),
                    "cutoff": latest_complete_month,
                },
                "Confirm lifecycle status; keep at zero unless a reviewed reactivation is approved.",
            )
        if monthly_average < min_monthly_volume:
            emit(
                record,
                "low_volume",
                "medium",
                {
                    "monthlyAverage": monthly_average,
                    "minimumMonthlyVolume": min_monthly_volume,
                },
                "Review sparse demand and retain exclusion or set a documented planner override.",
            )
        if active_months < 6:
            emit(
                record,
                "insufficient_active_months",
                "medium",
                {"activeMonths": active_months, "requiredActiveMonths": 6},
                "Collect more active-month history or use a governed proxy.",
            )
        if route == "new_model_proxy":
            emit(
                record,
                "new_reintroduced_proxy",
                "medium",
                {
                    "lifecycleStatus": record.get("lifecycleStatus"),
                    "historyMonths": record.get("historyMonths"),
                    "proxy": "recent run-rate",
                },
                "Review proxy assumptions until sufficient leakage-safe history exists.",
            )
        if route == "planner_review_residual":
            emit(
                record,
                "planner_review_residual",
                "high",
                {"allocationRoute": route, "historyVolume": record.get("historyVolume")},
                "Assign the residual to reviewed child entities before operational use.",
            )
        zero_forecast = any(
            float(item.get("value", 0.0)) == 0.0
            for item in record.get("forecast", [])
        )
        unit_price = float(record.get("expectedUnitRevenue", 0.0) or 0.0)
        if metric == "revenue" and zero_forecast and unit_price > 0:
            emit(
                record,
                "zero_forecast_historical_unit_price",
                "medium",
                {
                    "expectedUnitRevenue": unit_price,
                    "forecastValues": [
                        float(item.get("value", 0.0))
                        for item in record.get("forecast", [])
                    ],
                },
                "Confirm lifecycle/volume routing because a historical unit price still exists.",
            )

    if not source.empty:
        working = source.copy()
        working["month"] = working["month"].astype(str).str[:7]
        working = working[working["month"] <= latest_complete_month]
        value_column = (
            "pioRevenue" if metric == "revenue" else "installationQuantity"
        )
        if value_column in working.columns:
            for scope, dimensions, scope_records in (
                ("Model", ["brand", "entityKey", "modelName"], model_records),
                (
                    "PLC",
                    ["brand", "entityKey", "modelName", "plc"],
                    plc_records,
                ),
            ):
                monthly = (
                    working.groupby(dimensions + ["month"], as_index=False, dropna=False)[
                        value_column
                    ]
                    .sum()
                )
                record_lookup = {
                    tuple(str(record.get(key, "")) for key in dimensions): record
                    for record in scope_records
                }
                grouped = monthly.groupby(
                    dimensions[0] if len(dimensions) == 1 else dimensions,
                    dropna=False,
                )
                for raw_key, group in grouped:
                    key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
                    record = record_lookup.get(tuple(str(item) for item in key))
                    if record is None:
                        continue
                    series = group.set_index("month")[value_column].astype(float)
                    full_index = pd.period_range(
                        pd.Period(str(series.index.min()), freq="M"),
                        pd.Period(latest_complete_month, freq="M"),
                        freq="M",
                    ).astype(str)
                    complete = series.reindex(full_index, fill_value=0.0)
                    internal = complete.iloc[:-3] if len(complete) > 3 else complete.iloc[:0]
                    gap_months = [
                        str(index)
                        for index, value in internal.items()
                        if float(value) <= 0.0
                    ]
                    if gap_months:
                        emit(
                            record,
                            "history_gaps",
                            "medium",
                            {
                                "gapCount": len(gap_months),
                                "gapMonths": gap_months[-12:],
                                "knownThrough": latest_complete_month,
                            },
                            "Confirm missing activity versus true zero demand before overriding.",
                            scope=scope,
                        )
                    recent = complete.tail(3)
                    if len(recent) == 3 and (recent <= 0).all():
                        emit(
                            record,
                            "recent_zero_streak",
                            "high",
                            {
                                "zeroStreakMonths": [str(item) for item in recent.index],
                                "streakLength": 3,
                            },
                            "Review lifecycle and supply status before accepting a zero continuation.",
                            scope=scope,
                        )

    for record in part_records:
        if str(record.get("allocationRoute", "")) == "planner_review_residual":
            emit(
                record,
                "planner_review_residual",
                "high",
                {"allocationRoute": "planner_review_residual"},
                "Assign this exact-part residual before operational use.",
                scope="PIS_PNO",
                month=str(record.get("month", forecast_month)),
            )
        if (
            metric == "revenue"
            and float(record.get("value", 0.0)) == 0.0
            and float(record.get("expectedUnitRevenue", 0.0) or 0.0) > 0
        ):
            emit(
                record,
                "zero_forecast_historical_unit_price",
                "medium",
                {
                    "expectedUnitRevenue": record.get("expectedUnitRevenue"),
                    "forecastValue": record.get("value"),
                },
                "Review exact-part lifecycle and allocation share.",
                scope="PIS_PNO",
                month=str(record.get("month", forecast_month)),
            )
    deduplicated = {
        item["exceptionId"]: item for item in exceptions
    }
    return sorted(
        deduplicated.values(),
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(str(item["severity"]), 9),
            str(item["reasonCode"]),
            str(item["seriesKey"]),
        ),
    )


def _forecast_exceptions(
    source: pd.DataFrame,
    model_records: list[dict[str, Any]],
    plc_records: list[dict[str, Any]],
    part_records: list[dict[str, Any]],
    *,
    metric: str,
    latest_complete_month: str,
    min_monthly_volume: float,
) -> list[dict[str, Any]]:
    """Build cutoff-safe exceptions from complete pre-eligibility history."""

    forecast_months = _forecast_months(model_records or plc_records)
    profiles = _series_exception_profiles(
        source,
        latest_complete_month=latest_complete_month,
        min_monthly_volume=min_monthly_volume,
        include_parts=metric != "wholesale_quantity",
    )
    exceptions: list[dict[str, Any]] = []

    def emit(
        record: dict[str, Any],
        reason_code: str,
        severity: str,
        evidence: dict[str, Any],
        suggested_action: str,
        *,
        month: str | None = None,
        series_level: bool = True,
    ) -> None:
        scope = str(record["scope"])
        series_key = str(record["seriesKey"])
        exceptions.append(
            {
                "exceptionId": (
                    f"{reason_code}::{series_key}::"
                    f"{month if month is not None else 'SERIES'}"
                ),
                "reasonCode": reason_code,
                "severity": severity,
                "scope": scope,
                "grain": (
                    f"series-level {scope}"
                    if series_level
                    else f"forecast month × {scope}"
                ),
                "seriesLevel": series_level,
                "seriesKey": series_key,
                "entityKey": str(record.get("entityKey", "")),
                "brand": str(record.get("brand", "")),
                "modelName": str(record.get("modelName", "")),
                "plc": str(record.get("plc", "")),
                "partNumber": str(record.get("partNumber", "")),
                "forecastMonth": None if series_level else month,
                "evidence": {
                    **evidence,
                    "knownThrough": latest_complete_month,
                    "affectedForecastMonths": forecast_months,
                },
                "suggestedAction": suggested_action,
            }
        )

    for profile in profiles:
        lifecycle_code = str(profile.get("lifecycleStatusCode", "")).lower()
        lifecycle_label = str(profile.get("lifecycleStatus", ""))
        if lifecycle_code in {"inactive", "discontinued"} or lifecycle_label.startswith(
            ("Inactive", "Discontinued")
        ):
            emit(
                profile,
                "inactive_discontinued",
                "high",
                {
                    "lifecycleStatus": lifecycle_label,
                    "lifecycleStatusCode": lifecycle_code,
                },
                "Confirm lifecycle state; retain zero routing unless reactivation is approved.",
            )
        if float(profile["monthlyAverage"]) < min_monthly_volume:
            emit(
                profile,
                "low_volume",
                "medium",
                {
                    "monthlyAverage": float(profile["monthlyAverage"]),
                    "minimumMonthlyVolume": min_monthly_volume,
                },
                "Review sparse demand and retain exclusion or document an override.",
            )
        if int(profile["activeMonths"]) < 6:
            emit(
                profile,
                "insufficient_active_months",
                "medium",
                {
                    "activeMonths": int(profile["activeMonths"]),
                    "requiredActiveMonths": 6,
                },
                "Collect more active history or use a governed proxy.",
            )
        if int(profile["missingHistoryMonths"]) > 0:
            emit(
                profile,
                "history_gaps",
                "medium",
                {
                    "missingHistoryMonths": int(profile["missingHistoryMonths"]),
                    "observedHistoryMonths": int(profile["observedHistoryMonths"]),
                    "historyMonths": int(profile["historyMonths"]),
                },
                "Confirm whether absent months are true zero demand or missing data.",
            )
        if int(profile["recentPositiveMonths"]) == 0 and int(profile["historyMonths"]) >= 3:
            emit(
                profile,
                "recent_zero_streak",
                "high",
                {
                    "streakLength": 3,
                    "zeroStreakMonths": [
                        str(pd.Period(latest_complete_month, freq="M") - offset)
                        for offset in (2, 1, 0)
                    ],
                },
                "Review lifecycle and supply status before accepting zero continuation.",
            )
        if lifecycle_code in {"new", "reintroduced"}:
            emit(
                profile,
                "new_reintroduced_proxy",
                "medium",
                {
                    "lifecycleStatus": lifecycle_label,
                    "historyMonths": int(profile["historyMonths"]),
                    "proxy": "recent run-rate",
                },
                "Review proxy assumptions until sufficient history exists.",
            )

    profile_lookup = {
        (str(item["scope"]), str(item["seriesKey"])): item for item in profiles
    }
    forecast_records: list[dict[str, Any]] = []
    for scope, records in (("Model", model_records), ("PLC", plc_records)):
        forecast_records.extend({**record, "scope": scope} for record in records)
    for record in part_records:
        forecast_records.append(
            {
                **record,
                "scope": "PIS_PNO",
                "seriesKey": _part_series_key(record),
                "forecast": [
                    {
                        "month": record.get("month"),
                        "value": record.get("value", 0.0),
                    }
                ],
            }
        )
    forecast_lookup = {
        (str(record["scope"]), str(record.get("seriesKey", ""))): record
        for record in forecast_records
    }
    for key, profile in profile_lookup.items():
        record = forecast_lookup.get(key)
        unit_price = float(profile.get("historicalUnitRevenue", 0.0) or 0.0)
        if metric != "revenue" or unit_price <= 0:
            continue
        forecasts = record.get("forecast", []) if record is not None else []
        values_by_month = {
            str(item.get("month")): float(item.get("value", 0.0))
            for item in forecasts
        }
        excluded_without_rows = record is None and (
            float(profile["monthlyAverage"]) < min_monthly_volume
            or int(profile["activeMonths"]) < 6
            or (
                profile["scope"] == "PIS_PNO"
                and float(profile.get("recentSixQuantity", 0.0)) <= 0.0
            )
            or str(profile.get("lifecycleStatusCode", "")).lower()
            in {"inactive", "discontinued"}
        )
        for month in forecast_months:
            if (
                month in values_by_month and values_by_month[month] == 0.0
            ) or excluded_without_rows:
                emit(
                    profile,
                    "zero_forecast_historical_unit_price",
                    "medium",
                    {
                        "historicalUnitRevenue": unit_price,
                        "forecastValue": values_by_month.get(month, 0.0),
                    },
                    "Review routing because prior unit revenue exists.",
                    month=month,
                    series_level=False,
                )

    part_profiles = [item for item in profiles if item["scope"] == "PIS_PNO"]
    parent_routes = {
        (
            str(parent.get("brand", "")),
            str(parent.get("entityKey", "")),
            str(parent.get("modelName", "")),
            str(parent.get("plc", "")),
        ): str(parent.get("allocationRoute", "regular_allocation"))
        for parent in plc_records
    }
    parent_signals: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for item in part_profiles:
        parent_key = (
            str(item.get("brand", "")),
            str(item.get("entityKey", "")),
            str(item.get("modelName", "")),
            str(item.get("plc", "")),
        )
        parent_route = parent_routes.get(parent_key, "regular_allocation")
        eligible = (
            float(item["monthlyAverage"]) >= min_monthly_volume
            and str(item.get("lifecycleStatusCode", "")).lower()
            not in {"inactive", "discontinued"}
            and (
                float(item["recentSixQuantity"]) > 0
                if parent_route == "new_model_proxy"
                else int(item["activeMonths"]) >= 6
            )
        )
        if not eligible:
            continue
        unit_price = (
            float(item["recentSixRevenue"]) / float(item["recentSixQuantity"])
            if float(item["recentSixQuantity"]) > 0
            else float(item["historicalUnitRevenue"])
        )
        signals = parent_signals.setdefault(
            parent_key, {"latest": 0.0, "recentSix": 0.0}
        )
        if metric == "revenue":
            signals["latest"] += float(item["latestQuantity"]) * unit_price
            signals["recentSix"] += float(item["recentSixQuantity"]) * unit_price
        else:
            signals["latest"] += float(item["latestQuantity"])
            signals["recentSix"] += float(item["recentSixQuantity"])
    eligible_part_parents = {
        parent_key
        for parent_key, signals in parent_signals.items()
        if signals["latest"] > 0 or signals["recentSix"] > 0
    }
    for parent in plc_records:
        parent_key = (
            str(parent.get("brand", "")),
            str(parent.get("entityKey", "")),
            str(parent.get("modelName", "")),
            str(parent.get("plc", "")),
        )
        if parent_key in eligible_part_parents:
            continue
        synthetic = {
            **parent,
            "scope": "PIS_PNO",
            "partNumber": "PLANNER_REVIEW",
            "seriesKey": "::".join((*parent_key, "PLANNER_REVIEW")),
        }
        for forecast in parent.get("forecast", []):
            if float(forecast.get("value", 0.0)) <= 0:
                continue
            emit(
                synthetic,
                "planner_review_residual",
                "high",
                {
                    "allocationRoute": "planner_review_residual",
                    "forecastValue": float(forecast.get("value", 0.0)),
                },
                "Assign the residual to reviewed exact parts.",
                month=str(forecast.get("month")),
                series_level=False,
            )

    for scope, records in (("Model", model_records), ("PLC", plc_records)):
        for record in records:
            if str(record.get("allocationRoute", "")) != "planner_review_residual":
                continue
            profile = {
                **record,
                "scope": scope,
                "seriesKey": str(record.get("seriesKey", "")),
            }
            for forecast in record.get("forecast", []):
                emit(
                    profile,
                    "planner_review_residual",
                    "high",
                    {
                        "allocationRoute": "planner_review_residual",
                        "forecastValue": float(forecast.get("value", 0.0)),
                    },
                    "Assign the residual to reviewed child entities.",
                    month=str(forecast.get("month")),
                    series_level=False,
                )
    deduplicated = {item["exceptionId"]: item for item in exceptions}
    return sorted(
        deduplicated.values(),
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(str(item["severity"]), 9),
            str(item["reasonCode"]),
            str(item["seriesKey"]),
            str(item["forecastMonth"]),
        ),
    )


def _series_exception_profiles(
    source: pd.DataFrame,
    *,
    latest_complete_month: str,
    min_monthly_volume: float,
    include_parts: bool,
) -> list[dict[str, Any]]:
    if source.empty:
        return []
    working = source.copy()
    working["month"] = working["month"].astype(str).str[:7]
    working = working[working["month"] <= latest_complete_month]
    for column in ("installationQuantity", "pioRevenue"):
        if column not in working.columns:
            working[column] = 0.0
        working[column] = pd.to_numeric(
            working[column], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    if "lifecycleStatus" not in working.columns:
        working["lifecycleStatus"] = "Unknown"
    if "lifecycleStatusCode" not in working.columns:
        working["lifecycleStatusCode"] = working["lifecycleStatus"].map(
            _lifecycle_code_from_label
        )
    specs = [
        ("Model", ["brand", "entityKey", "modelName"]),
        ("PLC", ["brand", "entityKey", "modelName", "plc"]),
    ]
    if include_parts and "partNumber" in working.columns:
        specs.append(
            (
                "PIS_PNO",
                ["brand", "entityKey", "modelName", "plc", "partNumber"],
            )
        )
    cutoff = pd.Period(latest_complete_month, freq="M")
    recent_start = str(cutoff - 2)
    recent_six_start = str(cutoff - 5)
    profiles: list[dict[str, Any]] = []
    for scope, dimensions in specs:
        for dimension in dimensions:
            if dimension not in working.columns:
                working[dimension] = ""
        monthly = (
            working.groupby(dimensions + ["month"], as_index=False, dropna=False)
            .agg(
                quantity=("installationQuantity", "sum"),
                revenue=("pioRevenue", "sum"),
                lifecycleStatus=("lifecycleStatus", _mode_text),
                lifecycleStatusCode=("lifecycleStatusCode", _mode_text),
            )
        )
        monthly["positive"] = monthly["quantity"] > 0
        monthly["recentPositive"] = (
            (monthly["month"] >= recent_start) & monthly["positive"]
        )
        monthly["recentSixQuantity"] = np.where(
            monthly["month"] >= recent_six_start, monthly["quantity"], 0.0
        )
        monthly["recentSixRevenue"] = np.where(
            monthly["month"] >= recent_six_start, monthly["revenue"], 0.0
        )
        monthly["latestQuantity"] = np.where(
            monthly["month"] == latest_complete_month, monthly["quantity"], 0.0
        )
        monthly["latestRevenue"] = np.where(
            monthly["month"] == latest_complete_month, monthly["revenue"], 0.0
        )
        summary = (
            monthly.groupby(dimensions, as_index=False, dropna=False)
            .agg(
                historyQuantity=("quantity", "sum"),
                historyRevenue=("revenue", "sum"),
                activeMonths=("positive", "sum"),
                observedHistoryMonths=("month", "nunique"),
                recentPositiveMonths=("recentPositive", "sum"),
                recentSixQuantity=("recentSixQuantity", "sum"),
                recentSixRevenue=("recentSixRevenue", "sum"),
                latestQuantity=("latestQuantity", "sum"),
                latestRevenue=("latestRevenue", "sum"),
                firstMonth=("month", "min"),
                lifecycleStatus=("lifecycleStatus", _mode_text),
                lifecycleStatusCode=("lifecycleStatusCode", _mode_text),
            )
        )
        summary["historyMonths"] = summary["firstMonth"].map(
            lambda value: cutoff.ordinal
            - pd.Period(str(value), freq="M").ordinal
            + 1
        )
        summary["missingHistoryMonths"] = (
            summary["historyMonths"] - summary["observedHistoryMonths"]
        ).clip(lower=0)
        summary["monthlyAverage"] = (
            summary["historyQuantity"] / summary["historyMonths"].clip(lower=1)
        )
        summary["historicalUnitRevenue"] = np.where(
            summary["historyQuantity"] > 0,
            summary["historyRevenue"] / summary["historyQuantity"],
            0.0,
        )
        for _, row in summary.iterrows():
            payload = {dimension: str(row[dimension]) for dimension in dimensions}
            payload.update(
                {
                    "scope": scope,
                    "seriesKey": "::".join(
                        str(row[dimension]) for dimension in dimensions
                    ),
                    "plc": str(row.get("plc", "")),
                    "partNumber": str(row.get("partNumber", "")),
                    "activeMonths": int(row["activeMonths"]),
                    "observedHistoryMonths": int(row["observedHistoryMonths"]),
                    "recentPositiveMonths": int(row["recentPositiveMonths"]),
                    "historyMonths": int(row["historyMonths"]),
                    "missingHistoryMonths": int(row["missingHistoryMonths"]),
                    "monthlyAverage": float(row["monthlyAverage"]),
                    "historicalUnitRevenue": float(row["historicalUnitRevenue"]),
                    "recentSixQuantity": float(row["recentSixQuantity"]),
                    "recentSixRevenue": float(row["recentSixRevenue"]),
                    "latestQuantity": float(row["latestQuantity"]),
                    "latestRevenue": float(row["latestRevenue"]),
                    "lifecycleStatus": str(row["lifecycleStatus"]),
                    "lifecycleStatusCode": str(row["lifecycleStatusCode"]),
                    "minimumMonthlyVolume": min_monthly_volume,
                }
            )
            profiles.append(payload)
    return profiles


def _part_series_key(record: dict[str, Any]) -> str:
    return "::".join(
        str(record.get(key, ""))
        for key in ("brand", "entityKey", "modelName", "plc", "partNumber")
    )


def _mode_text(values: pd.Series) -> str:
    cleaned = values.dropna().astype(str).str.strip()
    cleaned = cleaned[(cleaned != "") & (cleaned.str.lower() != "nan")]
    return cleaned.mode().iloc[0] if not cleaned.empty else "Unknown"


def _empty_payload(
    metric: str,
    level: str,
    surface: str,
    horizon: int,
    top_n: int,
) -> dict[str, Any]:
    return {
        "summary": {
            "metric": metric,
            "metricLabel": METRIC_LABELS.get(metric, metric),
            "unit": "USD" if metric == "revenue" else "units",
            "level": level,
            "loadedSurface": surface,
            "seriesCount": 0,
            "allModelSeriesCount": 0,
            "allModelPlcSeriesCount": 0,
            "topN": top_n,
            "latestCompleteMonth": None,
            "latestObservedMonth": None,
            "dataThrough": None,
            "latestMonthExcluded": False,
            "latestMonthCompletenessRatio": None,
            "horizon": horizon,
            "forecastMonths": [],
            "nowcastMonths": [],
            "pureForecastMonths": [],
            "periodExplanation": "No usable history was found.",
            "weightedWape": None,
            "accuracyPct": None,
            "modelCounts": {},
            "brandDefinition": "Official anchors are HMA, GMA, and KUS.",
            "anchorPolicy": {
                "officialAnchors": list(OFFICIAL_ANCHORS),
                "sharedCutoff": None,
                "dealerWholesaleQuantityCoveragePct": 0.0,
                "fallbackQuantitySharePct": 0.0,
                "mappingMethods": {},
                "denominatorPolicy": {},
                "fleetPolicy": "",
                "negativeSentinelPolicy": "-1 is normalized to 0.",
                "modelVariantPolicy": "Exact model names are retained.",
            },
            "allocationRouting": {
                "model": {},
                "plc": {},
                "excludedModelSeries": 0,
                "excludedPlcSeries": 0,
                "newModelProxySeries": 0,
                "plannerReviewResiduals": 0,
            },
            "businessValidation": [],
            "reconciliation": {
                "status": "NOT_LOADED",
                "brandToModelMaxAbsDelta": 0.0,
                "modelToPlcMaxAbsDelta": 0.0,
                "tolerance": 0.01,
            },
            "factors": {},
            "formulaCatalog": _formula_catalog(metric),
            "accuracyDefinition": None,
            "accuracyScope": _accuracy_scope(metric),
            "evaluationScopes": [],
            "registeredEvidenceGate": {
                "evaluationScopeId": "governed_h123_24m_h1_18_h2_17_h3_16_official_total_51",
                "eligible": False,
                "validationStatus": "unvalidated_empty_scope",
                "checks": {},
            },
            "fairModelComparison": {
                "validationStatus": "unvalidated_not_same_contract",
                "comparisonType": "isolated_hma_ets_comparison",
                "rows": [],
            },
            "algorithmLeaderboard": {
                "validationStatus": "not_loaded",
                "disclosure": "Open Algorithm Leaderboard to load governed Brand-level evidence.",
                "rows": [],
            },
            "allocationAccuracy": [],
            "predictionIntervals": {
                "nominalCoverage": 0.90,
                "officialTotal": [],
                "brands": [],
                "childCoveragePolicy": (
                    "Child interval coverage is unvalidated without held-out child tests."
                ),
            },
            "modelGovernance": {
                "requestedStrategy": "auto",
                "sourceHash": "unavailable",
                "trainingCutoff": "",
                "backtestHorizons": [1],
                "foldCount": 0,
                "wapeScope": "no eligible Brand anchors",
                "accuracyProxy": None,
                "referenceMethodStatus": "not_reference_portfolio",
                "contractVersion": None,
                "brandSpecificMethods": {},
                "evaluationScopeId": "application_recent_h1",
                "validationGate": {},
            },
        },
        "records": [],
        "topAccessories": [],
        "brandRecords": [],
        "forecastExceptions": [],
    }
