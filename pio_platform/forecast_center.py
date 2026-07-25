from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from pio_platform.hierarchical_forecasting import build_hierarchical_forecast
from pio_platform.model_entities import normalize_model_name


FORECAST_CENTER_METRICS = {"quantity", "revenue", "wholesale_quantity"}
FORECAST_CENTER_LEVELS = {"brand", "model", "plc", "model_plc"}
BRAND_NAMES = {"H": "Hyundai / Genesis", "K": "Kia"}
METRIC_COLUMNS = {"quantity": "installationQuantity", "revenue": "pioRevenue"}
METRIC_LABELS = {
    "quantity": "PIO Quantity",
    "revenue": "PIO Revenue",
    "wholesale_quantity": "Wholesale Quantity",
}


def build_forecast_center(
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    wholesale_long: pd.DataFrame | None,
    *,
    metric: str,
    level: str,
    horizon: int = 3,
    use_working_days: bool = True,
    use_seasonality: bool = True,
    tariff_impact_pct: float = 0.0,
    model_strategy: str = "auto",
    top_n: int = 10,
    latest_sales_month_is_complete: bool = False,
    latest_sales_date: pd.Timestamp | None = None,
    include_all_records: bool = False,
) -> dict[str, Any]:
    if metric not in FORECAST_CENTER_METRICS:
        raise ValueError(f"Unsupported Forecast Center metric: {metric}")
    if level not in FORECAST_CENTER_LEVELS:
        raise ValueError(f"Unsupported Forecast Center level: {level}")
    if metric == "wholesale_quantity" and level in {"plc", "model_plc"}:
        raise ValueError("Wholesale Quantity is available at Brand and Model levels only.")
    if horizon < 1 or horizon > 12:
        raise ValueError("Forecast horizon must be between 1 and 12 months.")

    working_day_map = _working_day_map(working_days)
    if metric == "wholesale_quantity":
        source = _prepare_wholesale_facts(wholesale_long, working_days)
        latest_source_date = pd.Timestamp(latest_sales_date) if latest_sales_date is not None and pd.notna(latest_sales_date) else None
        latest_month_complete = latest_sales_month_is_complete
        check_latest_volume = True
    else:
        source = facts.copy()
        target_column = METRIC_COLUMNS[metric]
        if target_column not in source.columns:
            return _empty_payload(metric, level, horizon, top_n)
        source["installationQuantity"] = pd.to_numeric(source[target_column], errors="coerce").fillna(0.0).clip(lower=0)
        latest_source_date = pd.Timestamp(latest_sales_date) if latest_sales_date is not None and pd.notna(latest_sales_date) else None
        latest_month_complete = latest_sales_month_is_complete
        check_latest_volume = True

    if source.empty:
        return _empty_payload(metric, level, horizon, top_n)

    anchor = build_hierarchical_forecast(
        source,
        working_days,
        level="brand",
        horizon=horizon,
        use_working_days=use_working_days,
        use_seasonality=use_seasonality,
        tariff_impact_pct=tariff_impact_pct if metric != "wholesale_quantity" else 0.0,
        min_monthly_volume=0.0,
        model_strategy=model_strategy,
        limit=10,
        latest_month_is_complete=latest_month_complete,
        check_latest_volume=check_latest_volume,
    )
    brand_records = _decorate_brand_anchor(
        anchor,
        source,
        metric=metric,
        latest_source_date=latest_source_date,
        working_day_map=working_day_map,
    )
    latest_complete_month = anchor["summary"].get("latestCompleteMonth")
    if not latest_complete_month:
        return _empty_payload(metric, level, horizon, top_n)

    if metric == "wholesale_quantity":
        model_records = _allocate_records(
            source,
            metric=metric,
            child_dimensions=["brand", "entityKey", "modelName"],
            parent_dimensions=["brand"],
            parent_records=brand_records,
            latest_complete_month=latest_complete_month,
            working_day_map=working_day_map,
            use_working_days=use_working_days,
        )
        plc_records: list[dict[str, Any]] = []
        top_accessories: list[dict[str, Any]] = []
    else:
        model_records = _allocate_records(
            facts,
            metric=metric,
            child_dimensions=["brand", "entityKey", "modelName"],
            parent_dimensions=["brand"],
            parent_records=brand_records,
            latest_complete_month=latest_complete_month,
            working_day_map=working_day_map,
            use_working_days=use_working_days,
        )
        plc_records = _allocate_records(
            facts,
            metric=metric,
            child_dimensions=["brand", "entityKey", "modelName", "plc"],
            parent_dimensions=["brand", "entityKey", "modelName"],
            parent_records=model_records,
            latest_complete_month=latest_complete_month,
            working_day_map=working_day_map,
            use_working_days=use_working_days,
        )
        top_accessories = _aggregate_top_plcs(
            facts,
            plc_records,
            latest_complete_month=latest_complete_month,
            top_n=top_n,
        )

    if level == "brand":
        display_records = brand_records
    elif level == "model":
        display_records = model_records
    elif level == "plc":
        display_records = top_accessories
    else:
        top_plcs = {str(record["plc"]) for record in top_accessories}
        display_records = [record for record in plc_records if str(record.get("plc", "")) in top_plcs]

    reconciliation = _reconciliation_checks(brand_records, model_records, plc_records)
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
        "periodExplanation": _period_explanation(latest_complete_month, nowcast_months, pure_forecast_months, latest_source_date),
        "weightedWape": anchor["summary"].get("weightedWape"),
        "accuracyPct": anchor["summary"].get("accuracyPct"),
        "modelCounts": dict(model_counts),
        "brandDefinition": "H = Hyundai / Genesis combined; K = Kia. No inferred HMA/GMA company split.",
        "reconciliation": reconciliation,
        "factors": {
            "workingDays": use_working_days,
            "seasonality": use_seasonality,
            "tariffImpactPct": float(tariff_impact_pct if metric != "wholesale_quantity" else 0.0),
            "modelStrategy": model_strategy,
        },
        "formulaCatalog": _formula_catalog(metric),
        "accuracyDefinition": anchor["summary"].get("accuracyDefinition"),
    }
    payload: dict[str, Any] = {
        "summary": summary,
        "records": display_records,
        "topAccessories": top_accessories,
        "brandRecords": brand_records,
    }
    if include_all_records:
        payload["modelRecords"] = model_records
        payload["modelPlcRecords"] = plc_records
    return payload


