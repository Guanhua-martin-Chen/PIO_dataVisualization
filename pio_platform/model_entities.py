from __future__ import annotations

import re
from typing import Any

import pandas as pd


def normalize_model_name(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\s+", " ", text.strip().upper())
    return text


def normalize_brand(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    return re.sub(r"\s+", " ", text.strip().upper())


def model_entity_key(model_name: Any, brand: Any = "") -> str:
    """Stable model-name entity key; model code is intentionally excluded.

    Model codes are many-to-many in the source (for example one code can cover
    base, N, HEV, and EV variants), so they are retained as attributes only.
    """
    model_key = normalize_model_name(model_name)
    brand_key = normalize_brand(brand)
    return f"{brand_key or 'UNKNOWN'}::{model_key}" if model_key else ""


def build_model_entity_map(
    df: pd.DataFrame,
    *,
    model_col: str | None,
    brand_col: str | None = None,
    model_code_col: str | None = None,
    model_year_col: str | None = None,
) -> dict[str, Any]:
    if not model_col or model_col not in df.columns:
        return {"count": 0, "records": []}

    working = pd.DataFrame(index=df.index)
    working["modelName"] = df[model_col].fillna("").astype(str).str.strip()
    working["modelKey"] = working["modelName"].map(normalize_model_name)
    working["brand"] = (
        df[brand_col].fillna("").astype(str).str.strip() if brand_col and brand_col in df.columns else ""
    )
    working["brandKey"] = working["brand"].map(normalize_brand)
    working["modelCode"] = (
        df[model_code_col].fillna("").astype(str).str.strip()
        if model_code_col and model_code_col in df.columns
        else ""
    )
    working["modelYear"] = (
        df[model_year_col].fillna("").astype(str).str.strip()
        if model_year_col and model_year_col in df.columns
        else ""
    )
    working = working[working["modelKey"] != ""].copy()
    if working.empty:
        return {"count": 0, "records": []}

    working["entityKey"] = [
        model_entity_key(model, brand)
        for model, brand in zip(working["modelName"], working["brand"], strict=False)
    ]

    records: list[dict[str, Any]] = []
    for entity_key, group in working.groupby("entityKey", sort=True):
        model_names = group["modelName"][group["modelName"] != ""]
        brands = sorted({value for value in group["brand"] if value})
        model_codes = sorted({value for value in group["modelCode"] if value})
        model_years = sorted({value for value in group["modelYear"] if value})
        records.append(
            {
                "entityKey": entity_key,
                "modelName": model_names.mode().iloc[0] if not model_names.empty else entity_key.split("::", 1)[-1],
                "brand": brands[0] if len(brands) == 1 else " / ".join(brands),
                "modelCodes": model_codes,
                "modelYears": model_years,
                "rowCount": int(len(group)),
            }
        )
    return {"count": len(records), "records": records}


def build_model_lifecycle(
    df: pd.DataFrame,
    date_series: pd.Series,
    *,
    model_col: str | None,
    qty_col: str | None,
    brand_col: str | None = None,
    model_code_col: str | None = None,
    cutoff_year: int = 2024,
    reintroduction_gap_months: int = 12,
) -> dict[str, Any]:
    if not model_col or model_col not in df.columns:
        return _empty_lifecycle(cutoff_year)

    working = pd.DataFrame(index=df.index)
    working["date"] = pd.to_datetime(date_series.reindex(df.index), errors="coerce")
    working["modelName"] = df[model_col].fillna("").astype(str).str.strip()
    working["brand"] = (
        df[brand_col].fillna("").astype(str).str.strip() if brand_col and brand_col in df.columns else ""
    )
    working["modelCode"] = (
        df[model_code_col].fillna("").astype(str).str.strip()
        if model_code_col and model_code_col in df.columns
        else ""
    )
    working["quantity"] = (
        pd.to_numeric(df[qty_col], errors="coerce").fillna(0).clip(lower=0)
        if qty_col and qty_col in df.columns
        else 1.0
    )
    working = working[(working["date"].notna()) & (working["modelName"] != "") & (working["quantity"] > 0)]
    if working.empty:
        return _empty_lifecycle(cutoff_year)

    working["month"] = working["date"].dt.to_period("M")
    working["entityKey"] = [
        model_entity_key(model, brand)
        for model, brand in zip(working["modelName"], working["brand"], strict=False)
    ]
    data_end = working["month"].max()
    cutoff = pd.Period(f"{cutoff_year}-12", freq="M")

    records: list[dict[str, Any]] = []
    for entity_key, group in working.groupby("entityKey", sort=True):
        months = sorted(group["month"].unique())
        first_month = months[0]
        last_month = months[-1]
        gaps = [months[index].ordinal - months[index - 1].ordinal - 1 for index in range(1, len(months))]
        max_gap = max(gaps, default=0)
        reintroduced_month = None
        if max_gap >= reintroduction_gap_months:
            gap_index = gaps.index(max_gap) + 1
            reintroduced_month = months[gap_index]

        discontinued = bool(last_month <= cutoff and data_end > cutoff)
        reintroduced = reintroduced_month is not None
        inactive_months = max(0, data_end.ordinal - last_month.ordinal)
        if discontinued:
            status_code = "discontinued"
            status = f"Discontinued through {cutoff_year}"
        elif reintroduced:
            status_code = "reintroduced"
            status = "Reintroduced"
        elif inactive_months >= reintroduction_gap_months:
            status_code = "inactive"
            status = "Inactive"
        else:
            status_code = "active"
            status = "Active"

        model_names = group["modelName"].mode()
        model_name = model_names.iloc[0] if not model_names.empty else entity_key.split("::", 1)[-1]
        codes = sorted({value for value in group["modelCode"] if value})
        if discontinued:
            evidence = f"Last positive PIO month was {last_month}; no later positive activity exists through {data_end}."
        elif reintroduced_month is not None:
            evidence = f"Positive PIO activity resumed in {reintroduced_month} after {max_gap} inactive month(s)."
        elif status_code == "inactive":
            evidence = f"Last positive PIO month was {last_month}; the model has {inactive_months} inactive month(s) through {data_end}."
        else:
            evidence = f"Positive PIO activity continues through {last_month}."

        records.append(
            {
                "entityKey": entity_key,
                "modelName": model_name,
                "brand": normalize_brand(group["brand"].mode().iloc[0]) if not group["brand"].mode().empty else "",
                "modelCodes": codes,
                "firstPositiveMonth": str(first_month),
                "lastPositiveMonth": str(last_month),
                "status": status,
                "statusCode": status_code,
                "discontinuedThroughCutoff": discontinued,
                "reintroduced": reintroduced,
                "reintroducedMonth": str(reintroduced_month) if reintroduced_month is not None else None,
                "longestInactiveGapMonths": int(max_gap),
                "inactiveMonthsAtDataEnd": int(inactive_months),
                "evidence": evidence,
            }
        )

    status_order = {"discontinued": 0, "reintroduced": 1, "inactive": 2, "active": 3}
    records.sort(key=lambda item: (status_order[item["statusCode"]], item["modelName"]))
    return {
        "cutoffYear": cutoff_year,
        "asOfMonth": str(data_end),
        "entityCount": len(records),
        "discontinuedCount": sum(1 for item in records if item["discontinuedThroughCutoff"]),
        "reintroducedCount": sum(1 for item in records if item["reintroduced"]),
        "inactiveCount": sum(1 for item in records if item["statusCode"] == "inactive"),
        "records": records,
    }


def _empty_lifecycle(cutoff_year: int) -> dict[str, Any]:
    return {
        "cutoffYear": cutoff_year,
        "asOfMonth": None,
        "entityCount": 0,
        "discontinuedCount": 0,
        "reintroducedCount": 0,
        "inactiveCount": 0,
        "records": [],
    }
