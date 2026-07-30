from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO, StringIO
import json
import threading
import time
from typing import Any

import pandas as pd

from pio_platform.forecast_center import (
    build_forecast_center,
    build_part_planning_records,
)
from pio_platform.sop_workbook import build_sop_workbook_bytes


OUTPUT_RUN_CONTRACT_VERSION = "pio-output-run-v1"
OUTPUT_RUN_TTL_SECONDS = 30 * 60
OUTPUT_RUN_CACHE_LIMIT = 8
OUTPUT_RUN_CACHE_BYTES_LIMIT = 256 * 1024 * 1024


class OutputDependencyUnavailable(RuntimeError):
    """Raised when an explicitly governed export dependency is unavailable."""


@dataclass(frozen=True)
class _CachedOutputRun:
    expires_at: float
    size_bytes: int
    value: dict[str, Any]


@dataclass
class _InFlightOutputRun:
    event: threading.Event
    value: dict[str, Any] | None = None
    error: BaseException | None = None


_OUTPUT_RUNS: OrderedDict[str, _CachedOutputRun] = OrderedDict()
_OUTPUT_RUN_INFLIGHT: dict[str, _InFlightOutputRun] = {}
_OUTPUT_RUN_LOCK = threading.RLock()
_OUTPUT_RUN_CACHE_BYTES = 0


def clear_output_run_cache() -> None:
    global _OUTPUT_RUN_CACHE_BYTES
    with _OUTPUT_RUN_LOCK:
        _OUTPUT_RUNS.clear()
        _OUTPUT_RUN_CACHE_BYTES = 0


def output_run_cache_stats() -> dict[str, int]:
    with _OUTPUT_RUN_LOCK:
        _evict_expired_runs()
        return {
            "count": len(_OUTPUT_RUNS),
            "bytes": _OUTPUT_RUN_CACHE_BYTES,
            "inFlight": len(_OUTPUT_RUN_INFLIGHT),
        }


def create_or_get_output_run(
    *,
    workbook_id: str,
    sheet_name: str,
    source_filename: str,
    source_hash: str,
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    wholesale_long: pd.DataFrame | None,
    filters: dict[str, Any],
    horizon: int,
    top_n: int,
    use_working_days: bool,
    use_seasonality: bool,
    tariff_impact_pct: float,
    min_monthly_volume: float,
    requested_strategy: str,
    latest_sales_month_is_complete: bool,
    latest_sales_date: pd.Timestamp | None,
) -> tuple[dict[str, Any], bool]:
    normalized_filters = _canonical_filters(filters)
    source_signature = _source_signature(facts, working_days, wholesale_long)
    cutoff = _completed_cutoff(
        latest_sales_date,
        latest_sales_month_is_complete,
    )
    settings = {
        "horizon": int(horizon),
        "topN": int(top_n),
        "useWorkingDays": bool(use_working_days),
        "useSeasonality": bool(use_seasonality),
        "tariffImpactPct": float(tariff_impact_pct),
        "minimumMonthlyVolume": float(min_monthly_volume),
        "requestedStrategy": str(requested_strategy),
    }
    identity = {
        "contractVersion": OUTPUT_RUN_CONTRACT_VERSION,
        "workbookId": workbook_id,
        "sheetName": sheet_name,
        "sourceHash": source_hash,
        "sourceSignature": source_signature,
        "cutoff": cutoff,
        "filters": normalized_filters,
        "settings": settings,
    }
    run_id = (
        f"{OUTPUT_RUN_CONTRACT_VERSION}__"
        f"{hashlib.sha256(_canonical_json(identity).encode('utf-8')).hexdigest()[:32]}"
    )

    with _OUTPUT_RUN_LOCK:
        _evict_expired_runs()
        cached = _OUTPUT_RUNS.get(run_id)
        if cached is not None:
            _OUTPUT_RUNS.move_to_end(run_id)
            return cached.value, True
        in_flight = _OUTPUT_RUN_INFLIGHT.get(run_id)
        owner = in_flight is None
        if owner:
            in_flight = _InFlightOutputRun(event=threading.Event())
            _OUTPUT_RUN_INFLIGHT[run_id] = in_flight

    assert in_flight is not None
    if not owner:
        in_flight.event.wait()
        if in_flight.error is not None:
            raise in_flight.error
        if in_flight.value is None:
            raise RuntimeError("Forecast output run completed without a value.")
        return in_flight.value, True

    try:
        output_run = _build_output_run(
            run_id=run_id,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            source_filename=source_filename,
            source_hash=source_hash,
            source_signature=source_signature,
            facts=facts,
            working_days=working_days,
            wholesale_long=wholesale_long,
            normalized_filters=normalized_filters,
            cutoff=cutoff,
            settings=settings,
            horizon=horizon,
            top_n=top_n,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            tariff_impact_pct=tariff_impact_pct,
            min_monthly_volume=min_monthly_volume,
            requested_strategy=requested_strategy,
            latest_sales_month_is_complete=latest_sales_month_is_complete,
            latest_sales_date=latest_sales_date,
        )
        size_bytes = _estimate_output_run_bytes(output_run)
    except BaseException as exc:
        with _OUTPUT_RUN_LOCK:
            in_flight.error = exc
            _OUTPUT_RUN_INFLIGHT.pop(run_id, None)
            in_flight.event.set()
        raise

    with _OUTPUT_RUN_LOCK:
        global _OUTPUT_RUN_CACHE_BYTES
        cached_run = _CachedOutputRun(
            expires_at=_monotonic() + OUTPUT_RUN_TTL_SECONDS,
            size_bytes=size_bytes,
            value=output_run,
        )
        _OUTPUT_RUNS[run_id] = cached_run
        _OUTPUT_RUN_CACHE_BYTES += size_bytes
        _OUTPUT_RUNS.move_to_end(run_id)
        in_flight.value = output_run
        _OUTPUT_RUN_INFLIGHT.pop(run_id, None)
        _evict_to_cache_limits()
        in_flight.event.set()
    return output_run, False


