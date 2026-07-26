from __future__ import annotations

import re
from typing import Any

import pandas as pd

from pio_platform.data_loader import parse_date_series
from pio_platform.model_entities import model_entity_key, normalize_model_name


MONTH_NUMBERS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

OFFICIAL_ANCHORS = ("HMA", "GMA", "KUS")
GENESIS_MODEL_PREFIXES = ("G70", "G80", "G90", "GV60", "GV70", "GV80")


def build_wholesale_long(
    df: pd.DataFrame,
    sheet_name: str,
    *,
    latest_sales_year: int | None = None,
) -> pd.DataFrame:
    columns = list(df.columns)
    model_col = next((col for col in columns if str(col).strip().lower() == "model"), None)
    brand_col = next((col for col in columns if str(col).strip().lower() == "brand"), None)
    code_col = next((col for col in columns if str(col).strip().lower() in {"model code", "model_code", "modelcode"}), None)
    if model_col is None:
        return _empty_wholesale()

    month_columns: list[tuple[str, int, int]] = []
    block_numbers: set[int] = set()
    for column in columns:
        label = str(column).strip()
        match = re.match(r"^([A-Za-z]+)(?:\s*\((\d+)\))?$", label)
        if not match:
            continue
        month_number = MONTH_NUMBERS.get(match.group(1).lower())
        if month_number is None:
            continue
        block_number = int(match.group(2) or 1)
        block_numbers.add(block_number)
        month_columns.append((column, month_number, block_number))
    if not month_columns:
        return _empty_wholesale()

    year_match = re.search(r"(20\d{2})", sheet_name)
    if year_match:
        start_year = int(year_match.group(1))
    elif latest_sales_year is not None:
        start_year = latest_sales_year - max(block_numbers) + 1
    else:
        start_year = pd.Timestamp.now().year - max(block_numbers) + 1

    records: list[dict[str, Any]] = []
    active_brand = ""
    channel = "wholesale"
    for _, row in df.iterrows():
        raw_brand = str(row.get(brand_col, "")).strip() if brand_col else ""
        normalized_brand = raw_brand.lower()
        if "fleet" in normalized_brand:
            channel = "fleet"
            continue
        if "wholesale" in normalized_brand:
            channel = "wholesale"
            continue
        if raw_brand and normalized_brand != "nan" and not _is_total_label(raw_brand):
            active_brand = raw_brand
        if channel != "wholesale":
            continue

        model_name = str(row.get(model_col, "")).strip()
        if (
            not model_name
            or model_name.lower() == "nan"
            or _is_total_label(model_name)
            or _is_total_label(raw_brand)
        ):
            continue
        if _is_total_label(active_brand):
            continue
        model_code = str(row.get(code_col, "")).strip() if code_col else ""
        if model_code.lower() == "nan":
            model_code = ""

        for column, month_number, block_number in month_columns:
            units = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
            if pd.isna(units):
                continue
            units = max(float(units), 0.0)
            year = start_year + block_number - 1
            records.append(
                {
                    "month": f"{year:04d}-{month_number:02d}",
                    "brand": active_brand,
                    "anchorBrand": normalize_anchor_brand(active_brand, model_name=model_name),
                    "modelName": model_name,
                    "modelKey": normalize_model_name(model_name),
                    "modelCode": model_code,
                    "wholesaleUnits": units,
                    "channel": "Dealer / non-fleet",
                    "sourceSheet": sheet_name,
                }
            )
    if not records:
        return _empty_wholesale()
    result = pd.DataFrame(records)
    result = result[result["anchorBrand"].isin(OFFICIAL_ANCHORS)].copy()
    if result.empty:
        return _empty_wholesale()
    result = (
        result.groupby(["month", "anchorBrand", "modelKey"], as_index=False)
        .agg(
            brand=("brand", _join_unique),
            modelName=("modelName", _mode_text),
            modelCode=("modelCode", _join_unique),
            wholesaleUnits=("wholesaleUnits", "sum"),
            channel=("channel", _mode_text),
            sourceSheet=("sourceSheet", _join_unique),
        )
    )
    return result


