from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from pio_platform.hierarchical_forecasting import build_hierarchical_forecast
from pio_platform.model_entities import build_model_lifecycle


def evaluate(source: Path) -> dict:
    workbook_bytes = source.read_bytes()
    sheet_names = list_workbook_sheets(workbook_bytes)
    sales_sheet = "PIO_Sales_Data" if "PIO_Sales_Data" in sheet_names else sheet_names[0]
    sales_bundle = load_dataset(workbook_bytes, sales_sheet)
    roles = sales_bundle.roles
    date_col = roles.get("date")
    if not date_col or date_col not in sales_bundle.date_candidates:
        raise RuntimeError("A reliable sales date field is required.")
    dates = sales_bundle.date_candidates[date_col]
    latest_year = int(dates.dropna().max().year)

    wholesale_frames = []
    working_days = pd.DataFrame(columns=["month", "workingDays"])
    for sheet_name in sheet_names:
        if sheet_name == sales_sheet:
            continue
        bundle = load_dataset(workbook_bytes, sheet_name)
        if "wholesale" in sheet_name.lower():
            frame = build_wholesale_long(bundle.dataframe, sheet_name, latest_sales_year=latest_year)
            if not frame.empty:
                wholesale_frames.append(frame)
        if "working_day" in sheet_name.lower().replace(" ", "_"):
            working_days = build_working_days_long(bundle.dataframe)
    if wholesale_frames:
        wholesale = pd.concat(wholesale_frames, ignore_index=True)
        wholesale = wholesale.groupby(["month", "modelKey"], as_index=False)["wholesaleUnits"].sum()
    else:
        wholesale = pd.DataFrame(columns=["month", "modelKey", "wholesaleUnits"])

    df = sales_bundle.dataframe
    lifecycle = build_model_lifecycle(
        df,
        dates,
        model_col=roles.get("model"),
        qty_col=roles.get("installation_quantity"),
        brand_col=roles.get("brand"),
        model_code_col="PIS_SERI" if "PIS_SERI" in df.columns else None,
        cutoff_year=2024,
    )
    facts = build_monthly_fact_table(
        df,
        dates,
        brand_col=roles.get("brand"),
        model_col=roles.get("model"),
        model_code_col="PIS_SERI" if "PIS_SERI" in df.columns else None,
        part_number_col=roles.get("part_number"),
        part_description_col=roles.get("part_description"),
        qty_col=roles.get("installation_quantity"),
        revenue_col=roles.get("revenue"),
        wholesale_long=wholesale,
        working_days_long=working_days,
        lifecycle_records=lifecycle["records"],
        start_year=2023,
        end_year=2026,
    )
    forecasts = {
        level: build_hierarchical_forecast(
            facts,
            working_days,
            level=level,
            horizon=6,
            use_working_days=True,
            use_seasonality=True,
            tariff_impact_pct=0,
            min_monthly_volume=5,
            limit=100,
            latest_month_is_complete=bool(
                dates.dropna().max().normalize()
                >= (dates.dropna().max() + pd.offsets.MonthEnd(0)).normalize()
            ),
        )
        for level in ("brand", "model", "model_accessory")
    }
    return {
        "source": str(source),
        "dataQuality": {
            "salesRows": int(len(df)),
            "dateMin": dates.dropna().min().date().isoformat(),
            "dateMax": dates.dropna().max().date().isoformat(),
            "contains1970": bool((dates.dropna().dt.year == 1970).any()),
        },
        "facts": summarize_monthly_facts(facts),
        "lifecycle": lifecycle,
        "forecast": {level: payload["summary"] for level, payload in forecasts.items()},
        "topForecasts": {level: payload["records"][:10] for level, payload in forecasts.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the 2023–2026 hierarchical PIO forecast pipeline.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "forecast": result["forecast"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