def _build_output_run(
    *,
    run_id: str,
    workbook_id: str,
    sheet_name: str,
    source_filename: str,
    source_hash: str,
    source_signature: str,
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    wholesale_long: pd.DataFrame | None,
    normalized_filters: dict[str, Any],
    cutoff: str | None,
    settings: dict[str, Any],
    horizon: int,
    top_n: int,
    use_working_days: bool,
    use_seasonality: bool,
    tariff_impact_pct: float,
    min_monthly_volume: float,
    requested_strategy: str,
    latest_sales_month_is_complete: bool,
    latest_sales_date: pd.Timestamp | None,
) -> dict[str, Any]:
    filters_applied = any(
        bool(normalized_filters.get(field))
        for field in ("brand", "model", "part", "startDate", "endDate")
    )
    request_scope = {
        "filtersApplied": filters_applied,
        "brand": normalized_filters["brand"],
        "model": normalized_filters["model"],
        "part": normalized_filters["part"],
        "startDate": normalized_filters["startDate"],
        "endDate": normalized_filters["endDate"],
        "requestCutoff": cutoff,
    }
    non_revenue_strategy = (
        "auto" if requested_strategy == "reference_portfolio" else requested_strategy
    )
    effective_strategies = {
        "revenue": requested_strategy,
        "quantity": non_revenue_strategy,
        "wholesale_quantity": non_revenue_strategy,
    }
    payloads: dict[str, dict[str, Any]] = {}
    for metric in ("revenue", "quantity", "wholesale_quantity"):
        payloads[metric] = build_forecast_center(
            facts,
            working_days,
            wholesale_long,
            metric=metric,
            level="brand",
            horizon=horizon,
            top_n=top_n,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            tariff_impact_pct=tariff_impact_pct,
            model_strategy=effective_strategies[metric],
            min_monthly_volume=min_monthly_volume,
            latest_sales_month_is_complete=latest_sales_month_is_complete,
            latest_sales_date=latest_sales_date,
            include_all_records=True,
            source_hash=source_hash,
            evaluation_scope_eligible=not filters_applied,
            evaluation_scope_metadata={
                **request_scope,
                "target": metric,
            },
        )

    latest_complete_month = str(
        payloads["revenue"]["summary"]["latestCompleteMonth"]
    )
    part_quantity, part_revenue = build_part_planning_bundle(
        facts,
        quantity=payloads["quantity"],
        revenue=payloads["revenue"],
        latest_complete_month=latest_complete_month,
    )
    metadata = {
        "runId": run_id,
        "workbookId": workbook_id,
        "sheetName": sheet_name,
        "sourceHash": source_hash,
        "sourceSignature": source_signature,
        "sourceFilename": source_filename,
        "cutoff": latest_complete_month,
        "filters": normalized_filters,
        **settings,
        "effectiveStrategies": effective_strategies,
        "effectiveBrandMethods": {
            metric: payload["summary"]
            .get("modelGovernance", {})
            .get("brandSpecificMethods", {})
            for metric, payload in payloads.items()
        },
        "nowcastPeriods": payloads["revenue"]["summary"].get(
            "nowcastMonths", []
        ),
        "forecastPeriods": payloads["revenue"]["summary"].get(
            "pureForecastMonths", []
        ),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "contractVersion": OUTPUT_RUN_CONTRACT_VERSION,
        "retentionPolicy": (
            "Process-local immutable LRU/TTL cache; restart or expiry invalidates "
            "the run and every artifact returns 404 without recomputation."
        ),
    }
    executive_summary = build_canonical_executive_summary(
        metadata=metadata,
        revenue=payloads["revenue"],
        quantity=payloads["quantity"],
        wholesale=payloads["wholesale_quantity"],
    )
    excel_bytes = build_sop_workbook_bytes(
        source_filename=source_filename,
        revenue=payloads["revenue"],
        quantity=payloads["quantity"],
        wholesale=payloads["wholesale_quantity"],
        part_quantity=part_quantity,
        part_revenue=part_revenue,
        working_days=_dataframe_records(working_days),
        executive_summary=executive_summary,
        run_metadata=metadata,
    )
    try:
        pdf_bytes = build_executive_summary_pdf(executive_summary)
        pdf_status = "ready"
    except OutputDependencyUnavailable:
        pdf_bytes = None
        pdf_status = "dependency_unavailable"
    return {
        "metadata": metadata,
        "executiveSummary": executive_summary,
        "payloads": payloads,
        "partQuantity": part_quantity,
        "partRevenue": part_revenue,
        "artifacts": {
            "detailedExcel": excel_bytes,
            "executiveSummaryPdf": pdf_bytes,
            "pdfStatus": pdf_status,
        },
    }