def normalize_anchor_brand(value: Any, *, model_name: Any = "", source_brand: Any = "") -> str:
    """Resolve the governed company anchor without collapsing model variants."""
    label = normalize_model_name(value)
    source = normalize_model_name(source_brand)
    model = normalize_model_name(model_name)
    if source in OFFICIAL_ANCHORS:
        return source
    if "KUS" in label or "KIA" in label or label == "K" or source == "K":
        return "KUS"
    if "GMA" in label or "GENESIS" in label:
        return "GMA"
    if "HMA" in label or "HYUNDAI" in label:
        return "HMA"
    if model.startswith(GENESIS_MODEL_PREFIXES):
        return "GMA"
    if source == "H":
        return "HMA"
    return ""


def build_model_anchor_map(wholesale_long: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    """Choose the strongest dealer-wholesale anchor for each exact model name."""
    if wholesale_long is None or wholesale_long.empty or "modelKey" not in wholesale_long.columns:
        return {}
    working = wholesale_long.copy()
    if "anchorBrand" not in working.columns:
        working["anchorBrand"] = [
            normalize_anchor_brand(brand, model_name=model)
            for brand, model in zip(
                working.get("brand", pd.Series("", index=working.index)),
                working.get("modelName", pd.Series("", index=working.index)),
                strict=False,
            )
        ]
    working["modelKey"] = working["modelKey"].fillna("").astype(str).map(normalize_model_name)
    working["wholesaleUnits"] = pd.to_numeric(working.get("wholesaleUnits"), errors="coerce").fillna(0.0).clip(lower=0)
    working = working[
        (working["modelKey"] != "")
        & working["anchorBrand"].isin(OFFICIAL_ANCHORS)
    ].copy()
    if working.empty:
        return {}
    volumes = (
        working.groupby(["modelKey", "anchorBrand"], as_index=False)
        .agg(
            wholesaleUnits=("wholesaleUnits", "sum"),
            activeMonths=("wholesaleUnits", lambda values: int((values > 0).sum())),
        )
        .sort_values(
            ["modelKey", "wholesaleUnits", "activeMonths", "anchorBrand"],
            ascending=[True, False, False, True],
            kind="stable",
        )
    )
    mapping: dict[str, dict[str, Any]] = {}
    for model_key, group in volumes.groupby("modelKey", sort=True):
        selected = group.iloc[0]
        positive = group[group["wholesaleUnits"] > 0]
        candidate_anchors = positive["anchorBrand"].astype(str).tolist() or group["anchorBrand"].astype(str).tolist()
        mapping[str(model_key)] = {
            "anchorBrand": str(selected["anchorBrand"]),
            "method": (
                "dealer_wholesale_exact"
                if len(set(candidate_anchors)) == 1
                else "dealer_wholesale_volume_resolved"
            ),
            "candidateAnchors": sorted(set(candidate_anchors)),
            "wholesaleUnits": float(selected["wholesaleUnits"]),
        }
    alias_candidates: dict[str, list[dict[str, Any]]] = {}
    for model_key, item in mapping.items():
        for alias in _model_anchor_aliases(model_key):
            if alias != model_key:
                alias_candidates.setdefault(alias, []).append(item)
    for alias, candidates in alias_candidates.items():
        if alias in mapping:
            continue
        anchors = {str(item["anchorBrand"]) for item in candidates}
        if len(anchors) == 1:
            mapping[alias] = {
                "anchorBrand": next(iter(anchors)),
                "method": "dealer_wholesale_variant_alias",
                "candidateAnchors": sorted(anchors),
                "wholesaleUnits": float(sum(float(item["wholesaleUnits"]) for item in candidates)),
            }
    return mapping


def build_working_days_long(df: pd.DataFrame) -> pd.DataFrame:
    month_col = next((col for col in df.columns if str(col).strip().lower() in {"month", "yyyymm", "period"}), None)
    days_col = next((col for col in df.columns if "working day" in str(col).strip().lower()), None)
    if month_col is None or days_col is None:
        return pd.DataFrame(columns=["month", "workingDays"])
    months = parse_date_series(df[month_col])
    days = pd.to_numeric(df[days_col], errors="coerce").clip(lower=0)
    result = pd.DataFrame({"month": months.dt.to_period("M").astype(str), "workingDays": days}).dropna()
    return result.groupby("month", as_index=False)["workingDays"].max()


def build_monthly_fact_table(
    sales_df: pd.DataFrame,
    date_series: pd.Series,
    *,
    brand_col: str | None,
    model_col: str | None,
    model_code_col: str | None,
    part_number_col: str | None,
    part_description_col: str | None,
    qty_col: str | None,
    revenue_col: str | None,
    plc_col: str | None = None,
    wholesale_long: pd.DataFrame | None = None,
    working_days_long: pd.DataFrame | None = None,
    lifecycle_records: list[dict[str, Any]] | None = None,
    start_year: int = 2023,
    end_year: int = 2026,
) -> pd.DataFrame:
    required = [model_col, part_number_col, qty_col]
    if any(column is None or column not in sales_df.columns for column in required):
        return _empty_facts()

    working = pd.DataFrame(index=sales_df.index)
    working["date"] = pd.to_datetime(date_series.reindex(sales_df.index), errors="coerce")
    working["month"] = working["date"].dt.to_period("M").astype(str)
    working["brand"] = sales_df[brand_col].fillna("").astype(str).str.strip() if brand_col and brand_col in sales_df else ""
    working["modelName"] = sales_df[model_col].fillna("").astype(str).str.strip()
    working["modelKey"] = working["modelName"].map(normalize_model_name)
    working["modelCode"] = sales_df[model_code_col].fillna("").astype(str).str.strip() if model_code_col and model_code_col in sales_df else ""
    working["partNumber"] = sales_df[part_number_col].fillna("").astype(str).str.strip()
    working["partDescription"] = (
        sales_df[part_description_col].fillna("").astype(str).str.strip()
        if part_description_col and part_description_col in sales_df
        else ""
    )
    working["plc"] = (
        sales_df[plc_col].fillna("").astype(str).str.strip()
        if plc_col and plc_col in sales_df
        else working["partDescription"]
    )
    working["plc"] = working["plc"].where(working["plc"] != "", working["partNumber"])
    working["installationQuantity"] = pd.to_numeric(sales_df[qty_col], errors="coerce").fillna(0).clip(lower=0)
    working["pioRevenue"] = (
        pd.to_numeric(sales_df[revenue_col], errors="coerce").fillna(0).clip(lower=0)
        if revenue_col and revenue_col in sales_df
        else 0.0
    )
    working = working[
        working["date"].dt.year.between(start_year, end_year, inclusive="both")
        & (working["modelKey"] != "")
        & (working["partNumber"] != "")
    ].copy()
    if working.empty:
        return _empty_facts()
    anchor_map = build_model_anchor_map(wholesale_long)
    anchor_assignments = [
        _assign_sales_anchor(source_brand, model_name, model_key, anchor_map)
        for source_brand, model_name, model_key in zip(
            working["brand"], working["modelName"], working["modelKey"], strict=False
        )
    ]
    working["anchorBrand"] = [assignment["anchorBrand"] for assignment in anchor_assignments]
    working["anchorMappingMethod"] = [assignment["method"] for assignment in anchor_assignments]
    working["entityKey"] = [
        model_entity_key(model, brand)
        for model, brand in zip(working["modelName"], working["brand"], strict=False)
    ]

    facts = (
        working.groupby(
            [
                "month", "brand", "anchorBrand", "anchorMappingMethod", "entityKey",
                "modelKey", "modelName", "plc", "partNumber",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            modelCode=("modelCode", _join_unique),
            partDescription=("partDescription", _mode_text),
            installationQuantity=("installationQuantity", "sum"),
            pioRevenue=("pioRevenue", "sum"),
            sourceRows=("partNumber", "size"),
        )
    )

    if wholesale_long is not None and not wholesale_long.empty:
        wholesale = wholesale_long.copy()
        if "anchorBrand" not in wholesale.columns:
            wholesale["anchorBrand"] = [
                normalize_anchor_brand(brand, model_name=model)
                for brand, model in zip(
                    wholesale.get("brand", pd.Series("", index=wholesale.index)),
                    wholesale.get("modelName", pd.Series("", index=wholesale.index)),
                    strict=False,
                )
            ]
        if wholesale["anchorBrand"].isin(OFFICIAL_ANCHORS).any():
            wholesale = wholesale.groupby(
                ["month", "anchorBrand", "modelKey"], as_index=False
            )["wholesaleUnits"].sum()
            facts = facts.merge(wholesale, on=["month", "anchorBrand", "modelKey"], how="left")
        else:
            wholesale = wholesale.groupby(
                ["month", "modelKey"], as_index=False
            )["wholesaleUnits"].sum()
            facts = facts.merge(wholesale, on=["month", "modelKey"], how="left")
    else:
        facts["wholesaleUnits"] = pd.NA
    if working_days_long is not None and not working_days_long.empty:
        facts = facts.merge(working_days_long[["month", "workingDays"]], on="month", how="left")
    else:
        facts["workingDays"] = pd.NA

    wholesale_denominator = pd.to_numeric(facts["wholesaleUnits"], errors="coerce").replace(0, pd.NA)
    facts["accessoryUnitsPerVehicle"] = facts["installationQuantity"] / wholesale_denominator
    facts["revenuePerVehicle"] = facts["pioRevenue"] / wholesale_denominator
    facts["pnvw"] = facts["revenuePerVehicle"]
    facts["quantityPerWorkingDay"] = facts["installationQuantity"] / pd.to_numeric(facts["workingDays"], errors="coerce").replace(0, pd.NA)
    facts["lifecycleStatus"] = "Unknown"
    facts["lifecycleStatusCode"] = "unknown"
    if lifecycle_records:
        lifecycle = pd.DataFrame(lifecycle_records)
        if not lifecycle.empty and {"entityKey", "status"}.issubset(lifecycle.columns):
            lifecycle = lifecycle.drop_duplicates("entityKey").set_index("entityKey")
            facts["lifecycleStatus"] = facts["entityKey"].map(lifecycle["status"]).fillna("Unknown")
            if "statusCode" in lifecycle.columns:
                facts["lifecycleStatusCode"] = facts["entityKey"].map(lifecycle["statusCode"]).fillna("unknown")

    facts = facts.sort_values(["month", "brand", "modelName", "partNumber"]).reset_index(drop=True)
    return facts[
        [
            "month", "brand", "anchorBrand", "anchorMappingMethod", "entityKey", "modelName",
            "modelCode", "plc", "partNumber", "partDescription", "lifecycleStatus",
            "lifecycleStatusCode", "installationQuantity", "pioRevenue", "wholesaleUnits",
            "accessoryUnitsPerVehicle", "revenuePerVehicle", "pnvw", "workingDays",
            "quantityPerWorkingDay", "sourceRows",
        ]
    ]


def summarize_monthly_facts(facts: pd.DataFrame) -> dict[str, Any]:
    if facts.empty:
        return {
            "rowCount": 0, "monthCount": 0, "minMonth": None, "maxMonth": None,
            "brandCount": 0, "modelCount": 0, "plcCount": 0, "partCount": 0,
            "anchorCount": 0, "dealerWholesaleExactQuantityCoveragePct": 0.0,
            "totalQuantity": 0.0, "totalRevenue": 0.0,
            "wholesaleCoveragePct": 0.0, "workingDaysCoveragePct": 0.0,
            "grain": "month x brand x model entity x PLC x part number",
        }
    total_quantity = float(facts["installationQuantity"].sum())
    exact_quantity = float(
        facts.loc[
            facts["anchorMappingMethod"].isin(
                {
                    "dealer_wholesale_exact",
                    "dealer_wholesale_volume_resolved",
                    "dealer_wholesale_variant_alias",
                    "source_brand_kus",
                }
            ),
            "installationQuantity",
        ].sum()
    )
    return {
        "rowCount": int(len(facts)),
        "monthCount": int(facts["month"].nunique()),
        "minMonth": str(facts["month"].min()),
        "maxMonth": str(facts["month"].max()),
        "brandCount": int(facts["brand"].nunique()),
        "anchorCount": int(facts["anchorBrand"].nunique()) if "anchorBrand" in facts.columns else 0,
        "modelCount": int(facts["entityKey"].nunique()),
        "plcCount": int(facts["plc"].nunique()) if "plc" in facts.columns else 0,
        "partCount": int(facts["partNumber"].nunique()),
        "totalQuantity": float(facts["installationQuantity"].sum()),
        "totalRevenue": float(facts["pioRevenue"].sum()),
        "dealerWholesaleExactQuantityCoveragePct": round(
            exact_quantity / total_quantity * 100.0 if total_quantity > 0 else 0.0,
            2,
        ),
        "wholesaleCoveragePct": round(float(facts["wholesaleUnits"].notna().mean() * 100), 2),
        "workingDaysCoveragePct": round(float(facts["workingDays"].notna().mean() * 100), 2),
        "grain": "month x brand x model entity x PLC x part number",
    }


def _join_unique(values: pd.Series) -> str:
    cleaned = sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip() and str(value).strip().lower() != "nan"})
    return " / ".join(cleaned)


