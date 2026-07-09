"""Server-side pivot-table aggregation.

Turns the flat PIO sales table into a cross-tab the way a planner would build
one in Excel: drag dimensions onto rows and columns, pick a measure, and read
the aggregated grid. All work happens server-side so the browser never needs
the full dataset (consistent with the rest of the platform).

Two input shapes are supported:

1. Long/tidy sheets (e.g. PIO_Sales_Data) — one row per transaction, with
   detected roles for date / brand / model / part / quantity / revenue.
2. Wide month-matrix sheets (e.g. Vehicle_Wholesale_Data) — month columns
   (Jan…Dec, plus a second year as "Jan (2)"…), interleaved Wholesale / Fleet
   blocks and subtotal rows. These are melted into a tidy frame on the fly so
   they can be pivoted too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

ROW_KEY = "__pio_rowkey"
COL_KEY = "__pio_colkey"
VAL_KEY = "__pio_value"

MAX_ROW_KEYS = 2000
MAX_COL_KEYS = 200

AGG_FUNCS = {"sum", "avg", "count"}
PANDAS_AGG = {"sum": "sum", "avg": "mean", "count": "count"}

MONTH_NUMBERS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
MONTH_COL_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s*\((\d+)\))?$"
)


@dataclass
class Dimension:
    key: str
    label: str


@dataclass
class Measure:
    key: str
    label: str


# ── shared helpers ─────────────────────────────────────────────────────────────
def _month_label(parsed: pd.Series) -> pd.Series:
    return parsed.dt.to_period("M").astype(str).where(parsed.notna(), "")


def _year_label(parsed: pd.Series) -> pd.Series:
    return parsed.dt.year.astype("Int64").astype(str).where(parsed.notna(), "")


def _empty_payload(
    row_fields: list[str],
    col_fields: list[str],
    measure: str,
    agg: str,
    dims: list[Dimension],
    measures: list[Measure],
) -> dict[str, Any]:
    return {
        "rowFields": row_fields,
        "colFields": col_fields,
        "measure": measure,
        "agg": agg,
        "availableDimensions": [{"key": d.key, "label": d.label} for d in dims],
        "availableMeasures": [{"key": m.key, "label": m.label} for m in measures],
        "rowKeys": [],
        "colKeys": [],
        "cells": {},
        "rowTotals": {},
        "colTotals": {},
        "grandTotal": 0.0,
        "rowCount": 0,
        "colCount": 0,
        "truncated": False,
        "measureUnit": "currency" if measure == "revenue" else "number",
    }


def _composite_key(
    dim_series: dict[str, pd.Series], fields: list[str], index: pd.Index
) -> pd.Series:
    if not fields:
        return pd.Series("Total", index=index)
    parts = [dim_series[f].astype(str).replace("", "—") for f in fields]
    combined = parts[0]
    for extra in parts[1:]:
        combined = combined.str.cat(extra, sep=" / ")
    return combined


def _assemble(
    index: pd.Index,
    dim_series: dict[str, pd.Series],
    measure_values: pd.Series,
    row_fields: list[str],
    col_fields: list[str],
    measure: str,
    agg: str,
    dims: list[Dimension],
    measures: list[Measure],
    measure_unit: str,
) -> dict[str, Any]:
    payload = _empty_payload(row_fields, col_fields, measure, agg, dims, measures)
    payload["measureUnit"] = measure_unit
    if len(index) == 0 or (not row_fields and not col_fields):
        return payload

    work = pd.DataFrame(
        {
            ROW_KEY: _composite_key(dim_series, row_fields, index).values,
            COL_KEY: _composite_key(dim_series, col_fields, index).values,
            VAL_KEY: pd.to_numeric(measure_values, errors="coerce").fillna(0.0).values,
        }
    )

    pandas_agg = PANDAS_AGG[agg]
    grid = work.groupby([ROW_KEY, COL_KEY])[VAL_KEY].agg(pandas_agg)
    row_totals = work.groupby(ROW_KEY)[VAL_KEY].agg(pandas_agg)
    col_totals = work.groupby(COL_KEY)[VAL_KEY].agg(pandas_agg)
    grand_total = float(work[VAL_KEY].agg(pandas_agg))

    row_keys = row_totals.sort_values(ascending=False).index.tolist()
    col_keys = col_totals.sort_values(ascending=False).index.tolist()

    truncated = False
    if len(row_keys) > MAX_ROW_KEYS:
        row_keys = row_keys[:MAX_ROW_KEYS]
        truncated = True
    if len(col_keys) > MAX_COL_KEYS:
        col_keys = col_keys[:MAX_COL_KEYS]
        truncated = True

    row_set, col_set = set(row_keys), set(col_keys)
    cells: dict[str, dict[str, float]] = {}
    for (rk, ck), value in grid.items():
        if rk not in row_set or ck not in col_set:
            continue
        cells.setdefault(str(rk), {})[str(ck)] = round(float(value), 2)

    payload.update(
        {
            "rowKeys": [str(k) for k in row_keys],
            "colKeys": [str(k) for k in col_keys],
            "cells": cells,
            "rowTotals": {str(k): round(float(row_totals[k]), 2) for k in row_keys},
            "colTotals": {str(k): round(float(col_totals[k]), 2) for k in col_keys},
            "grandTotal": round(grand_total, 2),
            "rowCount": len(row_keys),
            "colCount": len(col_keys),
            "truncated": truncated,
        }
    )
    return payload


# ── long / tidy sheets ─────────────────────────────────────────────────────────
def available_dimensions(
    roles: dict[str, str], date_candidates: dict[str, pd.Series]
) -> list[Dimension]:
    dims: list[Dimension] = []
    if roles.get("brand"):
        dims.append(Dimension("brand", "Brand"))
    if roles.get("model"):
        dims.append(Dimension("model", "Model"))
    if roles.get("model_year"):
        dims.append(Dimension("model_year", "Model year"))
    if roles.get("part_description") or roles.get("part_number"):
        dims.append(Dimension("part", "Part"))
    date_col = roles.get("date")
    if date_col and date_col in date_candidates:
        dims.append(Dimension("month", "Month"))
        dims.append(Dimension("year", "Year"))
    return dims


def available_measures(roles: dict[str, str]) -> list[Measure]:
    measures: list[Measure] = []
    if roles.get("installation_quantity"):
        measures.append(Measure("quantity", "Installation quantity"))
    if roles.get("revenue"):
        measures.append(Measure("revenue", "Sales revenue"))
    measures.append(Measure("records", "Record count"))
    return measures


def _long_dimension_series(
    df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    key: str,
) -> pd.Series | None:
    if key == "brand" and roles.get("brand") in df.columns:
        return df[roles["brand"]].fillna("").astype(str)
    if key == "model" and roles.get("model") in df.columns:
        return df[roles["model"]].fillna("").astype(str)
    if key == "model_year":
        col = roles.get("model_year")
        if col and col in date_candidates:
            return _year_label(date_candidates[col].loc[df.index])
        if col and col in df.columns:
            return df[col].fillna("").astype(str)
        return None
    if key == "part":
        col = roles.get("part_description") or roles.get("part_number")
        if col and col in df.columns:
            return df[col].fillna("").astype(str)
        return None
    if key in ("month", "year"):
        date_col = roles.get("date")
        if not date_col or date_col not in date_candidates:
            return None
        parsed = date_candidates[date_col].loc[df.index]
        return _month_label(parsed) if key == "month" else _year_label(parsed)
    return None


def _long_measure_values(df: pd.DataFrame, roles: dict[str, str], measure: str) -> pd.Series:
    if measure == "revenue" and roles.get("revenue") in df.columns:
        return pd.to_numeric(df[roles["revenue"]], errors="coerce").fillna(0.0)
    if measure == "quantity" and roles.get("installation_quantity") in df.columns:
        return pd.to_numeric(df[roles["installation_quantity"]], errors="coerce").fillna(0.0)
    return pd.Series(1.0, index=df.index)


# ── wide month-matrix sheets (wholesale / fleet) ───────────────────────────────
def month_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if MONTH_COL_RE.match(str(c).strip())]


def _named_column(df: pd.DataFrame, name: str) -> str | None:
    return next((c for c in df.columns if str(c).strip().lower() == name), None)


def is_wide_month_matrix(df: pd.DataFrame, roles: dict[str, str]) -> bool:
    return not roles.get("date") and bool(month_columns(df))


def wide_brand_series(df: pd.DataFrame) -> pd.Series:
    brand_col = _named_column(df, "brand")
    if not brand_col:
        return pd.Series("", index=df.index, dtype="object")

    raw_brand = df[brand_col].astype(str)
    is_label = (
        raw_brand.str.contains("total", case=False, na=False)
        | raw_brand.str.strip().str.startswith("▣")
        | (raw_brand.str.strip() == "Brand")
        | raw_brand.isin(["", "nan", "NaN", "None"])
    )
    return df[brand_col].where(~is_label).ffill().fillna("").astype(str)


def prepare_wide_long(df: pd.DataFrame, start_year: int) -> pd.DataFrame:
    """Melt a wide month-matrix sheet into a tidy frame.

    Splits Wholesale / Fleet blocks into a ``channel`` column, forward-fills the
    sparse brand column, drops subtotal / marker rows, and unpivots the month
    columns (Jan…Dec, Jan (2)… for the next year) into ``month`` + ``units``.
    """
    cols = month_columns(df)
    if not cols:
        return pd.DataFrame(columns=["brand", "model", "channel", "month", "units"])

    model_col = _named_column(df, "model")
    if not model_col:
        return pd.DataFrame(columns=["brand", "model", "channel", "month", "units"])

    work = df.reset_index(drop=True)
    brand = wide_brand_series(work)
    brand_col = _named_column(work, "brand")
    marker_brand = (
        work[brand_col].astype(str)
        if brand_col
        else pd.Series("", index=work.index)
    )

    # Channel: everything from the first "Fleet" marker onward is Fleet.
    channel = pd.Series("Wholesale", index=work.index)
    fleet_hits = work.index[marker_brand.str.contains("fleet", case=False, na=False)]
    if len(fleet_hits) > 0:
        channel.iloc[int(fleet_hits[0]):] = "Fleet"

    model = work[model_col]

    keep = model.notna() & (model.astype(str).str.strip() != "")

    frames: list[pd.DataFrame] = []
    for col in cols:
        match = MONTH_COL_RE.match(str(col).strip())
        if not match:
            continue
        group_index = int(match.group(2) or "1")
        year = start_year + group_index - 1
        month_ts = pd.Timestamp(year=year, month=MONTH_NUMBERS[match.group(1)], day=1)
        sub = pd.DataFrame(
            {
                "brand": brand,
                "model": model.astype(str).str.strip(),
                "channel": channel,
                "units": pd.to_numeric(work[col], errors="coerce"),
            }
        )[keep]
        sub["month"] = month_ts
        sub = sub[sub["units"].notna()]
        frames.append(sub)

    if not frames:
        return pd.DataFrame(columns=["brand", "model", "channel", "month", "units"])
    long_df = pd.concat(frames, ignore_index=True)
    long_df = long_df[long_df["model"] != ""]
    long_df["brand"] = long_df["brand"].fillna("").astype(str)
    return long_df


def _wide_dimensions(long_df: pd.DataFrame) -> list[Dimension]:
    dims = [Dimension("brand", "Brand"), Dimension("model", "Model")]
    if long_df["channel"].nunique() > 1:
        dims.append(Dimension("channel", "Channel"))
    dims.append(Dimension("month", "Month"))
    dims.append(Dimension("year", "Year"))
    return dims


def _wide_dimension_series(long_df: pd.DataFrame, key: str) -> pd.Series | None:
    if key == "brand":
        return long_df["brand"].fillna("").astype(str)
    if key == "model":
        return long_df["model"].fillna("").astype(str)
    if key == "channel":
        return long_df["channel"].fillna("").astype(str)
    if key == "month":
        return _month_label(long_df["month"])
    if key == "year":
        return _year_label(long_df["month"])
    return None


# ── public entry point ─────────────────────────────────────────────────────────
def build_pivot(
    filtered_df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    row_fields: list[str],
    col_fields: list[str],
    measure: str,
    agg: str,
    wide_start_year: int | None = None,
) -> dict[str, Any]:
    is_wide = is_wide_month_matrix(filtered_df, roles)

    if is_wide:
        long_df = prepare_wide_long(filtered_df, start_year=wide_start_year or 2025)
        dims = _wide_dimensions(long_df)
        measures = [Measure("wholesale", "Wholesale units"), Measure("records", "Record count")]
        index = long_df.index
        resolver: Callable[[str], pd.Series | None] = lambda key: _wide_dimension_series(long_df, key)

        def measure_values(name: str) -> pd.Series:
            if name == "wholesale":
                return pd.to_numeric(long_df["units"], errors="coerce").fillna(0.0)
            return pd.Series(1.0, index=long_df.index)
    else:
        dims = available_dimensions(roles, date_candidates)
        measures = available_measures(roles)
        index = filtered_df.index
        resolver = lambda key: _long_dimension_series(filtered_df, roles, date_candidates, key)

        def measure_values(name: str) -> pd.Series:
            return _long_measure_values(filtered_df, roles, name)

    valid_dim_keys = {d.key for d in dims}
    valid_measure_keys = {m.key for m in measures}

    row_fields = [f for f in row_fields if f in valid_dim_keys]
    col_fields = [f for f in col_fields if f in valid_dim_keys]
    if measure not in valid_measure_keys:
        measure = measures[0].key if measures else "records"
    if agg not in AGG_FUNCS:
        agg = "sum"
    if measure == "records":
        agg = "count"

    measure_unit = "currency" if measure == "revenue" else "number"

    if len(index) == 0 or (not row_fields and not col_fields):
        return _empty_payload(row_fields, col_fields, measure, agg, dims, measures)

    needed = set(row_fields) | set(col_fields)
    dim_series: dict[str, pd.Series] = {}
    for key in needed:
        series = resolver(key)
        if series is None:
            return _empty_payload(row_fields, col_fields, measure, agg, dims, measures)
        dim_series[key] = series

    return _assemble(
        index=index,
        dim_series=dim_series,
        measure_values=measure_values(measure),
        row_fields=row_fields,
        col_fields=col_fields,
        measure=measure,
        agg=agg,
        dims=dims,
        measures=measures,
        measure_unit=measure_unit,
    )