def get_output_run(
    run_id: str,
    *,
    workbook_id: str,
    sheet_name: str,
) -> dict[str, Any] | None:
    with _OUTPUT_RUN_LOCK:
        _evict_expired_runs()
        cached = _OUTPUT_RUNS.get(run_id)
        if cached is None:
            return None
        metadata = cached.value["metadata"]
        if (
            metadata.get("workbookId") != workbook_id
            or metadata.get("sheetName") != sheet_name
        ):
            return None
        _OUTPUT_RUNS.move_to_end(run_id)
        return cached.value


def output_run_preview(output_run: dict[str, Any], *, reused: bool = False) -> dict[str, Any]:
    return {
        "metadata": deepcopy(output_run["metadata"]),
        "executiveSummary": deepcopy(output_run["executiveSummary"]),
        "artifacts": {
            "detailedExcel": "ready",
            "executiveSummaryPdf": output_run["artifacts"]["pdfStatus"],
            "currentViewCsv": "ready",
        },
        "reused": bool(reused),
    }


def build_canonical_executive_summary(
    *,
    metadata: dict[str, Any],
    revenue: dict[str, Any],
    quantity: dict[str, Any],
    wholesale: dict[str, Any],
) -> dict[str, Any]:
    payloads = {
        "revenue": revenue,
        "quantity": quantity,
        "wholesale_quantity": wholesale,
    }
    forecast_months = list(revenue["summary"].get("forecastMonths", []))
    headline_totals: list[dict[str, Any]] = []
    for month in forecast_months:
        row: dict[str, Any] = {
            "month": month,
            "periodType": _period_type(revenue, month),
        }
        for metric, payload in payloads.items():
            row[metric] = sum(
                float(item.get("value", 0.0))
                for record in payload.get("brandRecords", [])
                for item in record.get("forecast", [])
                if str(item.get("month")) == month
            )
        headline_totals.append(row)
    return {
        "contractVersion": OUTPUT_RUN_CONTRACT_VERSION,
        "metadata": deepcopy(metadata),
        "units": {
            "revenue": "USD",
            "quantity": "installed accessory units",
            "wholesale_quantity": "vehicles",
        },
        "headlineTotals": headline_totals,
        "topPlcs": deepcopy(revenue.get("topAccessories", [])),
        "reconciliation": {
            metric: deepcopy(payload["summary"].get("reconciliation", {}))
            for metric, payload in payloads.items()
        },
        "periodDefinitions": {
            "nowcast": "Partial current month using actual-to-date plus governed completion.",
            "forecast": "Future month with no target-month actuals.",
        },
    }


