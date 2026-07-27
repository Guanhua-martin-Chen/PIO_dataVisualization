from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pio_platform.data_loader import list_workbook_sheets, load_dataset
from pio_platform.fact_table import (
    build_monthly_fact_table,
    build_wholesale_long,
    build_working_days_long,
    summarize_monthly_facts,
)
from pio_platform.forecast_center import build_forecast_center
from pio_platform.model_entities import build_model_lifecycle


def _sales_columns(bundle: Any) -> dict[str, str | None]:
    pick = lambda preferred, role: preferred if preferred in bundle.dataframe.columns else bundle.roles.get(role)
    return {
        "date": pick("PIS_MST_IVC_DT", "date"),
        "brand": pick("PIS_CMP_KND", "brand"),
        "model": pick("Model", "model"),
        "model_code": pick("PIS_SERI", "model_code"),
        "part_number": pick("PIS_PNO", "part_number"),
        "part_description": pick("Part Description", "part_description"),
        "plc": pick("PLC", "plc"),
        "quantity": pick("SumOfPIS_INST_QT", "installation_quantity"),
        "revenue": pick("SumOfPIS_CRP_CFM_PRI", "revenue"),
    }


def _records_by_anchor(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "anchor": record.get("brand"),
            "selectedModel": record.get("selectedModel"),
            "wape": record.get("wape"),
            "accuracyPct": record.get("accuracyPct"),
            "forecast": record.get("forecast"),
        }
        for record in payload.get("brandRecords", [])
    ]


def validate(workbook_path: Path, horizon: int) -> dict[str, Any]:
    file_bytes = workbook_path.read_bytes()
    sheet_names = list_workbook_sheets(file_bytes)
    sales_sheet = "PIO_Sales_Data"
    if sales_sheet not in sheet_names:
        raise ValueError("PIO_Sales_Data was not found.")
    sales = load_dataset(file_bytes, sales_sheet, header_mode="Auto detect")
    columns = _sales_columns(sales)
    date_col = columns["date"]
    if not date_col or date_col not in sales.date_candidates:
        raise ValueError("A reliable PIO date field was not found.")
    dates = sales.date_candidates[date_col]
    latest_date = pd.Timestamp(dates.max())
    latest_year = int(latest_date.year)

    wholesale_frames = []
    for sheet_name in sheet_names:
        if sheet_name == sales_sheet or "wholesale" not in sheet_name.lower():
            continue
        bundle = load_dataset(file_bytes, sheet_name, header_mode="Auto detect")
        frame = build_wholesale_long(bundle.dataframe, sheet_name, latest_sales_year=latest_year)
        if not frame.empty:
            wholesale_frames.append(frame)
    if wholesale_frames:
        wholesale = pd.concat(wholesale_frames, ignore_index=True)
        wholesale = (
            wholesale.groupby(["month", "anchorBrand", "modelKey"], as_index=False)
            .agg(
                brand=("brand", "first"),
                modelName=("modelName", "first"),
                modelCode=("modelCode", "first"),
                wholesaleUnits=("wholesaleUnits", "sum"),
                channel=("channel", "first"),
                sourceSheet=("sourceSheet", "first"),
            )
        )
    else:
        wholesale = pd.DataFrame()

    working_days = pd.DataFrame()
    for sheet_name in sheet_names:
        if "working_day" in sheet_name.lower().replace(" ", "_"):
            bundle = load_dataset(file_bytes, sheet_name, header_mode="Auto detect")
            working_days = build_working_days_long(bundle.dataframe)
            break

    lifecycle = build_model_lifecycle(
        sales.dataframe,
        dates,
        model_col=columns["model"],
        qty_col=columns["quantity"],
        brand_col=columns["brand"],
        model_code_col=columns["model_code"],
        cutoff_year=2024,
    )
    facts = build_monthly_fact_table(
        sales.dataframe,
        dates,
        brand_col=columns["brand"],
        model_col=columns["model"],
        model_code_col=columns["model_code"],
        part_number_col=columns["part_number"],
        part_description_col=columns["part_description"],
        plc_col=columns["plc"],
        qty_col=columns["quantity"],
        revenue_col=columns["revenue"],
        wholesale_long=wholesale,
        working_days_long=working_days,
        lifecycle_records=lifecycle["records"],
        start_year=2023,
        end_year=2026,
    )
    latest_month = latest_date.strftime("%Y-%m")
    actual_by_anchor = (
        facts[facts["month"] == latest_month]
        .groupby("anchorBrand", as_index=False)
        .agg(
            pioQuantity=("installationQuantity", "sum"),
            pioRevenue=("pioRevenue", "sum"),
        )
        .to_dict("records")
    )
    wholesale_by_anchor = (
        wholesale[wholesale["month"] == latest_month]
        .groupby("anchorBrand", as_index=False)
        .agg(dealerWholesaleUnits=("wholesaleUnits", "sum"))
        .to_dict("records")
        if not wholesale.empty
        else []
    )

    forecasts: dict[str, Any] = {}
    for metric in ("revenue", "quantity", "wholesale_quantity"):
        payload = build_forecast_center(
            facts,
            working_days,
            wholesale,
            metric=metric,
            level="brand",
            horizon=horizon,
            min_monthly_volume=5.0,
            latest_sales_month_is_complete=False,
            latest_sales_date=latest_date,
            include_all_records=True,
        )
        forecasts[metric] = {
            "summary": {
                "accuracyPct": payload["summary"].get("accuracyPct"),
                "weightedWape": payload["summary"].get("weightedWape"),
                "forecastMonths": payload["summary"].get("forecastMonths"),
                "reconciliation": payload["summary"].get("reconciliation"),
                "allocationRouting": payload["summary"].get("allocationRouting"),
                "anchorPolicy": payload["summary"].get("anchorPolicy"),
                "businessValidation": payload["summary"].get("businessValidation"),
            },
            "anchors": _records_by_anchor(payload),
        }

    return {
        "workbook": str(workbook_path),
        "sheets": sheet_names,
        "cutoff": latest_date.date().isoformat(),
        "factSummary": summarize_monthly_facts(facts),
        "lifecycleSummary": {
            key: value
            for key, value in lifecycle.items()
            if key != "records"
        },
        "latestMonthPioActual": actual_by_anchor,
        "latestMonthDealerWholesale": wholesale_by_anchor,
        "forecasts": forecasts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate HMA/GMA/KUS anchor and allocation policy.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--horizon", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(validate(args.workbook, args.horizon), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
