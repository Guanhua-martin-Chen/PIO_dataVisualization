from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from pio_platform.hierarchical_forecasting import build_hierarchical_forecast
from pio_platform.fact_table import OFFICIAL_ANCHORS, normalize_anchor_brand
from pio_platform.model_entities import build_model_lifecycle, normalize_model_name


FORECAST_CENTER_METRICS = {"quantity", "revenue", "wholesale_quantity"}
FORECAST_CENTER_LEVELS = {"brand", "model", "plc", "model_plc"}
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
    min_monthly_volume: float = 5.0,
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
        anchor_source = source
        latest_source_date = pd.Timestamp(latest_sales_date) if latest_sales_date is not None and pd.notna(latest_sales_date) else None
        latest_month_complete = latest_sales_month_is_complete
        check_latest_volume = True
    else:
        source = _prepare_pio_anchor_facts(facts)
        target_column = METRIC_COLUMNS[metric]
        if target_column not in source.columns:
            return _empty_payload(metric, level, horizon, top_n)
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
        return _empty_payload(metric, level, horizon, top_n)

    anchor = build_hierarchical_forecast(
        anchor_source,
        working_days,
        level="brand",
        horizon=horizon,
        use_working_days=use_working_days,
        use_seasonality=use_seasonality,
        tariff_impact_pct=tariff_impact_pct if metric != "wholesale_quantity" else 0.0,
        min_monthly_volume=0.0,
        model_strategy=model_strategy,
        limit=len(OFFICIAL_ANCHORS),
        latest_month_is_complete=latest_month_complete,
        check_latest_volume=check_latest_volume,
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
            min_monthly_volume=min_monthly_volume,
        )
        plc_records: list[dict[str, Any]] = []
        top_accessories: list[dict[str, Any]] = []
    else:
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
        "weightedWape": anchor["summary"].get("weightedWape"),
        "accuracyPct": anchor["summary"].get("accuracyPct"),
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
            "KUS": "Dealer / non-fleet wholesale; fleet excluded",
        },
        "fleetPolicy": (
            "Fleet vehicle volume is excluded from the denominator and is not added to PIO quantity/revenue. "
            "The source PIO actual has no channel field, so whether fleet accessory transactions are embedded remains unobservable."
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
            "status": str(reconciliation.get("status", "WARN")),
            "detail": (
                f"Maximum parent/child delta is "
                f"{max(float(reconciliation.get('brandToModelMaxAbsDelta', 0.0)), float(reconciliation.get('modelToPlcMaxAbsDelta', 0.0))):.6f}."
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
        channel = wholesale_long.get(
            "channel",
            pd.Series("Dealer / non-fleet", index=wholesale_long.index),
        ).fillna("").astype(str)
        checks.append(
            {
                "check": "Dealer wholesale denominator",
                "status": (
                    "PASS"
                    if not channel.str.strip().str.lower().isin({"fleet", "fleet wholesale"}).any()
                    else "FAIL"
                ),
                "detail": "HMA, GMA, and KUS use dealer/non-fleet wholesale under the current business rule; fleet is excluded.",
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
            fallback_groups.append(
                f"{model_name} -> {anchor_brand} "
                f"({str(group['month'].min())[:7]} to {str(group['month'].max())[:7]}; "
                "no exact dealer-wholesale model match)"
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
                else "Wholesale Quantity uses only dealer/non-fleet vehicle wholesale; fleet is excluded."
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
                "For example, 2026-07 contains 22 full-month working days even though the data cutoff is July 22."
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
        "evaluatedGrain": "month x selected official brand anchor(s) from HMA/GMA/KUS",
        "overallFormula": (
            "Overall Accuracy = max(0, 1 - SUM(absolute backtest error across selected governed anchors) "
            "/ SUM(actual across selected governed anchors)). It is volume-weighted, not a simple average of anchor percentages."
        ),
        "anchorFormula": "Each anchor Accuracy = max(0, 1 - anchor independent-test WAPE).",
        "childPolicy": (
            "Model, PLC, and exact-part results are reconciled allocations of the official brand anchors. "
            "They do not currently have separate independent accuracy scores."
        ),
    }


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
                "status": "PASS",
                "brandToModelMaxAbsDelta": 0.0,
                "modelToPlcMaxAbsDelta": 0.0,
                "tolerance": 0.01,
            },
            "factors": {},
            "formulaCatalog": _formula_catalog(metric),
            "accuracyDefinition": None,
            "accuracyScope": _accuracy_scope(metric),
        },
        "records": [],
        "topAccessories": [],
        "brandRecords": [],
    }