def _mode_text(values: pd.Series) -> str:
    cleaned = values.dropna().astype(str).str.strip()
    cleaned = cleaned[(cleaned != "") & (cleaned.str.lower() != "nan")]
    return cleaned.mode().iloc[0] if not cleaned.empty else ""


def _empty_wholesale() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "month", "brand", "anchorBrand", "modelName", "modelKey", "modelCode",
            "wholesaleUnits", "channel", "sourceSheet",
        ]
    )


def _is_total_label(value: Any) -> bool:
    return bool(re.search(r"\btotal\b", str(value or ""), flags=re.IGNORECASE))


def _empty_facts() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "month", "brand", "anchorBrand", "anchorMappingMethod", "entityKey",
            "modelName", "modelCode", "plc", "partNumber", "partDescription",
            "lifecycleStatus", "lifecycleStatusCode", "installationQuantity", "pioRevenue",
            "wholesaleUnits", "accessoryUnitsPerVehicle", "revenuePerVehicle", "pnvw",
            "workingDays", "quantityPerWorkingDay", "sourceRows",
        ]
    )


def _assign_sales_anchor(
    source_brand: Any,
    model_name: Any,
    model_key: Any,
    anchor_map: dict[str, dict[str, Any]],
) -> dict[str, str]:
    source = normalize_model_name(source_brand)
    mapped = anchor_map.get(normalize_model_name(model_key))
    if mapped:
        return {
            "anchorBrand": str(mapped["anchorBrand"]),
            "method": str(mapped["method"]),
        }
    if source == "K":
        return {"anchorBrand": "KUS", "method": "source_brand_kus"}
    model = normalize_model_name(model_name)
    if model.startswith(GENESIS_MODEL_PREFIXES):
        return {"anchorBrand": "GMA", "method": "genesis_name_fallback"}
    return {"anchorBrand": "HMA", "method": "hma_default_fallback"}


def _model_anchor_aliases(value: Any) -> set[str]:
    model = normalize_model_name(value)
    if not model:
        return set()
    aliases = {model}
    normalized = re.sub(r"\bPLUG[\s-]*IN\s+HYBRID\b", "PHEV", model)
    normalized = re.sub(r"\bHYBRID\b", "HEV", normalized)
    aliases.add(normalized)
    base = re.sub(r"\s+(?:EV|HEV|PHEV)$", "", normalized).strip()
    if base:
        aliases.add(base)
    return aliases
