from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pio_platform.backtest_harness import (  # noqa: E402
    CONTRACT_VERSION,
    BacktestContract,
    run_portfolio_backtest,
    run_series_backtest,
    self_test,
    summarize_predictions,
    predictions_to_frame,
)
from pio_platform.data_loader import load_dataset  # noqa: E402
from pio_platform.fact_table import (  # noqa: E402
    build_monthly_fact_table,
    build_wholesale_long,
)


DEFAULT_SOURCE = Path(r"C:\Users\Lenovo\Desktop\PIO\CapStone_Sales_Data_0722+PLC.xlsx")
PIO_SHEET = "PIO_Sales_Data"
WHOLESALE_SHEETS = (
    "Vehicle_Wholesale_Data",
    "2023 Vehicle Wholesale",
    "2024 Vehicle Wholesale",
)
WORKING_DAYS_SHEET = "Working_Days"
OFFICIAL_ANCHORS = ("HMA", "GMA", "KUS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run governed Revenue, Quantity, and Wholesale backtests on one common contract."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0

    source = args.source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    source_hash = sha256_file(source)
    governed = load_governed_monthly(source, source_hash, use_cache=not args.no_cache)
    contract = BacktestContract()
    working_days = governed["workingDays"]

    revenue = governed["pioRevenue"]
    quantity = governed["pioQuantity"]
    wholesale = governed["wholesale"]

    results: dict[str, Any] = {
        "contractVersion": CONTRACT_VERSION,
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "actualThrough": governed["actualThrough"],
            "completedTrainingThrough": governed["completedTrainingThrough"],
        },
        "warnings": [
            "Reference Revenue uses the repository ets_additive as an implementation proxy; exact reference ETS fitting code is unavailable.",
            "Results on the 7/22 source are not exact reproductions of the reference workbook generated from the 7/15 source snapshot.",
            "July partial actual is excluded from pre-month backtests; cutoff-specific nowcast requires daily historical cutoff rows.",
        ],
        "runs": {},
    }

    results["runs"]["referenceRevenueProxy"] = run_portfolio_backtest(
        revenue,
        model_id="reference_revenue_portfolio_v2_proxy",
        target="pio_revenue",
        entity_models={
            "HMA": "ets_additive",
            "GMA": "naive_last",
            "KUS": "working_day_adjusted_seasonal",
        },
        contract=contract,
        working_days=working_days,
        source_hash=source_hash,
    )
    results["runs"]["currentAutoRevenue"] = run_portfolio_backtest(
        revenue,
        model_id="current_auto_brand_anchor",
        target="pio_revenue",
        entity_models={anchor: "auto" for anchor in OFFICIAL_ANCHORS},
        contract=contract,
        working_days=working_days,
        source_hash=source_hash,
    )
    results["runs"]["legacyRevenueFrozen"] = run_portfolio_backtest(
        revenue,
        model_id="legacy_revenue_frozen_brand_models",
        target="pio_revenue",
        entity_models={
            "HMA": "damped_trend",
            "GMA": "log_linear_trend",
            "KUS": "seasonal_mean",
        },
        contract=contract,
        working_days=working_days,
        source_hash=source_hash,
    )
    results["runs"]["currentAutoQuantityByBrand"] = run_portfolio_backtest(
        quantity,
        model_id="current_auto_quantity_brand_anchors",
        target="pio_quantity",
        entity_models={anchor: "auto" for anchor in OFFICIAL_ANCHORS},
        contract=contract,
        working_days=working_days,
        source_hash=source_hash,
    )

    quantity_total = (
        quantity.groupby("month", as_index=False)["value"].sum().set_index("month")["value"]
    )
    quantity_ets_rows = run_series_backtest(
        quantity_total,
        model_id="reference_quantity_total_ets_v2_proxy",
        target="pio_quantity",
        level="official_total",
        entity="TOTAL",
        contract=contract,
        source_hash=source_hash,
    )
    quantity_ets_frame = predictions_to_frame(quantity_ets_rows)
    results["runs"]["referenceQuantityTotalEtsProxy"] = {
        "contract": contract.__dict__,
        "modelId": "reference_quantity_total_ets_v2_proxy",
        "target": "pio_quantity",
        "officialTotalMetrics": summarize_predictions(quantity_ets_frame),
        "predictions": quantity_ets_frame.to_dict(orient="records"),
    }

    results["runs"]["currentAutoWholesale"] = run_portfolio_backtest(
        wholesale,
        model_id="current_wholesale_auto",
        target="dealer_non_fleet_wholesale_quantity",
        entity_models={anchor: "auto" for anchor in OFFICIAL_ANCHORS},
        contract=contract,
        working_days=working_days,
        source_hash=source_hash,
    )

    output = args.output or (
        PROJECT_ROOT
        / "outputs"
        / "backtests"
        / f"unified_backtest_{source_hash[:12]}_{CONTRACT_VERSION}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, default=_json_default), encoding="utf-8")
    print(str(output))
    return 0


def load_governed_monthly(
    source: Path,
    source_hash: str,
    *,
    use_cache: bool,
) -> dict[str, Any]:
    cache_dir = PROJECT_ROOT / "outputs" / "backtest_cache"
    cache_path = cache_dir / f"governed_monthly_{source_hash}_{CONTRACT_VERSION}.pkl"
    if use_cache and cache_path.exists():
        with cache_path.open("rb") as handle:
            cached = pickle.load(handle)
        if (
            cached.get("sourceHash") == source_hash
            and cached.get("contractVersion") == CONTRACT_VERSION
        ):
            payload = cached["payload"]
            if not payload.get("workingDays"):
                payload = dict(payload)
                payload["workingDays"] = load_working_days_only(source)
                if not payload["workingDays"]:
                    raise RuntimeError(
                        "Governed cache has no Working Days and the Working_Days sheet "
                        "could not be parsed."
                    )
                cache_dir.mkdir(parents=True, exist_ok=True)
                with cache_path.open("wb") as handle:
                    pickle.dump(
                        {
                            "sourceHash": source_hash,
                            "contractVersion": CONTRACT_VERSION,
                            "payload": payload,
                        },
                        handle,
                        protocol=pickle.HIGHEST_PROTOCOL,
                    )
            return payload

    file_bytes = source.read_bytes()
    pio_bundle = load_dataset(file_bytes, PIO_SHEET)
    wholesale_parts: list[pd.DataFrame] = []
    for sheet_name in WHOLESALE_SHEETS:
        bundle = load_dataset(file_bytes, sheet_name)
        part = build_wholesale_long(
            bundle.dataframe,
            sheet_name,
            latest_sales_year=2026,
        )
        if not part.empty:
            wholesale_parts.append(part)
    wholesale_long = (
        pd.concat(wholesale_parts, ignore_index=True)
        if wholesale_parts
        else pd.DataFrame(
            columns=["month", "anchorBrand", "modelKey", "modelName", "wholesaleUnits"]
        )
    )
    if not wholesale_long.empty:
        wholesale_long = (
            wholesale_long.groupby(["month", "anchorBrand", "modelKey"], as_index=False)
            .agg(
                modelName=("modelName", "first"),
                wholesaleUnits=("wholesaleUnits", "sum"),
            )
        )

    roles = pio_bundle.roles
    date_col = roles.get("date") or "Deliminated Date"
    date_series = pio_bundle.date_candidates.get(date_col)
    if date_series is None:
        date_series = pd.to_datetime(pio_bundle.dataframe[date_col], errors="coerce")
    max_date = pd.Timestamp(date_series.max())
    partial_period = max_date.to_period("M")
    is_partial = max_date.normalize() < (max_date + pd.offsets.MonthEnd(0)).normalize()

    facts = build_monthly_fact_table(
        pio_bundle.dataframe,
        date_series,
        brand_col=roles.get("brand") or "PIS_CMP_KND",
        model_col=roles.get("model") or "Model",
        model_code_col=roles.get("model_code") or "PIS_SERI",
        part_number_col=roles.get("part_number") or "PIS_PNO",
        part_description_col=roles.get("part_description") or "Part Description",
        qty_col=roles.get("quantity") or "SumOfPIS_INST_QT",
        revenue_col=roles.get("revenue") or "SumOfPIS_CRP_CFM_PRI",
        plc_col=roles.get("plc") or "PLC",
        wholesale_long=wholesale_long,
        start_year=2023,
        end_year=2026,
    )
    if facts.empty:
        raise RuntimeError("Governed monthly fact table is empty.")
    facts["period"] = pd.PeriodIndex(facts["month"], freq="M")
    completed = facts[facts["period"] != partial_period].copy() if is_partial else facts.copy()

    revenue = (
        completed.groupby(["month", "anchorBrand"], as_index=False)["pioRevenue"]
        .sum()
        .rename(columns={"anchorBrand": "entity", "pioRevenue": "value"})
    )
    quantity = (
        completed.groupby(["month", "anchorBrand"], as_index=False)["installationQuantity"]
        .sum()
        .rename(columns={"anchorBrand": "entity", "installationQuantity": "value"})
    )
    revenue = revenue[revenue["entity"].isin(OFFICIAL_ANCHORS)].copy()
    quantity = quantity[quantity["entity"].isin(OFFICIAL_ANCHORS)].copy()

    wholesale = (
        wholesale_long.groupby(["month", "anchorBrand"], as_index=False)["wholesaleUnits"]
        .sum()
        .rename(columns={"anchorBrand": "entity", "wholesaleUnits": "value"})
    )
    wholesale = wholesale[wholesale["entity"].isin(OFFICIAL_ANCHORS)].copy()
    wholesale = wholesale[pd.PeriodIndex(wholesale["month"], freq="M") < partial_period].copy()

    working_bundle = load_dataset(file_bytes, WORKING_DAYS_SHEET)
    working_days = working_days_map(working_bundle.dataframe)
    payload = {
        "pioRevenue": revenue,
        "pioQuantity": quantity,
        "wholesale": wholesale,
        "workingDays": working_days,
        "actualThrough": max_date.strftime("%Y-%m-%d"),
        "completedTrainingThrough": str(completed["period"].max()),
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as handle:
        pickle.dump(
            {
                "sourceHash": source_hash,
                "contractVersion": CONTRACT_VERSION,
                "payload": payload,
            },
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    return payload


def working_days_map(frame: pd.DataFrame) -> dict[str, float]:
    columns = {str(column).strip().lower(): column for column in frame.columns}
    year_col = next((value for key, value in columns.items() if key in {"yyyy", "year"}), None)
    month_col = next((value for key, value in columns.items() if key in {"month", "period", "yyyymm"}), None)
    days_col = next((value for key, value in columns.items() if "working day" in key), None)
    if month_col is None or days_col is None:
        return {}

    if year_col is not None:
        years = pd.to_numeric(frame[year_col], errors="coerce").astype("Int64")
        months = frame[month_col].map(month_number)
        keys = [
            f"{int(year):04d}-{int(month):02d}" if pd.notna(year) and month else ""
            for year, month in zip(years, months, strict=False)
        ]
    else:
        keys = pd.to_datetime(frame[month_col], errors="coerce").dt.to_period("M").astype(str)
    days = pd.to_numeric(frame[days_col], errors="coerce").clip(lower=0)
    result = pd.DataFrame({"month": keys, "days": days})
    result = result[(result["month"] != "") & result["days"].notna()]
    return result.groupby("month")["days"].max().astype(float).to_dict()


def month_number(value: Any) -> int | None:
    if pd.isna(value):
        return None
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(numeric):
        integer = int(numeric)
        if 1 <= integer <= 12:
            return integer
        possible_month = integer % 100
        if 100001 <= integer <= 999912 and 1 <= possible_month <= 12:
            return possible_month
    token = str(value).strip()[:3].lower()
    names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    return names.get(token)


def load_working_days_only(source: Path) -> dict[str, float]:
    """Read only the small calendar sheet when an otherwise valid cache lacks it."""

    frame = pd.read_excel(
        source,
        sheet_name=WORKING_DAYS_SHEET,
        engine="openpyxl",
    )
    return working_days_map(frame)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, pd.Period):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