def build_part_planning_records(
    facts: pd.DataFrame,
    model_plc_records: list[dict[str, Any]],
    *,
    metric: str,
    latest_complete_month: str,
) -> list[dict[str, Any]]:
    if metric not in {"quantity", "revenue"} or facts.empty or not model_plc_records:
        return []
    working = facts.copy()
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
        if subset.empty:
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
        if float(stats["rawWeight"].sum()) <= 0:
            stats["rawWeight"] = 1.0
        stats["share"] = stats["rawWeight"] / float(stats["rawWeight"].sum())
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
                        "expectedUnitRevenue": float(part["expectedUnitRevenue"]),
                        "value": float(forecast["value"]) * float(part["share"]),
                    }
                )
    return records


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
            historyQuantity=("installationQuantity", "sum"),
            historyRevenue=("pioRevenue", "sum"),
        )
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
        raw_forecast = []
        for month in forecast_months:
            signal = _allocation_signal(
                group,
                month,
                metric=metric,
                expected_unit_price=expected_price,
                working_day_map=working_day_map,
                use_working_days=use_working_days,
            )
            if lifecycle_status.startswith("Discontinued through"):
                signal = 0.0
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
            "historyVolume": history_volume,
            "historyQuantity": float(meta["historyQuantity"]) if meta is not None else 0.0,
            "historyRevenue": float(meta["historyRevenue"]) if meta is not None else 0.0,
            "expectedUnitRevenue": expected_price if metric == "revenue" else None,
            "selectedModel": "reconciled_allocation",
            "selectionNote": "Recent/seasonal quantity signal allocated to the official parent forecast and reconciled exactly.",
            "wape": None,
            "accuracyPct": None,
            "rawForecast": raw_forecast,
        }
        raw_records.append(record)

    parent_lookup = {
        tuple(str(record.get(column, "")) for column in parent_dimensions): record
        for record in parent_records
    }
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
            raw_values = [
                float(next(item["rawSignal"] for item in child["rawForecast"] if item["month"] == month))
                for child in children
            ]
            raw_total = float(sum(raw_values))
            if raw_total <= 0 and children:
                history_values = [max(float(child["historyVolume"]), 0.0) for child in children]
                history_total = float(sum(history_values))
                raw_values = history_values if history_total > 0 else [1.0] * len(children)
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
                "selectionNote": "Sum of all reconciled Brand × Model × PLC records.",
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
    working["brand"] = [
        _consolidated_wholesale_brand(brand, model)
        for brand, model in zip(working.get("brand", ""), working["modelName"], strict=False)
    ]
    working = working[working["brand"].isin(BRAND_NAMES)]
    working["entityKey"] = [
        f"{brand}::{normalize_model_name(model)}"
        for brand, model in zip(working["brand"], working["modelName"], strict=False)
    ]
    working["installationQuantity"] = pd.to_numeric(working["wholesaleUnits"], errors="coerce").fillna(0.0).clip(lower=0)
    working["pioRevenue"] = 0.0
    working["plc"] = ""
    working["partNumber"] = ""
    working["partDescription"] = ""
    working["lifecycleStatus"] = "Active"
    if working_days is not None and not working_days.empty:
        working = working.merge(working_days[["month", "workingDays"]], on="month", how="left")
    else:
        working["workingDays"] = pd.NA
    return working


def _consolidated_wholesale_brand(value: Any, model_name: Any) -> str:
    label = str(value or "").upper()
    model = str(model_name or "").upper()
    if "KUS" in label or "KIA" in label or label.strip() == "K":
        return "K"
    if any(token in label for token in ["HMA", "GMA", "HYUNDAI", "GENESIS"]) or label.strip() == "H":
        return "H"
    kia_models = {"CARNIVAL", "EV6", "EV9", "FORTE", "K4", "K5", "NIRO", "SELTOS", "SORENTO", "SOUL", "SPORTAGE", "TELLURIDE"}
    return "K" if normalize_model_name(model) in kia_models else "H"