def build_part_planning_bundle(
    facts: pd.DataFrame,
    *,
    quantity: dict[str, Any],
    revenue: dict[str, Any],
    latest_complete_month: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the governed quantity/revenue exact-part bundle once per output run."""

    return (
        build_part_planning_records(
            facts,
            quantity.get("modelPlcRecords", []),
            metric="quantity",
            latest_complete_month=latest_complete_month,
        ),
        build_part_planning_records(
            facts,
            revenue.get("modelPlcRecords", []),
            metric="revenue",
            latest_complete_month=latest_complete_month,
        ),
    )


def build_current_view_csv(
    output_run: dict[str, Any],
    *,
    metric: str,
    level: str,
) -> str:
    if metric not in {"revenue", "quantity", "wholesale_quantity"}:
        raise ValueError(f"Unsupported metric: {metric}")
    if level not in {"brand", "model", "plc", "model_plc"}:
        raise ValueError(f"Unsupported level: {level}")
    if metric == "wholesale_quantity" and level in {"plc", "model_plc"}:
        raise ValueError("Wholesale Quantity is available at Brand and Model levels only.")
    payload = output_run["payloads"][metric]
    records = _records_for_level(payload, level)
    metadata = output_run["metadata"]
    rows: list[dict[str, Any]] = []
    for record in records:
        for forecast in record.get("forecast", []):
            rows.append(
                {
                    "runId": metadata["runId"],
                    "sourceHash": metadata["sourceHash"],
                    "cutoff": metadata["cutoff"],
                    "requestedStrategy": metadata["requestedStrategy"],
                    "effectiveStrategy": metadata["effectiveStrategies"][metric],
                    "metric": metric,
                    "unit": output_run["executiveSummary"]["units"][metric],
                    "level": record.get("level", level),
                    "brand": record.get("brand", ""),
                    "brandName": record.get("brandName", ""),
                    "modelName": record.get("modelName", ""),
                    "plc": record.get("plc", ""),
                    "rank": record.get("rank"),
                    "selectedModel": record.get("selectedModel", ""),
                    "allocationRoute": record.get("allocationRoute", ""),
                    "period": forecast.get("month"),
                    "periodType": forecast.get("forecastType", "Forecast"),
                    "value": forecast.get("value", 0.0),
                    "lower": forecast.get("lower"),
                    "point": forecast.get("point", forecast.get("value", 0.0)),
                    "upper": forecast.get("upper"),
                }
            )
    output = StringIO()
    pd.DataFrame(rows).to_csv(output, index=False)
    return output.getvalue()


def build_executive_summary_pdf(executive_summary: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ModuleNotFoundError as exc:
        raise OutputDependencyUnavailable(
            "Executive Summary PDF requires reportlab>=4.2,<5."
        ) from exc

    metadata = executive_summary["metadata"]
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=letter, pageCompression=0)
    width, height = letter
    y = height - 52

    def line(text: str, *, size: int = 9, leading: int = 14) -> None:
        nonlocal y
        if y < 54:
            document.showPage()
            y = height - 52
        document.setFont("Helvetica", size)
        document.drawString(48, y, str(text)[:130])
        y -= leading

    document.setTitle(f"PIO Executive Summary {metadata['runId']}")
    line("PIO FORECAST - EXECUTIVE SUMMARY", size=16, leading=24)
    line(f"Run ID: {metadata['runId']}")
    line(f"Source hash: {metadata['sourceHash']}")
    line(f"Source file: {metadata['sourceFilename']}")
    line(f"Cutoff: {metadata['cutoff']}")
    line(f"Requested strategy: {metadata['requestedStrategy']}")
    line(
        "Effective strategies: "
        + ", ".join(
            f"{key}={value}"
            for key, value in metadata["effectiveStrategies"].items()
        )
    )
    line(f"Nowcast periods: {', '.join(metadata['nowcastPeriods']) or 'none'}")
    line(f"Forecast periods: {', '.join(metadata['forecastPeriods']) or 'none'}")
    y -= 8
    line("Headline totals", size=12, leading=18)
    for row in executive_summary["headlineTotals"]:
        line(
            f"{row['month']} {row['periodType']} | "
            f"Revenue USD {float(row['revenue']):.2f} | "
            f"PIO Quantity {float(row['quantity']):.2f} | "
            f"Wholesale {float(row['wholesale_quantity']):.2f}"
        )
    y -= 8
    line("Reconciliation", size=12, leading=18)
    for metric, check in executive_summary["reconciliation"].items():
        line(
            f"{metric}: {check.get('status')} | "
            f"Brand-Model delta {float(check.get('brandToModelMaxAbsDelta', 0.0)):.6f} | "
            f"Model-PLC delta {float(check.get('modelToPlcMaxAbsDelta', 0.0)):.6f}"
        )
    y -= 8
    line("Top PLC revenue forecast", size=12, leading=18)
    for record in executive_summary["topPlcs"][:10]:
        line(f"{record.get('rank')}. {record.get('plc')}")
    document.save()
    return output.getvalue()


def _records_for_level(
    payload: dict[str, Any],
    level: str,
) -> list[dict[str, Any]]:
    if level == "brand":
        return payload.get("brandRecords", [])
    if level == "model":
        return payload.get("modelRecords", [])
    if level == "plc":
        return payload.get("topAccessories", [])
    top_plcs = {
        str(record.get("plc", ""))
        for record in payload.get("topAccessories", [])
    }
    return [
        record
        for record in payload.get("modelPlcRecords", [])
        if str(record.get("plc", "")) in top_plcs
    ]


def _period_type(payload: dict[str, Any], month: str) -> str:
    return (
        "Nowcast"
        if month in payload["summary"].get("nowcastMonths", [])
        else "Forecast"
    )


def _source_signature(
    facts: pd.DataFrame,
    working_days: pd.DataFrame | None,
    wholesale_long: pd.DataFrame | None,
) -> str:
    payload = {
        "facts": _frame_signature(facts),
        "workingDays": _frame_signature(working_days),
        "wholesale": _frame_signature(wholesale_long),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _frame_signature(frame: pd.DataFrame | None) -> str:
    if frame is None or frame.empty:
        return "empty"
    columns = sorted(str(column) for column in frame.columns)
    normalized = frame[columns].copy()
    for column in columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column]):
            normalized[column] = normalized[column].astype(str)
    value_hash = pd.util.hash_pandas_object(normalized, index=False).values.tobytes()
    return hashlib.sha256(
        json.dumps(columns, separators=(",", ":")).encode("utf-8") + value_hash
    ).hexdigest()


def _canonical_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "brand": sorted({str(value) for value in filters.get("brand", []) if value}),
        "model": sorted({str(value) for value in filters.get("model", []) if value}),
        "part": sorted({str(value) for value in filters.get("part", []) if value}),
        "startDate": str(filters.get("startDate", "") or ""),
        "endDate": str(filters.get("endDate", "") or ""),
    }


def _completed_cutoff(
    latest_sales_date: pd.Timestamp | None,
    latest_sales_month_is_complete: bool,
) -> str | None:
    if latest_sales_date is None or pd.isna(latest_sales_date):
        return None
    period = pd.Timestamp(latest_sales_date).to_period("M")
    if not latest_sales_month_is_complete:
        period -= 1
    return str(period)


def _dataframe_records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _estimate_output_run_bytes(output_run: dict[str, Any]) -> int:
    artifacts = output_run["artifacts"]
    structured = {
        "metadata": output_run["metadata"],
        "executiveSummary": output_run["executiveSummary"],
        "payloads": output_run["payloads"],
        "partQuantity": output_run["partQuantity"],
        "partRevenue": output_run["partRevenue"],
    }
    return (
        len(artifacts["detailedExcel"])
        + len(artifacts["executiveSummaryPdf"] or b"")
        + len(_canonical_json(structured).encode("utf-8"))
    )


def _evict_expired_runs() -> None:
    now = _monotonic()
    expired = [
        run_id
        for run_id, cached in _OUTPUT_RUNS.items()
        if cached.expires_at <= now
    ]
    for run_id in expired:
        _remove_cached_run(run_id)


def _evict_to_cache_limits() -> None:
    while _OUTPUT_RUNS and (
        len(_OUTPUT_RUNS) > OUTPUT_RUN_CACHE_LIMIT
        or _OUTPUT_RUN_CACHE_BYTES > OUTPUT_RUN_CACHE_BYTES_LIMIT
    ):
        oldest_run_id = next(iter(_OUTPUT_RUNS))
        _remove_cached_run(oldest_run_id)


def _remove_cached_run(run_id: str) -> None:
    global _OUTPUT_RUN_CACHE_BYTES
    removed = _OUTPUT_RUNS.pop(run_id, None)
    if removed is not None:
        _OUTPUT_RUN_CACHE_BYTES = max(
            0,
            _OUTPUT_RUN_CACHE_BYTES - removed.size_bytes,
        )


def _monotonic() -> float:
    return time.monotonic()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