def _allocation_signal(
    group: pd.DataFrame,
    forecast_month: str,
    *,
    metric: str,
    expected_unit_price: float,
    working_day_map: dict[str, float],
    use_working_days: bool,
) -> float:
    values_column = "installationQuantity"
    group = group.sort_values("month")
    latest_month = pd.Period(str(group["month"].max()), freq="M")
    recent_months = [(latest_month - offset).strftime("%Y-%m") for offset in range(5, -1, -1)]
    recent_series = group.set_index("month")[values_column].reindex(recent_months, fill_value=0.0)
    recent_base = float(recent_series.mean())
    future_days = float(working_day_map.get(forecast_month, np.mean(list(working_day_map.values())) if working_day_map else 21.0))
    recent_days = [working_day_map.get(month) for month in recent_months if working_day_map.get(month)]
    recent_day_mean = float(np.mean(recent_days)) if recent_days else future_days
    recent_adjusted = recent_base * (future_days / recent_day_mean) if use_working_days and recent_day_mean > 0 else recent_base

    forecast_month_number = int(forecast_month[-2:])
    seasonal = group[group["month"].astype(str).str[-2:].astype(int) == forecast_month_number]
    if len(seasonal) >= 2:
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


def _period_explanation(
    latest_complete_month: str,
    nowcast_months: list[str],
    forecast_months: list[str],
    latest_source_date: pd.Timestamp | None,
) -> str:
    parts = [f"Training uses completed months through {latest_complete_month}."]
    if nowcast_months:
        cutoff = latest_source_date.date().isoformat() if latest_source_date is not None else "the latest observed date"
        parts.append(f"{', '.join(nowcast_months)} is a full-month nowcast using actuals through {cutoff}.")
    if forecast_months:
        parts.append(f"Pure forecast months: {', '.join(forecast_months)}.")
    return " ".join(parts)


def _formula_catalog(metric: str) -> list[dict[str, str]]:
    formulas = [
        {
            "name": "Brand anchor",
            "formula": "Official Brand Forecast = lowest rolling-WAPE eligible model forecast",
            "logic": "Candidates include recent-average, trend, seasonal, intermittent, additive ETS, and OLS driver models when eligible.",
        },
        {
            "name": "Working-day feature",
            "formula": "x_wd = (WorkingDays - meanWorkingDays) / meanWorkingDays",
            "logic": "The uploaded monthly Working_Days table is used for historical and future months.",
        },
        {
            "name": "Current-month nowcast",
            "formula": "Nowcast = MTD Actual + (1 - Estimated WD Completion) × Statistical Full-Month Baseline",
            "logic": "Estimated WD Completion prorates the uploaded monthly working-day total by elapsed calendar weekdays.",
        },
        {
            "name": "Lower-level quantity signal",
            "formula": "Raw Qty = 60% × WD-adjusted seasonal mean + 40% × WD-adjusted recent-6 mean",
            "logic": "If fewer than two same-calendar-month observations exist, the recent-6 signal is used.",
        },
        {
            "name": "Reconciliation",
            "formula": "Child Forecast = Parent Forecast × Raw Child Signal / Σ Raw Child Signals",
            "logic": "Model totals equal Brand; PLC totals equal Model for every forecast month.",
        },
    ]
    if metric == "revenue":
        formulas.insert(
            4,
            {
                "name": "Revenue allocation signal",
                "formula": "Raw Revenue = Raw Quantity × Expected Unit Revenue",
                "logic": "Expected unit revenue uses the latest three completed months, then falls back to the parent level.",
            },
        )
    if metric == "wholesale_quantity":
        formulas = [formula for formula in formulas if formula["name"] != "Revenue allocation signal"]
    return formulas


def _mode_text(values: pd.Series) -> str:
    cleaned = values.dropna().astype(str).str.strip()
    cleaned = cleaned[(cleaned != "") & (cleaned.str.lower() != "nan")]
    return cleaned.mode().iloc[0] if not cleaned.empty else "Unknown"


def _empty_payload(metric: str, level: str, horizon: int, top_n: int) -> dict[str, Any]:
    return {
        "summary": {
            "metric": metric,
            "metricLabel": METRIC_LABELS.get(metric, metric),
            "unit": "USD" if metric == "revenue" else "units",
            "level": level,
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
            "brandDefinition": "H = Hyundai / Genesis combined; K = Kia.",
            "reconciliation": {
                "status": "PASS",
                "brandToModelMaxAbsDelta": 0.0,
                "modelToPlcMaxAbsDelta": 0.0,
                "tolerance": 0.01,
            },
            "factors": {},
            "formulaCatalog": _formula_catalog(metric),
            "accuracyDefinition": None,
        },
        "records": [],
        "topAccessories": [],
        "brandRecords": [],
    }
