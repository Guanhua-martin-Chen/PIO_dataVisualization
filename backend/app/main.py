from __future__ import annotations

import json
import hashlib
import os
import pickle
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.retrieval import retrieve_analyst_context
from pio_platform.data_loader import DatasetBundle, list_workbook_sheets, load_dataset
from backend.app.memory_store import list_analyst_memories, save_analyst_memory
from pio_platform.forecasting import (
    _forecast_risk_label,
    build_anomaly_center,
    build_forecast_portfolio,
    build_forecast_narrative,
    build_monthly_part_series,
    build_watchlist,
    classify_series_regime,
    detect_series_anomalies,
    explain_latest_change,
    forecast_band,
    forecast_history,
    preprocess_history,
    select_best_model,
)
from pio_platform.fact_table import (
    build_monthly_fact_table,
    build_wholesale_long,
    build_working_days_long,
    summarize_monthly_facts,
)
from pio_platform.model_entities import build_model_entity_map, build_model_lifecycle
from pio_platform.hierarchical_forecasting import build_hierarchical_forecast
from pio_platform.forecast_center import build_forecast_center, build_part_planning_records
from pio_platform.sop_workbook import build_sop_workbook_bytes
from pio_platform.pivot import build_pivot, is_wide_month_matrix, wide_brand_series
from pio_platform.profiling import build_column_profile, build_insights, compute_kpis


# ── Role / group maps ─────────────────────────────────────────────────────────
ROLE_LABELS = {
    "date": "Time",
    "brand": "Source H/K code",
    "model": "Vehicle model",
    "model_year": "Model year",
    "part_number": "Part number",
    "part_description": "Part description",
    "plc": "PLC",
    "installation_quantity": "Installation quantity",
    "revenue": "Revenue",
}

SUPPORTING_FIELD_LABELS = {
    "PIS_MST_IVC_DT": "Invoice Date",
    "PIS_SERI": "Series",
    "YYYYMM": "Year-Month",
}

FIELD_GROUPS = {
    "date": "Time",
    "brand": "Vehicle",
    "model": "Vehicle",
    "model_year": "Vehicle",
    "part_number": "Part",
    "part_description": "Part",
    "plc": "Part",
    "installation_quantity": "Quantity",
    "revenue": "Revenue",
}

GROUP_ORDER = ["Time", "Vehicle", "Part", "Quantity", "Revenue", "Other"]

# ── Persistence constants ─────────────────────────────────────────────────────
MAX_WORKBOOKS = 20
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)
INDEX_FILE = OUTPUTS_DIR / "index.json"


# ── Session store ─────────────────────────────────────────────────────────────
@dataclass
class WorkbookSession:
    workbook_id: str
    filename: str
    file_bytes: bytes
    sheet_names: list[str]
    bundles: dict[str, DatasetBundle] = field(default_factory=dict)
    monthly_facts: dict[str, pd.DataFrame] = field(default_factory=dict)


WORKBOOKS: dict[str, WorkbookSession] = {}
# Values: "processing" | "ready" | "error"
WORKBOOK_STATUS: dict[str, str] = {}


class AnalystRequest(BaseModel):
    question: str
    focus_part: str = ""
    horizon: int = Field(default=3, ge=1, le=12)
    search: str = ""
    brand: list[str] = Field(default_factory=list)
    model: list[str] = Field(default_factory=list)
    model_year: list[str] = Field(default_factory=list)
    part: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            os.environ[key] = value
    except Exception:
        return


_load_local_env()


# ── Index helpers ─────────────────────────────────────────────────────────────
def _load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(entries: list[dict]) -> None:
    INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _bundle_cache_path(workbook_id: str, sheet_name: str) -> Path:
    # Ensure sheet_name doesn't contain path traversal characters
    safe_name = "".join(c for c in sheet_name if c.isalnum() or c in ("-", "_")).rstrip()
    return OUTPUTS_DIR / f"{workbook_id}_{safe_name}_bundle.pkl"


def _workbook_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _stored_entry_hash(entry: dict[str, Any]) -> str | None:
    stored_hash = str(entry.get("fileHash", "")).strip().lower()
    if stored_hash:
        return stored_hash
    workbook_id = str(entry.get("id", "")).strip()
    path = OUTPUTS_DIR / f"{workbook_id}.xlsx"
    if not workbook_id or not path.exists():
        return None
    return _workbook_sha256(path.read_bytes())


def _find_workbook_by_hash(file_hash: str) -> dict[str, Any] | None:
    for entry in _load_index():
        if _stored_entry_hash(entry) == file_hash.lower():
            return entry
    return None


def _add_to_index(workbook_id: str, filename: str, sheet_names: list[str], file_hash: str) -> None:
    entries = _load_index()
    # Remove duplicate
    entries = [e for e in entries if e["id"] != workbook_id]
    entries.insert(0, {
        "id": workbook_id,
        "filename": filename,
        "sheetNames": sheet_names,
        "defaultSheet": sheet_names[0] if sheet_names else None,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "fileHash": file_hash,
    })
    # Evict oldest beyond MAX_WORKBOOKS
    old = entries[MAX_WORKBOOKS:]
    entries = entries[:MAX_WORKBOOKS]
    for entry in old:
        p = OUTPUTS_DIR / f"{entry['id']}.xlsx"
        if p.exists():
            p.unlink(missing_ok=True)
        # Clean up corresponding .pkl files
        for cache_file in OUTPUTS_DIR.glob(f"{entry['id']}_*_bundle.pkl"):
            cache_file.unlink(missing_ok=True)
    _save_index(entries)


# ── Background processing ─────────────────────────────────────────────────────
def _process_workbook_background(workbook_id: str) -> None:
    """Process the default sheet in a background thread."""
    try:
        session = WORKBOOKS.get(workbook_id)
        if not session:
            WORKBOOK_STATUS[workbook_id] = "error"
            return
        _get_bundle(session, session.sheet_names[0])
        WORKBOOK_STATUS[workbook_id] = "ready"
    except Exception:
        WORKBOOK_STATUS[workbook_id] = "error"


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="PIO Demand Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workbooks")
def list_workbooks() -> list[dict[str, Any]]:
    """Return the list of previously uploaded workbooks (from disk index)."""
    return _load_index()


@app.post("/api/workbooks/upload")
async def upload_workbook(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A workbook filename is required.")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported.")

    file_bytes = await file.read()
    file_hash = _workbook_sha256(file_bytes)
    duplicate = _find_workbook_by_hash(file_hash)
    if duplicate is not None:
        return {
            "workbookId": duplicate["id"],
            "filename": duplicate["filename"],
            "sheetNames": duplicate["sheetNames"],
            "defaultSheet": duplicate.get("defaultSheet") or duplicate["sheetNames"][0],
            "duplicate": True,
        }

    sheet_names = list_workbook_sheets(file_bytes)
    if not sheet_names:
        raise HTTPException(status_code=400, detail="The uploaded workbook does not contain any sheets.")

    workbook_id = uuid4().hex

    # ── Phase 1: persist to disk and return immediately ───────────────────────
    (OUTPUTS_DIR / f"{workbook_id}.xlsx").write_bytes(file_bytes)
    _add_to_index(workbook_id, file.filename, sheet_names, file_hash)

    session = WorkbookSession(
        workbook_id=workbook_id,
        filename=file.filename,
        file_bytes=file_bytes,
        sheet_names=sheet_names,
    )
    WORKBOOKS[workbook_id] = session
    WORKBOOK_STATUS[workbook_id] = "processing"

    # ── Phase 2: heavy processing in background thread ────────────────────────
    thread = threading.Thread(
        target=_process_workbook_background,
        args=(workbook_id,),
        daemon=True,
    )
    thread.start()

    return {
        "workbookId": workbook_id,
        "filename": file.filename,
        "sheetNames": sheet_names,
        "defaultSheet": sheet_names[0],
        "duplicate": False,
    }


@app.get("/api/workbooks/{workbook_id}/status")
def get_workbook_status(workbook_id: str) -> dict[str, Any]:
    """Poll processing status. Also restores sessions after backend restarts."""
    status = WORKBOOK_STATUS.get(workbook_id)
    session = WORKBOOKS.get(workbook_id)

    if status == "ready" and session:
        return {
            "status": "ready",
            "filename": session.filename,
            "sheetNames": session.sheet_names,
            "defaultSheet": session.sheet_names[0] if session.sheet_names else None,
        }

    # Not in memory — try to restore from disk
    entries = _load_index()
    entry = next((e for e in entries if e["id"] == workbook_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Workbook not found.")

    out_file = OUTPUTS_DIR / f"{workbook_id}.xlsx"
    if not out_file.exists():
        raise HTTPException(status_code=404, detail="Workbook file not found on disk.")

    default_sheet = entry.get("defaultSheet") or entry["sheetNames"][0]
    cache_p = _bundle_cache_path(workbook_id, default_sheet)

    # ── Option A: Load from pkl cache instantly if it exists ──────────────────
    if cache_p.exists():
        if not session:
            file_bytes = out_file.read_bytes()
            session = WorkbookSession(
                workbook_id=workbook_id,
                filename=entry["filename"],
                file_bytes=file_bytes,
                sheet_names=entry["sheetNames"],
            )
            WORKBOOKS[workbook_id] = session
        
        if default_sheet not in session.bundles:
            try:
                with open(cache_p, "rb") as f:
                    session.bundles[default_sheet] = pickle.load(f)
            except Exception:
                pass

        WORKBOOK_STATUS[workbook_id] = "ready"
        return {
            "status": "ready",
            "filename": entry["filename"],
            "sheetNames": entry["sheetNames"],
            "defaultSheet": default_sheet,
        }

    # ── Option B: Cache does not exist — compute in background ────────────────
    if not session:
        file_bytes = out_file.read_bytes()
        session = WorkbookSession(
            workbook_id=workbook_id,
            filename=entry["filename"],
            file_bytes=file_bytes,
            sheet_names=entry["sheetNames"],
        )
        WORKBOOKS[workbook_id] = session

    if status != "processing":
        WORKBOOK_STATUS[workbook_id] = "processing"
        thread = threading.Thread(
            target=_process_workbook_background,
            args=(workbook_id,),
            daemon=True,
        )
        thread.start()

    return {
        "status": "processing",
        "filename": entry["filename"],
        "sheetNames": entry["sheetNames"],
        "defaultSheet": default_sheet,
    }


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}")
def get_workspace(
    workbook_id: str,
    sheet_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    sort_field: str = Query(default=""),
    sort_order: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    include_eda_dashboard: bool = Query(default=False),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    return _build_workspace_payload(
        session,
        sheet_name,
        page=page,
        page_size=page_size,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        sort_field=sort_field,
        sort_order=sort_order,
        start_date=start_date,
        end_date=end_date,
        include_eda_dashboard=include_eda_dashboard,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast")
def get_part_forecast(
    workbook_id: str,
    sheet_name: str,
    part_number: str = Query(default=""),
    horizon: int = Query(default=3, ge=1, le=12),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    return _build_forecast_payload(
        bundle=bundle,
        part_number=part_number,
        horizon=horizon,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/monthly-facts")
def get_monthly_facts(
    workbook_id: str,
    sheet_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=10, le=200),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    facts = _get_monthly_fact_table(session, sheet_name).copy()
    if brand:
        facts = _filter_fact_brand_values(facts, brand)
    if model:
        facts = facts[facts["modelName"].isin(model)]
    if part:
        facts = facts[facts["partNumber"].isin(part)]
    if start_date:
        facts = facts[facts["month"] >= str(start_date)[:7]]
    if end_date:
        facts = facts[facts["month"] <= str(end_date)[:7]]

    total_rows = int(len(facts))
    start = (page - 1) * page_size
    page_df = facts.iloc[start : start + page_size]
    return {
        "summary": summarize_monthly_facts(facts),
        "columns": list(facts.columns),
        "rows": _dataframe_records(page_df),
        "page": page,
        "pageSize": page_size,
        "totalRows": total_rows,
    }


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/hierarchical-forecast")
def get_hierarchical_forecast(
    workbook_id: str,
    sheet_name: str,
    level: str = Query(default="brand"),
    horizon: int = Query(default=6, ge=1, le=12),
    use_working_days: bool = Query(default=True),
    use_seasonality: bool = Query(default=True),
    tariff_impact_pct: float = Query(default=0.0, ge=-100.0, le=100.0),
    min_monthly_volume: float = Query(default=5.0, ge=0.0),
    model_strategy: str = Query(default="auto"),
    limit: int = Query(default=100, ge=1, le=200),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    facts = _get_monthly_fact_table(session, sheet_name).copy()
    if brand:
        facts = _filter_fact_brand_values(facts, brand)
    if model:
        facts = facts[facts["modelName"].isin(model)]
    if part:
        facts = facts[facts["partNumber"].isin(part)]
    if start_date:
        facts = facts[facts["month"] >= str(start_date)[:7]]
    if end_date:
        facts = facts[facts["month"] <= str(end_date)[:7]]
    latest_month_is_complete, _ = _forecast_cutoff_context(session, sheet_name, end_date)
    try:
        return build_hierarchical_forecast(
            facts,
            _working_days_long(session, sheet_name),
            level=level,
            horizon=horizon,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            tariff_impact_pct=tariff_impact_pct,
            min_monthly_volume=min_monthly_volume,
            model_strategy=model_strategy,
            limit=limit,
            latest_month_is_complete=latest_month_is_complete,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast-center")
def get_forecast_center(
    workbook_id: str,
    sheet_name: str,
    metric: str = Query(default="revenue"),
    level: str = Query(default="brand"),
    horizon: int = Query(default=3, ge=1, le=12),
    use_working_days: bool = Query(default=True),
    use_seasonality: bool = Query(default=True),
    tariff_impact_pct: float = Query(default=0.0, ge=-100.0, le=100.0),
    model_strategy: str = Query(default="auto"),
    min_monthly_volume: float = Query(default=5.0, ge=0.0),
    top_n: int = Query(default=10, ge=1, le=21),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    facts = _get_monthly_fact_table(session, sheet_name).copy()
    wholesale_long = _all_wholesale_long(session, sheet_name)
    facts, wholesale_long = _filter_forecast_sources(
        facts,
        wholesale_long,
        brand=brand,
        model=model,
        part=part,
        start_date=start_date,
        end_date=end_date,
    )
    latest_month_is_complete, latest_sales_date = _forecast_cutoff_context(
        session,
        sheet_name,
        end_date,
    )
    try:
        return build_forecast_center(
            facts,
            _working_days_long(session, sheet_name),
            wholesale_long,
            metric=metric,
            level=level,
            horizon=horizon,
            use_working_days=use_working_days,
            use_seasonality=use_seasonality,
            tariff_impact_pct=tariff_impact_pct,
            model_strategy=model_strategy,
            min_monthly_volume=min_monthly_volume,
            top_n=top_n,
            latest_sales_month_is_complete=latest_month_is_complete,
            latest_sales_date=latest_sales_date,
            source_hash=_workbook_sha256(session.file_bytes),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast-center/export.csv")
def export_forecast_center_csv(
    workbook_id: str,
    sheet_name: str,
    metric: str = Query(default="revenue"),
    level: str = Query(default="brand"),
    horizon: int = Query(default=3, ge=1, le=12),
    top_n: int = Query(default=10, ge=1, le=21),
    use_working_days: bool = Query(default=True),
    use_seasonality: bool = Query(default=True),
    tariff_impact_pct: float = Query(default=0.0, ge=-100.0, le=100.0),
    model_strategy: str = Query(default="auto"),
    min_monthly_volume: float = Query(default=5.0, ge=0.0),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    facts = _get_monthly_fact_table(session, sheet_name).copy()
    wholesale_long = _all_wholesale_long(session, sheet_name)
    facts, wholesale_long = _filter_forecast_sources(
        facts,
        wholesale_long,
        brand=brand,
        model=model,
        part=part,
        start_date=start_date,
        end_date=end_date,
    )
    latest_month_is_complete, latest_sales_date = _forecast_cutoff_context(
        session,
        sheet_name,
        end_date,
    )
    payload = build_forecast_center(
        facts,
        _working_days_long(session, sheet_name),
        wholesale_long,
        metric=metric,
        level=level,
        horizon=horizon,
        top_n=top_n,
        use_working_days=use_working_days,
        use_seasonality=use_seasonality,
        tariff_impact_pct=tariff_impact_pct,
        model_strategy=model_strategy,
        min_monthly_volume=min_monthly_volume,
        latest_sales_month_is_complete=latest_month_is_complete,
        latest_sales_date=latest_sales_date,
        source_hash=_workbook_sha256(session.file_bytes),
    )
    rows: list[dict[str, Any]] = []
    for record in payload["records"]:
        for forecast in record.get("forecast", []):
            rows.append(
                {
                    "metric": metric,
                    "level": record.get("level", level),
                    "brand": record.get("brand", ""),
                    "brandName": record.get("brandName", ""),
                    "modelName": record.get("modelName", ""),
                    "plc": record.get("plc", ""),
                    "rank": record.get("rank"),
                    "selectedModel": record.get("selectedModel", ""),
                    "allocationRoute": record.get("allocationRoute", ""),
                    "month": forecast.get("month"),
                    "forecastType": forecast.get("forecastType", "Forecast"),
                    "value": forecast.get("value", 0.0),
                    "allocationShare": forecast.get("allocationShare"),
                    "reconciliationFactor": forecast.get("reconciliationFactor"),
                }
            )
    output = StringIO()
    pd.DataFrame(rows).to_csv(output, index=False)
    output.seek(0)
    filename = f"{session.filename.rsplit('.', 1)[0]}-forecast-center-{metric}-{level}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast-center/export.xlsx")
def export_forecast_center_xlsx(
    workbook_id: str,
    sheet_name: str,
    horizon: int = Query(default=3, ge=1, le=12),
    top_n: int = Query(default=10, ge=1, le=21),
    use_working_days: bool = Query(default=True),
    use_seasonality: bool = Query(default=True),
    tariff_impact_pct: float = Query(default=0.0, ge=-100.0, le=100.0),
    model_strategy: str = Query(default="auto"),
    min_monthly_volume: float = Query(default=5.0, ge=0.0),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    facts = _get_monthly_fact_table(session, sheet_name)
    working_days = _working_days_long(session, sheet_name)
    wholesale_long = _all_wholesale_long(session, sheet_name)
    latest_complete = _latest_sales_month_is_complete(session, sheet_name)
    latest_date = _latest_sales_date(session, sheet_name)
    common = {
        "horizon": horizon,
        "top_n": top_n,
        "latest_sales_month_is_complete": latest_complete,
        "latest_sales_date": latest_date,
        "include_all_records": True,
        "use_working_days": use_working_days,
        "use_seasonality": use_seasonality,
        "tariff_impact_pct": tariff_impact_pct,
        "model_strategy": model_strategy,
        "min_monthly_volume": min_monthly_volume,
    }
    revenue = build_forecast_center(
        facts,
        working_days,
        wholesale_long,
        metric="revenue",
        level="brand",
        **common,
        source_hash=_workbook_sha256(session.file_bytes),
    )
    non_revenue_common = dict(common)
    if model_strategy == "reference_portfolio":
        non_revenue_common["model_strategy"] = "auto"
    quantity = build_forecast_center(
        facts,
        working_days,
        wholesale_long,
        metric="quantity",
        level="brand",
        **non_revenue_common,
        source_hash=_workbook_sha256(session.file_bytes),
    )
    wholesale = build_forecast_center(
        facts,
        working_days,
        wholesale_long,
        metric="wholesale_quantity",
        level="brand",
        **non_revenue_common,
        source_hash=_workbook_sha256(session.file_bytes),
    )
    part_quantity = build_part_planning_records(
        facts,
        quantity.get("modelPlcRecords", []),
        metric="quantity",
        latest_complete_month=str(quantity["summary"]["latestCompleteMonth"]),
    )
    part_revenue = build_part_planning_records(
        facts,
        revenue.get("modelPlcRecords", []),
        metric="revenue",
        latest_complete_month=str(revenue["summary"]["latestCompleteMonth"]),
    )
    output = build_sop_workbook_bytes(
        source_filename=session.filename,
        revenue=revenue,
        quantity=quantity,
        wholesale=wholesale,
        part_quantity=part_quantity,
        part_revenue=part_revenue,
        working_days=_dataframe_records(working_days),
    )
    filename = f"{session.filename.rsplit('.', 1)[0]}-PIO-Forecast-SOP.xlsx"
    return StreamingResponse(
        iter([output]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast/export.csv")
def export_forecast_csv(
    workbook_id: str,
    sheet_name: str,
    part_number: str = Query(default=""),
    horizon: int = Query(default=3, ge=1, le=12),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    payload = _build_forecast_payload(
        bundle=bundle,
        part_number=part_number,
        horizon=horizon,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        start_date=start_date,
        end_date=end_date,
    )

    series_df = pd.DataFrame(payload["series"])
    series_df.insert(0, "part_number", payload["selectedPart"])
    series_df.insert(1, "part_description", payload.get("partDescription"))
    output = StringIO()
    series_df.to_csv(output, index=False)
    output.seek(0)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}-forecast-{payload["selectedPart"]}.csv"'
        )
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast/export.xlsx")
def export_forecast_xlsx(
    workbook_id: str,
    sheet_name: str,
    part_number: str = Query(default=""),
    horizon: int = Query(default=3, ge=1, le=12),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    payload = _build_forecast_payload(
        bundle=bundle,
        part_number=part_number,
        horizon=horizon,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        start_date=start_date,
        end_date=end_date,
    )

    import io

    summary_df = pd.DataFrame(
        [
            {
                "partNumber": payload["selectedPart"],
                "partDescription": payload.get("partDescription"),
                "historyMonths": payload["summary"]["historyMonths"],
                "horizon": payload["summary"]["horizon"],
                "modelName": payload["summary"]["modelName"],
                "confidence": payload["summary"]["confidence"],
                "forecastRisk": payload["summary"]["forecastRisk"],
                "latestActual": payload["summary"]["latestActual"],
                "nextForecast": payload["summary"]["nextForecast"],
                "recent3MonthAverage": payload["summary"]["recent3MonthAverage"],
                "deltaPct": payload["summary"]["deltaPct"],
                "mae": payload["summary"]["mae"],
                "wape": payload["summary"]["wape"],
                "bias": payload["summary"]["bias"],
                "regime": payload["summary"]["regime"],
                "preprocessing": payload["summary"]["preprocessing"],
                "selectionBasis": payload["summary"]["selectionBasis"],
            }
        ]
    )
    series_df = pd.DataFrame(payload["series"])
    candidate_df = pd.DataFrame(payload["summary"]["candidateScores"])
    portfolio_df = pd.DataFrame(payload["portfolio"]["records"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        series_df.to_excel(writer, sheet_name="ForecastSeries", index=False)
        candidate_df.to_excel(writer, sheet_name="ModelBacktest", index=False)
        portfolio_df.to_excel(writer, sheet_name="Portfolio", index=False)
    output.seek(0)

    headers = {
        "Content-Disposition": (
            f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}-forecast-{payload["selectedPart"]}.xlsx"'
        )
    }
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/anomaly-center")
def get_anomaly_center(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    sales_sheet = _forecast_sales_sheet_name(session, sheet_name)
    bundle = _get_bundle(session, sales_sheet)
    all_wholesale = _all_wholesale_long(session, sales_sheet)
    anomaly_wholesale_long = pd.DataFrame(columns=["brand", "model", "month", "wholesale"])
    if not all_wholesale.empty:
        anomaly_wholesale_long = all_wholesale.loc[
            :,
            ["brand", "modelName", "month", "wholesaleUnits"],
        ].rename(
            columns={
                "modelName": "model",
                "wholesaleUnits": "wholesale",
            }
        )
    return _build_anomaly_center_payload(
        bundle=bundle,
        wholesale_bundle=None,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        start_date=start_date,
        end_date=end_date,
        wholesale_long=anomaly_wholesale_long,
    )


@app.post("/api/workbooks/{workbook_id}/sheets/{sheet_name}/analyst")
def ask_ai_analyst(
    workbook_id: str,
    sheet_name: str,
    payload: AnalystRequest,
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    wholesale_bundle = _find_wholesale_bundle(session, exclude_sheet=sheet_name)
    return _build_analyst_payload(
        bundle=bundle,
        wholesale_bundle=wholesale_bundle,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        question=payload.question,
        focus_part=payload.focus_part,
        horizon=payload.horizon,
        search=payload.search,
        brand=payload.brand,
        model=payload.model,
        model_year=payload.model_year,
        part=payload.part,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/analyst/memories")
def get_analyst_memories(
    workbook_id: str,
    sheet_name: str,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, Any]:
    _get_bundle(_get_session(workbook_id), sheet_name)
    return {
        "items": list_analyst_memories(workbook_id=workbook_id, sheet_name=sheet_name, limit=limit),
    }


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/pivot")
def get_pivot(
    workbook_id: str,
    sheet_name: str,
    rows: list[str] = Query(default=[]),
    cols: list[str] = Query(default=[]),
    measure: str = Query(default="quantity"),
    agg: str = Query(default="sum"),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )
    return build_pivot(
        filtered_df=filtered,
        roles=bundle.roles,
        date_candidates=bundle.date_candidates,
        row_fields=rows,
        col_fields=cols,
        measure=measure,
        agg=agg,
        wide_start_year=_infer_start_year(session, exclude_sheet=sheet_name),
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/export.csv")
def export_filtered_csv(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    visible_cols: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )

    if visible_cols:
        cols_to_export = [c for c in visible_cols.split(",") if c in filtered.columns]
        if cols_to_export:
            filtered = filtered[cols_to_export]

    output = StringIO()
    filtered.to_csv(output, index=False)
    output.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}.csv"'
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/export.xlsx")
def export_filtered_xlsx(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    visible_cols: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )

    if visible_cols:
        cols_to_export = [c for c in visible_cols.split(",") if c in filtered.columns]
        if cols_to_export:
            filtered = filtered[cols_to_export]

    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        filtered.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    output.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}.xlsx"'
    }
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )



@app.exception_handler(Exception)
def unhandled_exception(_: Any, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Session helpers ───────────────────────────────────────────────────────────
def _get_session(workbook_id: str) -> WorkbookSession:
    session = WORKBOOKS.get(workbook_id)
    if session:
        return session

    # Try restoring from disk (backend restart case)
    entries = _load_index()
    entry = next((e for e in entries if e["id"] == workbook_id), None)
    out_file = OUTPUTS_DIR / f"{workbook_id}.xlsx"
    if not entry or not out_file.exists():
        raise HTTPException(status_code=404, detail="Workbook session not found.")

    file_bytes = out_file.read_bytes()
    session = WorkbookSession(
        workbook_id=workbook_id,
        filename=entry["filename"],
        file_bytes=file_bytes,
        sheet_names=entry["sheetNames"],
    )
    WORKBOOKS[workbook_id] = session
    return session


def _get_bundle(session: WorkbookSession, sheet_name: str) -> DatasetBundle:
    if sheet_name not in session.sheet_names:
        raise HTTPException(status_code=404, detail="Sheet not found in workbook.")
    
    if sheet_name in session.bundles:
        return session.bundles[sheet_name]

    cache_p = _bundle_cache_path(session.workbook_id, sheet_name)
    if cache_p.exists():
        try:
            with open(cache_p, "rb") as f:
                bundle = pickle.load(f)
            session.bundles[sheet_name] = bundle
            return bundle
        except Exception:
            pass

    # No cache file — parse and infer
    bundle = load_dataset(session.file_bytes, sheet_name, header_mode="Auto detect")
    session.bundles[sheet_name] = bundle

    # Save to disk cache
    try:
        with open(cache_p, "wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass

    return bundle


def _build_workspace_payload(
    session: WorkbookSession,
    sheet_name: str,
    page: int,
    page_size: int,
    search: str = "",
    brand: list[str] | None = None,
    model: list[str] | None = None,
    model_year: list[str] | None = None,
    part: list[str] | None = None,
    model_query: str = "",
    part_query: str = "",
    sort_field: str = "",
    sort_order: str = "",
    start_date: str = "",
    end_date: str = "",
    include_eda_dashboard: bool = False,
) -> dict[str, Any]:
    bundle = _get_bundle(session, sheet_name)
    if bundle.dataframe.empty:
        raise HTTPException(status_code=400, detail="The selected worksheet does not contain a usable dataset.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand or [],
        model=model or [],
        model_year=model_year or [],
        part=part or [],
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )
    page_data = _build_table_page(
        bundle=bundle,
        filtered_df=filtered,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    payload = {
        "workbook": {
            "id": session.workbook_id,
            "filename": session.filename,
            "sheetNames": session.sheet_names,
        },
        "sheetName": sheet_name,
        "profile": bundle.profile,
        "roles": bundle.roles,
        "overview": _build_overview(session.filename, sheet_name, bundle, filtered),
        "table": page_data,
        "classification": _build_field_classification(bundle),
        "insights": _build_chart_payloads(session, sheet_name, bundle, filtered),
        "filters": {
            "search": search,
            "brand": brand or [],
            "model": model or [],
            "modelYear": model_year or [],
            "part": part or [],
            "modelQuery": model_query,
            "partQuery": part_query,
            "startDate": start_date,
            "endDate": end_date,
        },
        "filterOptions": _build_filter_options(
            bundle,
            search=search,
            brand=brand,
            model=model,
            model_year=model_year,
            part=part,
            model_query=model_query,
            part_query=part_query,
            start_date=start_date,
            end_date=end_date,
        ),
    }
    if include_eda_dashboard:
        payload["edaDashboard"] = _build_eda_dashboard(session, sheet_name, bundle, filtered)
    return payload


def _build_eda_dashboard(
    session: WorkbookSession,
    sheet_name: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
) -> dict[str, Any]:
    df = filtered_df.copy()
    columns = _resolve_eda_sales_columns(bundle)
    date_series = _eda_date_series(bundle, df, columns["date"])
    revenue = _eda_numeric_series(df, columns["revenue"])
    quantity = _eda_numeric_series(df, columns["quantity"])
    wholesale_long = _prepare_eda_wholesale_long(session, sheet_name)

    overview = {
        "rowCount": int(len(df)),
        "timeRange": {
            "min": date_series.min().date().isoformat() if date_series.notna().any() else None,
            "max": date_series.max().date().isoformat() if date_series.notna().any() else None,
        },
        "modelCount": _eda_nunique(df, columns["model"]),
        "modelCodeCount": _eda_nunique(df, columns["model_code"]),
        "partCount": _eda_nunique(df, columns["part_number"]),
        "brandCount": _eda_nunique(df, columns["brand"]),
        "totalRevenue": _eda_float_or_none(revenue.sum()) if revenue is not None else None,
        "totalQuantity": _eda_float_or_none(quantity.sum()) if quantity is not None else None,
    }

    monthly = _build_eda_monthly(df, columns, date_series, revenue, quantity, wholesale_long)
    relationship = _build_eda_relationship(df, columns, monthly, wholesale_long, bundle.profile)
    model_entities = build_model_entity_map(
        df,
        model_col=columns["model"],
        brand_col=columns["brand"],
        model_code_col=columns["model_code"],
        model_year_col=bundle.roles.get("model_year"),
    )
    model_lifecycle = build_model_lifecycle(
        df,
        date_series,
        model_col=columns["model"],
        qty_col=columns["quantity"],
        brand_col=columns["brand"],
        model_code_col=columns["model_code"],
        cutoff_year=2024,
    )
    source_anchor_audit = _build_eda_source_anchor_audit(
        df,
        columns,
        date_series,
        revenue,
        quantity,
        _get_monthly_fact_table(session, sheet_name),
    )

    return {
        "overview": overview,
        "dataQuality": _build_eda_data_quality(df, columns, revenue, quantity),
        "monthly": monthly,
        "rankings": {
            "topModels": _eda_top_groups(df, columns["model"], revenue, quantity),
            "topParts": _eda_top_parts(df, columns, revenue, quantity),
            "topBrands": _eda_top_groups(df, columns["brand"], revenue, quantity),
        },
        "relationship": relationship,
        "modelEntities": model_entities,
        "modelLifecycle": model_lifecycle,
        "sourceAnchorAudit": source_anchor_audit,
    }


def _build_eda_source_anchor_audit(
    df: pd.DataFrame,
    columns: dict[str, str | None],
    date_series: pd.Series,
    revenue: pd.Series | None,
    quantity: pd.Series | None,
    facts: pd.DataFrame,
) -> dict[str, Any]:
    required = [columns.get("brand"), columns.get("model")]
    if any(column is None or column not in df.columns for column in required):
        return {"latestMonth": None, "summary": [], "sourceHModels": []}

    source_col = str(columns["brand"])
    model_col = str(columns["model"])
    working = pd.DataFrame(index=df.index)
    working["sourceCode"] = df[source_col].fillna("").astype(str).str.strip().str.upper()
    working["modelName"] = df[model_col].fillna("").astype(str).str.strip()
    working["date"] = pd.to_datetime(date_series.reindex(df.index), errors="coerce")
    working["month"] = working["date"].dt.to_period("M").astype(str)
    working["quantity"] = (
        pd.to_numeric(quantity.reindex(df.index), errors="coerce").fillna(0.0).clip(lower=0)
        if quantity is not None
        else 0.0
    )
    working["revenue"] = (
        pd.to_numeric(revenue.reindex(df.index), errors="coerce").fillna(0.0).clip(lower=0)
        if revenue is not None
        else 0.0
    )
    model_year_col = columns.get("model_year")
    working["modelYear"] = (
        df[model_year_col]
        .fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        if model_year_col and model_year_col in df.columns
        else ""
    )

    def mode_text(values: pd.Series) -> str:
        cleaned = values.dropna().astype(str).str.strip()
        cleaned = cleaned[(cleaned != "") & (cleaned.str.lower() != "nan")]
        return cleaned.mode().iloc[0] if not cleaned.empty else ""

    mapping = (
        facts[["brand", "modelName", "anchorBrand", "anchorMappingMethod"]]
        .groupby(["brand", "modelName"], as_index=False, dropna=False)
        .agg(
            anchorBrand=("anchorBrand", mode_text),
            anchorMappingMethod=("anchorMappingMethod", mode_text),
        )
        .rename(columns={"brand": "sourceCode"})
        if not facts.empty
        else pd.DataFrame(
            columns=["sourceCode", "modelName", "anchorBrand", "anchorMappingMethod"]
        )
    )
    working = working.merge(mapping, on=["sourceCode", "modelName"], how="left")
    working["anchorBrand"] = working["anchorBrand"].fillna(
        working["sourceCode"].map({"K": "KUS"}).fillna("HMA")
    )
    working["anchorMappingMethod"] = working["anchorMappingMethod"].fillna(
        working["sourceCode"].map({"K": "source_brand_kus"}).fillna("hma_default_fallback")
    )
    working = working[(working["modelName"] != "") & working["date"].notna()].copy()
    if working.empty:
        return {"latestMonth": None, "summary": [], "sourceHModels": []}

    latest_month = str(working["month"].max())
    summary = (
        working[working["month"] == latest_month]
        .groupby(["sourceCode", "anchorBrand"], as_index=False, dropna=False)
        .agg(pioQuantity=("quantity", "sum"), pioRevenue=("revenue", "sum"))
        .sort_values(["sourceCode", "anchorBrand"], kind="stable")
    )

    def unique_text(values: pd.Series) -> list[str]:
        cleaned = {
            str(value).strip()
            for value in values
            if pd.notna(value)
            and str(value).strip()
            and str(value).strip().lower() != "nan"
        }
        return sorted(cleaned, key=lambda value: (int(value) if value.isdigit() else 9999, value))

    source_h_records: list[dict[str, Any]] = []
    source_h = working[working["sourceCode"] == "H"]
    for (anchor, model, method), group in source_h.groupby(
        ["anchorBrand", "modelName", "anchorMappingMethod"],
        dropna=False,
        sort=True,
    ):
        latest_quantity = float(group.loc[group["month"] == latest_month, "quantity"].sum())
        source_h_records.append(
            {
                "sourceCode": "H",
                "anchorBrand": str(anchor),
                "modelName": str(model),
                "mappingMethod": str(method),
                "modelYears": unique_text(group["modelYear"]),
                "salesYears": [str(year) for year in sorted(group["date"].dt.year.dropna().astype(int).unique())],
                "firstSaleDate": group["date"].min().date().isoformat(),
                "lastSaleDate": group["date"].max().date().isoformat(),
                "latestMonth": latest_month,
                "latestMonthQuantity": latest_quantity,
                "totalQuantity": float(group["quantity"].sum()),
                "totalRevenue": float(group["revenue"].sum()),
            }
        )
    source_h_records.sort(
        key=lambda record: (
            str(record["anchorBrand"]),
            -float(record["latestMonthQuantity"]),
            str(record["modelName"]),
        )
    )
    return {
        "latestMonth": latest_month,
        "summary": _dataframe_records(summary),
        "sourceHModels": source_h_records,
    }


def _resolve_eda_sales_columns(bundle: DatasetBundle) -> dict[str, str | None]:
    df = bundle.dataframe

    def pick(*candidates: str | None) -> str | None:
        for candidate in candidates:
            if candidate and candidate in df.columns:
                return candidate
        return None

    return {
        "date": pick(bundle.roles.get("date"), "PIS_MST_IVC_DT", "YYYYMM"),
        "brand": pick("PIS_CMP_KND", bundle.roles.get("brand")),
        "model": pick(bundle.roles.get("model"), "Model"),
        "model_year": pick(bundle.roles.get("model_year"), "PIS_MDL_YY", "Model Year"),
        "model_code": pick("PIS_SERI"),
        "part_number": pick(bundle.roles.get("part_number"), "PIS_PNO"),
        "part_description": pick(bundle.roles.get("part_description"), "Part Description"),
        "plc": pick(bundle.roles.get("plc"), "PLC"),
        "quantity": pick(bundle.roles.get("installation_quantity"), "SumOfPIS_INST_QT"),
        "revenue": pick(bundle.roles.get("revenue"), "SumOfPIS_CRP_CFM_PRI"),
    }


def _eda_date_series(bundle: DatasetBundle, df: pd.DataFrame, column: str | None) -> pd.Series:
    if column and column in bundle.date_candidates:
        return bundle.date_candidates[column].reindex(df.index)
    if column and column in df.columns:
        if column == "YYYYMM":
            return pd.to_datetime(df[column].astype(str) + "01", format="%Y%m%d", errors="coerce")
        return pd.to_datetime(df[column], errors="coerce")
    return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")


def _eda_numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series | None:
    if not column or column not in df.columns:
        return None
    return pd.to_numeric(df[column], errors="coerce")


def _eda_nunique(df: pd.DataFrame, column: str | None) -> int:
    if not column or column not in df.columns:
        return 0
    values = df[column].dropna().astype(str).str.strip()
    return int(values[values != ""].nunique())


def _eda_float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _build_eda_monthly(
    df: pd.DataFrame,
    columns: dict[str, str | None],
    date_series: pd.Series,
    revenue: pd.Series | None,
    quantity: pd.Series | None,
    wholesale_long: pd.DataFrame,
) -> list[dict[str, Any]]:
    work = pd.DataFrame({"__date": date_series})
    work["__month"] = work["__date"].dt.to_period("M").astype(str)
    work["__revenue"] = revenue if revenue is not None else 0.0
    work["__quantity"] = quantity if quantity is not None else 0.0
    work = work[work["__date"].notna()]
    sales_monthly = (
        work.groupby("__month", as_index=False)
        .agg(pioRevenue=("__revenue", "sum"), pioQuantity=("__quantity", "sum"))
    )

    if wholesale_long.empty:
        merged = sales_monthly
        merged["wholesaleUnits"] = pd.NA
    else:
        wholesale_monthly = wholesale_long.groupby("month", as_index=False).agg(wholesaleUnits=("units", "sum"))
        merged = sales_monthly.merge(wholesale_monthly, left_on="__month", right_on="month", how="outer")
        merged["__month"] = merged["__month"].fillna(merged["month"])
        merged = merged.drop(columns=["month"], errors="ignore")

    merged = merged.sort_values("__month")
    latest_month = work["__date"].max().to_period("M").to_timestamp() if not work.empty else None
    if latest_month is not None:
        merged["__monthStart"] = pd.to_datetime(merged["__month"] + "-01", errors="coerce")
        merged = merged[merged["__monthStart"] < latest_month].drop(columns=["__monthStart"], errors="ignore")
    rows: list[dict[str, Any]] = []
    for record in merged.to_dict("records"):
        wholesale_units = _eda_float_or_none(record.get("wholesaleUnits"))
        pio_revenue = _eda_float_or_none(record.get("pioRevenue")) or 0.0
        pio_quantity = _eda_float_or_none(record.get("pioQuantity")) or 0.0
        rows.append(
            {
                "month": record["__month"],
                "pioRevenue": pio_revenue,
                "pioQuantity": pio_quantity,
                "wholesaleUnits": wholesale_units,
                "pnvw": (pio_revenue / wholesale_units) if wholesale_units and wholesale_units != 0 else None,
            }
        )
    return rows


def _build_eda_data_quality(
    df: pd.DataFrame,
    columns: dict[str, str | None],
    revenue: pd.Series | None,
    quantity: pd.Series | None,
) -> dict[str, Any]:
    labels = {
        "date": "Date",
        "brand": "Brand",
        "model": "Model",
        "model_code": "Model code",
        "part_number": "Part number",
        "part_description": "Part description",
        "quantity": "Quantity",
        "revenue": "Revenue",
    }
    missing = []
    total_rows = max(len(df), 1)
    for key, label in labels.items():
        column = columns.get(key)
        if column and column in df.columns:
            blank_mask = df[column].isna() | (df[column].astype(str).str.strip() == "")
            missing_count = int(blank_mask.sum())
        else:
            missing_count = len(df)
        missing.append(
            {
                "field": label,
                "column": column,
                "missing": missing_count,
                "missingPct": round(missing_count / total_rows * 100, 2),
            }
        )

    unit_price = None
    if revenue is not None and quantity is not None:
        unit_price = revenue.where(quantity != 0) / quantity.where(quantity != 0)
        unit_price = unit_price.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if unit_price is not None and len(unit_price) >= 2:
        p01 = float(unit_price.quantile(0.01))
        p99 = float(unit_price.quantile(0.99))
        unit_outliers = int(((unit_price < p01) | (unit_price > p99)).sum())
    else:
        p01 = None
        p99 = None
        unit_outliers = 0

    return {
        "missing": missing,
        "outliers": {
            "negativeRevenueRows": int((revenue < 0).sum()) if revenue is not None else 0,
            "negativeQuantityRows": int((quantity < 0).sum()) if quantity is not None else 0,
            "zeroQuantityRows": int((quantity == 0).sum()) if quantity is not None else 0,
            "unitPriceOutlierRows": unit_outliers,
            "unitPriceP01": p01,
            "unitPriceP99": p99,
        },
        "partDescriptionIssues": _build_eda_part_description_issues(
            df,
            columns.get("part_number"),
            columns.get("part_description"),
        ),
    }


def _build_eda_part_description_issues(
    df: pd.DataFrame,
    part_col: str | None,
    desc_col: str | None,
) -> list[dict[str, Any]]:
    if not part_col or not desc_col or part_col not in df.columns or desc_col not in df.columns:
        return []
    work = df[[part_col, desc_col]].dropna().copy()
    work[part_col] = work[part_col].astype(str).str.strip()
    work[desc_col] = work[desc_col].astype(str).str.strip()
    work = work[(work[part_col] != "") & (work[desc_col] != "")]
    if work.empty:
        return []
    rows = []
    for part_number, group in work.groupby(part_col):
        descriptions = sorted(group[desc_col].dropna().unique().tolist())
        normalized_descriptions = {
            " ".join(description.lower().split())
            for description in descriptions
        }
        if len(descriptions) > 1:
            rows.append(
                {
                    "partNumber": part_number,
                    "issueType": "description_mismatch" if len(normalized_descriptions) > 1 else "format_warning",
                    "descriptionCount": len(normalized_descriptions),
                    "variantCount": len(descriptions),
                    "descriptions": descriptions[:5],
                    "rows": int(len(group)),
                }
            )
    return sorted(
        rows,
        key=lambda row: (row["issueType"] == "description_mismatch", row["descriptionCount"], row["rows"]),
        reverse=True,
    )[:10]


def _eda_top_groups(
    df: pd.DataFrame,
    group_col: str | None,
    revenue: pd.Series | None,
    quantity: pd.Series | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not group_col or group_col not in df.columns:
        return []
    metric = revenue if revenue is not None else quantity
    if metric is None:
        return []
    work = pd.DataFrame({"name": df[group_col].fillna("").astype(str).str.strip(), "value": metric})
    work = work[work["name"] != ""]
    grouped = work.groupby("name", as_index=False)["value"].sum().sort_values("value", ascending=False).head(limit)
    return [{"name": row["name"], "value": float(row["value"])} for row in grouped.to_dict("records")]


def _eda_top_parts(
    df: pd.DataFrame,
    columns: dict[str, str | None],
    revenue: pd.Series | None,
    quantity: pd.Series | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    part_col = columns.get("part_number")
    desc_col = columns.get("part_description")
    if not part_col or part_col not in df.columns:
        return []
    metric = revenue if revenue is not None else quantity
    if metric is None:
        return []
    names = df[part_col].fillna("").astype(str).str.strip()
    if desc_col and desc_col in df.columns:
        desc = df[desc_col].fillna("").astype(str).str.strip()
        names = names.where(desc == "", names + " - " + desc)
    work = pd.DataFrame({"name": names, "value": metric})
    work = work[work["name"] != ""]
    grouped = work.groupby("name", as_index=False)["value"].sum().sort_values("value", ascending=False).head(limit)
    return [{"name": row["name"], "value": float(row["value"])} for row in grouped.to_dict("records")]


def _build_eda_relationship(
    df: pd.DataFrame,
    columns: dict[str, str | None],
    monthly: list[dict[str, Any]],
    wholesale_long: pd.DataFrame,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    corr_df = pd.DataFrame(monthly)
    corr = None
    if {"pioRevenue", "wholesaleUnits"}.issubset(corr_df.columns):
        pairs = corr_df[["pioRevenue", "wholesaleUnits"]].dropna()
        if len(pairs) >= 2 and pairs["pioRevenue"].nunique() > 1 and pairs["wholesaleUnits"].nunique() > 1:
            corr = round(float(pairs["pioRevenue"].corr(pairs["wholesaleUnits"])), 3)

    sales_codes: set[str] = set()
    code_rows: dict[str, list[int]] = {}
    model_code_col = columns.get("model_code")
    if model_code_col and model_code_col in df.columns:
        normalized = _eda_normalized_code_frame(df, model_code_col, profile or {})
        sales_codes = set(normalized["value"].tolist())
        for value, group in normalized.groupby("value"):
            code_rows[value] = [int(row) for row in group["excelRow"].head(5).tolist()]
    wholesale_codes: set[str] = set()
    if not wholesale_long.empty and "modelCode" in wholesale_long.columns:
        wholesale_codes = set(_eda_normalize_code_series(wholesale_long["modelCode"]))
    matched = sales_codes & wholesale_codes
    coverage = round(len(matched) / len(sales_codes) * 100, 2) if sales_codes else None

    model_col = columns.get("model")
    sales_model_names: set[str] = set()
    wholesale_model_names: set[str] = set()
    ambiguous_sales_codes: list[dict[str, Any]] = []
    ambiguous_wholesale_codes: list[dict[str, Any]] = []
    if model_col and model_col in df.columns:
        sales_model_names = set(_eda_normalize_model_name_series(df[model_col]))
        if model_code_col and model_code_col in df.columns:
            ambiguous_sales_codes = _eda_ambiguous_model_codes(
                pd.DataFrame({"code": df[model_code_col], "model": df[model_col]})
            )
    if not wholesale_long.empty and "model" in wholesale_long.columns:
        wholesale_model_names = set(_eda_normalize_model_name_series(wholesale_long["model"]))
        if "modelCode" in wholesale_long.columns:
            ambiguous_wholesale_codes = _eda_ambiguous_model_codes(
                pd.DataFrame({"code": wholesale_long["modelCode"], "model": wholesale_long["model"]})
            )
    matched_model_names = sales_model_names & wholesale_model_names
    model_name_coverage = (
        round(len(matched_model_names) / len(sales_model_names) * 100, 2)
        if sales_model_names
        else None
    )

    return {
        "revenueWholesaleCorrelation": corr,
        "matchedModelCodes": len(matched),
        "salesModelCodes": len(sales_codes),
        "wholesaleModelCodes": len(wholesale_codes),
        "modelCodeCoveragePct": coverage,
        "matchedModelNames": len(matched_model_names),
        "salesModelNames": len(sales_model_names),
        "wholesaleModelNames": len(wholesale_model_names),
        "modelNameCoveragePct": model_name_coverage,
        "ambiguousSalesModelCodes": ambiguous_sales_codes,
        "ambiguousWholesaleModelCodes": ambiguous_wholesale_codes,
        "unmatchedSalesModelCodes": [
            {"value": value, "rows": code_rows.get(value, [])}
            for value in sorted(sales_codes - wholesale_codes)[:10]
        ],
    }


def _eda_normalize_code_series(series: pd.Series) -> list[str]:
    values = series.dropna().astype(str).str.strip().str.upper()
    return [value for value in values.unique().tolist() if value]


def _eda_normalize_model_name_series(series: pd.Series) -> list[str]:
    values = (
        series.dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )
    return [value for value in values.unique().tolist() if value]


def _eda_ambiguous_model_codes(frame: pd.DataFrame) -> list[dict[str, Any]]:
    working = frame.copy()
    working["code"] = working["code"].fillna("").astype(str).str.strip().str.upper()
    working["model"] = (
        working["model"].fillna("").astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    )
    working = working[(working["code"] != "") & (working["model"] != "")].drop_duplicates()
    if working.empty:
        return []
    grouped = working.groupby("code")["model"].agg(lambda values: sorted(set(values)))
    return [
        {"value": str(code), "models": models}
        for code, models in grouped.items()
        if len(models) > 1
    ]


def _filter_wholesale_for_sales_slice(
    sales_df: pd.DataFrame,
    wholesale_long: pd.DataFrame,
    model_col: str | None,
    model_code_col: str | None,
) -> pd.DataFrame:
    """Match a filtered sales slice without treating a shared model code as a unique vehicle key."""
    if wholesale_long.empty or not model_col or model_col not in sales_df.columns or "model" not in wholesale_long.columns:
        return wholesale_long

    sales = pd.DataFrame({"model": sales_df[model_col]})
    if model_code_col and model_code_col in sales_df.columns:
        sales["code"] = sales_df[model_code_col]
    else:
        sales["code"] = ""
    sales["modelKey"] = (
        sales["model"].fillna("").astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    )
    sales["codeKey"] = sales["code"].fillna("").astype(str).str.strip().str.upper()
    sales = sales[(sales["modelKey"] != "")].drop_duplicates()
    if sales.empty:
        return wholesale_long.iloc[0:0].copy()

    wholesale = wholesale_long.copy()
    wholesale["__modelKey"] = (
        wholesale["model"].fillna("").astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    )
    wholesale["__codeKey"] = (
        wholesale.get("modelCode", pd.Series("", index=wholesale.index))
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    sales_names = set(sales["modelKey"])
    matched = wholesale["__modelKey"].isin(sales_names)

    unmatched_sales = sales[~sales["modelKey"].isin(set(wholesale["__modelKey"]))]
    if not unmatched_sales.empty:
        code_cardinality = wholesale.groupby("__codeKey")["__modelKey"].nunique()
        unique_codes = set(code_cardinality[code_cardinality == 1].index) - {""}
        safe_fallback_codes = set(unmatched_sales["codeKey"]) & unique_codes
        if safe_fallback_codes:
            matched |= wholesale["__codeKey"].isin(safe_fallback_codes)

    return wholesale.loc[matched].drop(columns=["__modelKey", "__codeKey"])


def _eda_normalized_code_frame(df: pd.DataFrame, column: str, profile: dict[str, Any]) -> pd.DataFrame:
    header_row = int(profile.get("header_row", 1) or 1)
    header_depth = int(profile.get("header_depth", 1) or 1)
    values = df[column].dropna().astype(str).str.strip().str.upper()
    values = values[values != ""]
    return pd.DataFrame(
        {
            "value": values,
            "excelRow": [int(index) + header_row + header_depth for index in values.index],
        }
    )


def _prepare_eda_wholesale_long(session: WorkbookSession, current_sheet: str) -> pd.DataFrame:
    frames = _all_wholesale_long(session, current_sheet)
    if frames.empty:
        return pd.DataFrame(columns=["brand", "model", "modelCode", "month", "units"])
    return frames.rename(
        columns={"modelName": "model", "modelCode": "modelCode", "wholesaleUnits": "units"}
    )[["brand", "model", "modelCode", "month", "units"]]


def _eda_month_number_from_column(column: Any) -> int | None:
    label = str(column).strip().lower().split(".")[0][:3]
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return months.get(label)


def _get_column_profile(bundle: DatasetBundle) -> pd.DataFrame:
    if not hasattr(bundle, "_cached_column_profile"):
        bundle._cached_column_profile = build_column_profile(bundle.dataframe, bundle.date_candidates)
    return bundle._cached_column_profile


def _build_overview(
    filename: str,
    sheet_name: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
) -> dict[str, Any]:
    kpis = compute_kpis(filtered_df, bundle.roles)
    profile_df = _get_column_profile(bundle)
    health = {
        "dateFieldCount": len(bundle.date_fields),
        "numericFieldCount": len(bundle.numeric_fields),
        "categoryFieldCount": len(bundle.categorical_fields),
        "mappedRoleCount": len(bundle.roles),
        "highMissingFields": profile_df[profile_df["Missing %"] >= 20]["Column"].head(3).tolist(),
    }

    date_summary = _date_summary(bundle, filtered_df)
    summary = [
        f"{filename} / {sheet_name} has {bundle.profile['row_count']:,} rows across {bundle.profile['column_count']} columns.",
        date_summary,
        f"Detected {health['mappedRoleCount']} business-ready fields for planning workflows.",
    ]
    if health["highMissingFields"]:
        summary.append("Highest missing columns: " + ", ".join(health["highMissingFields"]))

    insights = build_insights(filtered_df, bundle.roles, bundle.date_candidates, "en")

    # Calculate Leaderboard Metrics
    leaders = {}
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")
    revenue_col = bundle.roles.get("revenue")
    qty_col = bundle.roles.get("installation_quantity")

    if brand_col and brand_col in filtered_df.columns:
        metric = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
        if metric:
            top_brand = filtered_df.groupby(brand_col)[metric].sum().sort_values(ascending=False)
            if not top_brand.empty:
                leaders["topBrand"] = {
                    "name": str(top_brand.index[0]),
                    "value": float(top_brand.iloc[0]),
                    "metric": "Revenue" if metric == revenue_col else "Quantity",
                }

    if model_col and model_col in filtered_df.columns:
        metric = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
        if metric:
            top_model = filtered_df.groupby(model_col)[metric].sum().sort_values(ascending=False)
            if not top_model.empty:
                leaders["topModel"] = {
                    "name": str(top_model.index[0]),
                    "value": float(top_model.iloc[0]),
                    "metric": "Revenue" if metric == revenue_col else "Quantity",
                }

    if part_col and part_col in filtered_df.columns:
        metric = qty_col if qty_col and qty_col in filtered_df.columns else revenue_col
        if metric:
            top_part = filtered_df.groupby(part_col)[metric].sum().sort_values(ascending=False)
            if not top_part.empty:
                leaders["topPart"] = {
                    "name": str(top_part.index[0]),
                    "value": float(top_part.iloc[0]),
                    "metric": "Quantity" if metric == qty_col else "Revenue",
                }

    # Calculate additional average/density metrics
    stats = {}
    total_rev = float(filtered_df[revenue_col].sum()) if revenue_col and revenue_col in filtered_df.columns else None
    total_qty = float(filtered_df[qty_col].sum()) if qty_col and qty_col in filtered_df.columns else None
    total_records = len(filtered_df)

    if total_rev is not None and total_qty is not None and total_qty > 0:
        stats["avgUnitPrice"] = total_rev / total_qty
    if total_qty is not None and total_records > 0:
        stats["avgQtyPerRow"] = total_qty / total_records
    if total_rev is not None and total_records > 0:
        stats["avgRevPerRow"] = total_rev / total_records

    # Overall file completeness (mean non-missing %)
    stats["completenessRate"] = float(100.0 - profile_df["Missing %"].mean())

    return {
        "datasetTitle": filename,
        "sheetName": sheet_name,
        "kpis": kpis,
        "summary": summary,
        "health": health,
        "autoInsights": insights,
        "leaders": leaders,
        "stats": stats,
    }


def _build_field_classification(bundle: DatasetBundle) -> dict[str, list[dict[str, Any]]]:
    inverse_roles = {column: role for role, column in bundle.roles.items()}
    profile_df = _get_column_profile(bundle)
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in GROUP_ORDER}


    for row in profile_df.to_dict("records"):
        column = row["Column"]
        role = inverse_roles.get(column)
        group = _resolve_group(column, role, bundle)
        confidence = "High" if role else "Medium" if group != "Other" else "Low"
        groups[group].append(
            {
                "column": column,
                "group": group,
                "detectedRole": ROLE_LABELS.get(role) if role else SUPPORTING_FIELD_LABELS.get(column, "Supporting field"),
                "confidence": confidence,
                "type": row["Type"],
                "missingPct": row["Missing %"],
                "uniqueCount": row["Unique"],
                "sampleValues": row["Sample Values"],
            }
        )

    return {group: groups[group] for group in GROUP_ORDER if groups[group]}


def _resolve_group(column: str, role: str | None, bundle: DatasetBundle) -> str:
    if role and role in FIELD_GROUPS:
        return FIELD_GROUPS[role]
    if column in bundle.date_fields:
        return "Time"
    if column in bundle.numeric_fields:
        return "Other"
    lowered = column.lower()
    if "model" in lowered or "brand" in lowered:
        return "Vehicle"
    if "part" in lowered or "desc" in lowered:
        return "Part"
    return "Other"


def _build_chart_payloads(
    session: WorkbookSession,
    sheet_name: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
) -> dict[str, Any]:
    charts: dict[str, Any] = {}
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    revenue_col = bundle.roles.get("revenue")
    model_col = bundle.roles.get("model")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")

    if date_col and date_col in bundle.date_candidates and qty_col and qty_col in filtered_df.columns:
        charts["monthlyInstallation"] = _monthly_chart(
            bundle.date_candidates[date_col].loc[filtered_df.index],
            filtered_df[qty_col],
            qty_col,
        )

    if date_col and date_col in bundle.date_candidates and revenue_col and revenue_col in filtered_df.columns:
        charts["monthlyRevenue"] = _monthly_chart(
            bundle.date_candidates[date_col].loc[filtered_df.index],
            filtered_df[revenue_col],
            revenue_col,
        )

    if model_col and revenue_col and model_col in filtered_df.columns and revenue_col in filtered_df.columns:
        top_models = (
            filtered_df.groupby(model_col, dropna=True)[revenue_col]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
        charts["topModels"] = {
            "title": "Top vehicle models by revenue",
            "labels": [str(index) for index in top_models.index.tolist()],
            "values": [float(value) for value in top_models.tolist()],
        }

    metric_col = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
    if part_col and metric_col and part_col in filtered_df.columns:
        top_parts = (
            filtered_df.groupby(part_col, dropna=True)[metric_col]
            .sum()
            .sort_values(ascending=False)
            .head(12)
        )
        charts["topParts"] = {
            "title": f"Top parts by {'revenue' if metric_col == revenue_col else 'installation quantity'}",
            "labels": [str(index) for index in top_parts.index.tolist()],
            "values": [float(value) for value in top_parts.tolist()],
        }

    charts.update(_build_wholesale_chart_payloads(session, sheet_name, bundle, filtered_df))

    return charts


def _build_wholesale_chart_payloads(
    session: WorkbookSession,
    sheet_name: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
) -> dict[str, Any]:
    columns = _resolve_eda_sales_columns(bundle)
    date_series = _eda_date_series(bundle, filtered_df, columns["date"])
    revenue = _eda_numeric_series(filtered_df, columns["revenue"])
    wholesale_long = _prepare_eda_wholesale_long(session, sheet_name)
    if wholesale_long.empty or revenue is None or date_series.dropna().empty:
        return {}

    wholesale_long = _filter_wholesale_for_sales_slice(
        filtered_df,
        wholesale_long,
        model_col=columns.get("model"),
        model_code_col=columns.get("model_code"),
    )
    if wholesale_long.empty:
        return {}

    sales = pd.DataFrame({"date": date_series, "revenue": revenue})
    sales = sales[sales["date"].notna()].copy()
    if sales.empty:
        return {}
    latest_month = sales["date"].max().to_period("M").to_timestamp()
    sales["month"] = sales["date"].dt.to_period("M").astype(str)
    sales_monthly = sales.groupby("month", as_index=False).agg(pioRevenue=("revenue", "sum"))
    wholesale_monthly = wholesale_long.groupby("month", as_index=False).agg(wholesaleUnits=("units", "sum"))
    monthly = sales_monthly.merge(wholesale_monthly, on="month", how="inner")
    monthly["monthStart"] = pd.to_datetime(monthly["month"] + "-01", errors="coerce")
    monthly = monthly[monthly["monthStart"] < latest_month].sort_values("month")
    if monthly.empty:
        return {}

    pnvw_values = []
    for row in monthly.to_dict("records"):
        units = float(row["wholesaleUnits"])
        pnvw_values.append(float(row["pioRevenue"]) / units if units else 0.0)

    return {
        "monthlyWholesale": {
            "title": "Wholesale monthly trend",
            "labels": monthly["month"].astype(str).tolist(),
            "values": [float(value) for value in monthly["wholesaleUnits"].tolist()],
        },
        "monthlyPnvw": {
            "title": "PNVW monthly trend",
            "labels": monthly["month"].astype(str).tolist(),
            "values": pnvw_values,
        },
    }


def _monthly_chart(date_series: pd.Series, value_series: pd.Series, metric_name: str) -> dict[str, Any]:
    chart_df = pd.DataFrame(
        {"month": date_series.dt.to_period("M").dt.to_timestamp(), metric_name: value_series}
    )
    chart_df = chart_df.groupby("month", dropna=True)[metric_name].sum().reset_index()
    return {
        "title": metric_name,
        "labels": [value.strftime("%Y-%m") for value in chart_df["month"].tolist()],
        "values": [float(value) for value in chart_df[metric_name].tolist()],
    }


def _build_table_page(
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
    page: int,
    page_size: int,
    sort_field: str,
    sort_order: str,
) -> dict[str, Any]:
    working = filtered_df.copy()
    model_year_col = bundle.roles.get("model_year")
    if sort_field and sort_field in working.columns:
        ascending = sort_order not in {"descend", "desc"}
        if sort_field in bundle.date_fields:
            sorter = bundle.date_candidates[sort_field].loc[working.index]
            working = working.assign(__sorter=sorter).sort_values(
                by="__sorter", ascending=ascending, na_position="last", kind="mergesort"
            )
            working = working.drop(columns="__sorter")
        else:
            working = working.sort_values(by=sort_field, ascending=ascending, na_position="last", kind="mergesort")

    total_rows = len(working)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = working.iloc[start:end].copy()

    columns = []
    default_visible = []
    inverse_roles = {column: role for role, column in bundle.roles.items()}

    for column in working.columns:
        role = inverse_roles.get(column)
        columns.append(
            {
                "key": column,
                "title": column,
                "role": ROLE_LABELS.get(role) if role else SUPPORTING_FIELD_LABELS.get(column, ""),
                "type": "year" if column == model_year_col else "date" if column in bundle.date_fields else _dtype_name(working[column]),
            }
        )
        if role or len(default_visible) < 8:
            default_visible.append(column)

    rows = []
    for row_index, (_, row) in enumerate(page_df.iterrows()):
        serialized = {"id": start + row_index}
        for column in page_df.columns:
            parsed_date = None
            if column in bundle.date_candidates:
                parsed_date = bundle.date_candidates[column].loc[row.name]
            serialized[column] = _serialize_cell(
                row[column],
                date_fields=bundle.date_fields,
                column=column,
                parsed_date=parsed_date,
                model_year_col=model_year_col,
            )
        rows.append(serialized)

    return {
        "columns": columns,
        "rows": rows,
        "totalRows": total_rows,
        "page": page,
        "pageSize": page_size,
        "defaultVisibleColumns": default_visible,
    }


def _apply_filters(
    bundle: DatasetBundle,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    part: list[str],
    model_query: str,
    part_query: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    df = bundle.dataframe
    mask = pd.Series(True, index=df.index)

    date_col = bundle.roles.get("date")
    if date_col and date_col in bundle.date_candidates:
        parsed = bundle.date_candidates[date_col]
        if start_date:
            mask &= parsed >= pd.to_datetime(start_date, errors="coerce")
        if end_date:
            mask &= parsed <= pd.to_datetime(end_date, errors="coerce")

    brand_col = bundle.roles.get("brand")
    if brand and brand_col and brand_col in df.columns:
        brand_series = _display_series_for_column(bundle, brand_col)
        mask &= brand_series.isin(brand)

    model_col = bundle.roles.get("model")
    if model and model_col and model_col in df.columns:
        mask &= df[model_col].fillna("").astype(str).isin(model)
    if model_query and model_col and model_col in df.columns:
        mask &= df[model_col].fillna("").astype(str).str.contains(model_query, case=False, regex=False)

    model_year_col = bundle.roles.get("model_year")
    if model_year and model_year_col and model_year_col in df.columns:
        year_series = _display_series_for_column(bundle, model_year_col)
        mask &= year_series.isin(model_year)

    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")
    if part and part_col and part_col in df.columns:
        mask &= df[part_col].fillna("").astype(str).isin(part)
    if part_query and part_col and part_col in df.columns:
        mask &= df[part_col].fillna("").astype(str).str.contains(part_query, case=False, regex=False)

    if search:
        search_columns = list(dict.fromkeys(
            [
                column
                for column in [
                    bundle.roles.get("brand"),
                    bundle.roles.get("model"),
                    bundle.roles.get("part_number"),
                    bundle.roles.get("part_description"),
                ]
                if column and column in df.columns
            ] + bundle.categorical_fields[:6]
        ))
        tokens = [token.strip().lower() for token in search.split() if token.strip()]
        if tokens and search_columns:
            combined = df[search_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            token_mask = pd.Series(True, index=df.index)
            for token in tokens:
                token_mask &= combined.str.contains(token, regex=False)
            mask &= token_mask

    return df.loc[mask].copy()


def _build_filter_options(
    bundle: DatasetBundle,
    search: str = "",
    brand: list[str] | None = None,
    model: list[str] | None = None,
    model_year: list[str] | None = None,
    part: list[str] | None = None,
    model_query: str = "",
    part_query: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    brand = brand or []
    model = model or []
    model_year = model_year or []
    part = part or []

    date_range = _filter_date_range(bundle)

    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    model_year_col = bundle.roles.get("model_year")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")

    # 1. Brand options: apply all filters EXCEPT brand
    if brand_col and brand_col in bundle.dataframe.columns:
        df_for_brand = _apply_filters(
            bundle, search, brand=[], model=model, model_year=model_year, part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        brand_options = _build_value_options(
            _display_series_for_column(bundle, brand_col).loc[df_for_brand.index],
            limit=25,
        )
    else:
        brand_options = []

    # 2. Model options: apply all filters EXCEPT model
    if model_col and model_col in bundle.dataframe.columns:
        df_for_model = _apply_filters(
            bundle, search, brand=brand, model=[], model_year=model_year, part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        model_options = _build_value_options(df_for_model[model_col], limit=80)
    else:
        model_options = []

    # 3. Model Year options: apply all filters EXCEPT model_year
    if model_year_col and model_year_col in bundle.dataframe.columns:
        df_for_my = _apply_filters(
            bundle, search, brand=brand, model=model, model_year=[], part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        model_year_options = _build_value_options(
            _display_series_for_column(bundle, model_year_col).loc[df_for_my.index],
            limit=20,
            sort_by_count=False,
        )
    else:
        model_year_options = []

    # 4. Part options: apply all filters EXCEPT part
    if part_col and part_col in bundle.dataframe.columns:
        df_for_part = _apply_filters(
            bundle, search, brand=brand, model=model, model_year=model_year, part=[],
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        part_options = _build_value_options(df_for_part[part_col], limit=120)
    else:
        part_options = []

    return {
        "dateRange": date_range,
        "brand": brand_options,
        "model": model_options,
        "modelYear": model_year_options,
        "part": part_options,
    }


def _build_forecast_payload(
    bundle: DatasetBundle,
    part_number: str,
    horizon: int,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_number_col = bundle.roles.get("part_number")
    part_description_col = bundle.roles.get("part_description")

    if not date_col or date_col not in bundle.date_candidates:
        raise HTTPException(status_code=400, detail="Forecasting requires a reliable date field.")
    if not qty_col or qty_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Forecasting requires an installation quantity field.")
    if not part_number_col or part_number_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Forecasting requires a part number field.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=[],
        model_query="",
        part_query="",
        start_date=start_date,
        end_date=end_date,
    )
    if filtered.empty:
        raise HTTPException(status_code=400, detail="No rows remain after applying the selected forecast filters.")

    part_options = _build_part_number_options(
        filtered,
        part_number_col=part_number_col,
        qty_col=qty_col,
        description_col=part_description_col,
        limit=120,
    )
    if not part_options:
        raise HTTPException(status_code=400, detail="No part numbers are available for forecasting in the selected slice.")

    portfolio = build_forecast_portfolio(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        part_description_col=part_description_col,
        scan_limit=60,
        top_n=18,
    )

    selected_part = part_number or portfolio.get("recommendedPart") or part_options[0]["value"]
    part_series = build_monthly_part_series(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        part_value=selected_part,
    )
    if part_series.empty:
        raise HTTPException(status_code=404, detail="The selected part does not have a usable monthly history.")

    history = part_series["actual"].astype(float).tolist()
    model_name, candidate_scores, diagnostics = select_best_model(history)
    forecast_input, adjusted_points = preprocess_history(history, diagnostics.preprocessing)
    forecast_values = forecast_history(forecast_input, horizon=horizon, model_name=model_name)
    bands = forecast_band(history, forecast_values, diagnostics)
    anomalies = detect_series_anomalies(part_series)
    regime = classify_series_regime(history)
    forecast_risk = _forecast_risk_label(diagnostics, regime, anomalies)
    narrative = build_forecast_narrative(
        history,
        forecast_values,
        diagnostics,
        regime=regime,
        forecast_risk=forecast_risk,
    )
    change_analysis = explain_latest_change(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        part_value=selected_part,
        brand_col=brand_col,
        model_col=model_col,
    )

    future_months = pd.date_range(part_series["month"].max() + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    forecast_rows = [
        {
            "month": month.strftime("%Y-%m"),
            "actual": None,
            "forecast": band["forecast"],
            "lower": band["lower"],
            "upper": band["upper"],
        }
        for month, band in zip(future_months, bands)
    ]
    history_rows = [
        {
            "month": month.strftime("%Y-%m"),
            "actual": float(actual),
            "forecast": None,
            "lower": None,
            "upper": None,
        }
        for month, actual in zip(part_series["month"], part_series["actual"])
    ]

    description = None
    if part_description_col and part_description_col in filtered.columns:
        desc_series = (
            filtered.loc[filtered[part_number_col].fillna("").astype(str) == selected_part, part_description_col]
            .dropna()
            .astype(str)
        )
        if not desc_series.empty:
            description = desc_series.mode().iloc[0]

    recent_avg = float(pd.Series(history[-3:]).mean()) if history else 0.0
    latest_actual = float(history[-1]) if history else 0.0
    next_forecast = float(forecast_values[0]) if forecast_values else 0.0
    delta_pct = ((next_forecast - latest_actual) / latest_actual * 100) if latest_actual else None

    return {
        "selectedPart": selected_part,
        "partDescription": description,
        "partOptions": part_options,
        "summary": {
            "historyMonths": diagnostics.history_months,
            "horizon": horizon,
            "modelName": diagnostics.model_name,
            "confidence": diagnostics.confidence,
            "preprocessing": diagnostics.preprocessing,
            "selectionBasis": diagnostics.selection_basis,
            "adjustedMonths": adjusted_points,
            "candidateScores": candidate_scores,
            "latestActual": latest_actual,
            "recent3MonthAverage": recent_avg,
            "nextForecast": next_forecast,
            "deltaPct": float(delta_pct) if delta_pct is not None else None,
            "mae": diagnostics.mae,
            "wape": diagnostics.wape,
            "bias": diagnostics.bias,
            "regime": regime["label"],
            "regimeCode": regime["code"],
            "forecastRisk": forecast_risk,
        },
        "series": history_rows + forecast_rows,
        "insights": narrative,
        "anomalies": anomalies,
        "changeAnalysis": change_analysis,
        "watchlist": build_watchlist(
            filtered,
            part_col=part_number_col,
            qty_col=qty_col,
            date_series=bundle.date_candidates[date_col],
            limit=8,
        ),
        "portfolio": portfolio,
    }


def _build_anomaly_center_payload(
    bundle: DatasetBundle,
    wholesale_bundle: DatasetBundle | None,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    part: list[str],
    start_date: str,
    end_date: str,
    wholesale_long: pd.DataFrame | None = None,
) -> dict[str, Any]:
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_number_col = bundle.roles.get("part_number")
    part_description_col = bundle.roles.get("part_description")

    if not date_col or date_col not in bundle.date_candidates:
        raise HTTPException(status_code=400, detail="Anomaly Center requires a reliable date field.")
    if not qty_col or qty_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Anomaly Center requires an installation quantity field.")
    if not part_number_col or part_number_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Anomaly Center requires a part number field.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query="",
        part_query="",
        start_date=start_date,
        end_date=end_date,
    )
    if filtered.empty:
        raise HTTPException(status_code=400, detail="No rows remain after applying the selected anomaly filters.")

    anomaly_center = build_anomaly_center(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        brand_col=brand_col,
        model_col=model_col,
        part_description_col=part_description_col,
        wholesale_df=wholesale_bundle.dataframe if wholesale_bundle else None,
        wholesale_long_df=wholesale_long,
        limit=12,
    )
    anomaly_center["filters"] = {
        "search": search,
        "brand": brand,
        "model": model,
        "modelYear": model_year,
        "part": part,
        "startDate": start_date,
        "endDate": end_date,
    }
    return anomaly_center


def _build_analyst_payload(
    bundle: DatasetBundle,
    wholesale_bundle: DatasetBundle | None,
    workbook_id: str,
    sheet_name: str,
    question: str,
    focus_part: str,
    horizon: int,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    part: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    prompt = question.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="A question is required for the AI Analyst.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query="",
        part_query="",
        start_date=start_date,
        end_date=end_date,
    )
    if filtered.empty:
        raise HTTPException(status_code=400, detail="No rows remain after applying the selected AI Analyst filters.")

    kpis = compute_kpis(filtered, bundle.roles)
    anomaly_center = _build_anomaly_center_payload(
        bundle=bundle,
        wholesale_bundle=wholesale_bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        start_date=start_date,
        end_date=end_date,
    )
    resolved_part = _resolve_analyst_part(
        question=prompt,
        focus_part=focus_part,
        anomaly_center=anomaly_center,
        filtered=filtered,
        roles=bundle.roles,
    )

    used_tools = ["workspace_filters", "kpi_summary", "anomaly_center"]
    warnings: list[str] = []
    forecast_payload = None
    if resolved_part:
        try:
            forecast_payload = _build_forecast_payload(
                bundle=bundle,
                part_number=resolved_part,
                horizon=horizon,
                search=search,
                brand=brand,
                model=model,
                model_year=model_year,
                start_date=start_date,
                end_date=end_date,
            )
            used_tools.append("forecast_center")
        except HTTPException as exc:
            warnings.append(exc.detail)

    intent = _classify_analyst_intent(prompt)
    draft_answer, evidence = _compose_analyst_answer(
        question=prompt,
        intent=intent,
        kpis=kpis,
        anomaly_center=anomaly_center,
        forecast_payload=forecast_payload,
        retrieved_context=[],
    )
    retrieved_context = retrieve_analyst_context(
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        question=prompt,
        bundle=bundle,
        filtered_df=filtered,
        anomaly_center=anomaly_center,
        forecast_payload=forecast_payload,
        filters={
            "search": search,
            "brand": brand,
            "model": model,
            "modelYear": model_year,
            "part": part,
            "startDate": start_date,
            "endDate": end_date,
        },
    )
    if retrieved_context:
        used_tools.append("context_retrieval")
        draft_answer, evidence = _compose_analyst_answer(
            question=prompt,
            intent=intent,
            kpis=kpis,
            anomaly_center=anomaly_center,
            forecast_payload=forecast_payload,
            retrieved_context=retrieved_context,
        )
    risk_level = _derive_analyst_risk(anomaly_center=anomaly_center, forecast_payload=forecast_payload)
    recommended_actions = _derive_recommended_actions(
        anomaly_center=anomaly_center,
        forecast_payload=forecast_payload,
    )
    follow_up_questions = _build_follow_up_questions(
        anomaly_center=anomaly_center,
        forecast_payload=forecast_payload,
    )

    mode = "grounded_tools"
    model_name = None
    llm_answer = _maybe_rewrite_with_llm(
        question=prompt,
        draft_answer=draft_answer,
        evidence=evidence,
        used_tools=used_tools,
        kpis=kpis,
        anomaly_center=anomaly_center,
        forecast_payload=forecast_payload,
        retrieved_context=retrieved_context,
    )
    if llm_answer:
        draft_answer = llm_answer["answer"]
        mode = llm_answer["mode"]
        model_name = llm_answer["model"]
    elif _ai_gateway_configured():
        warnings.append("The external AI gateway was configured but did not return a usable answer, so the grounded fallback was used.")

    memory_id = save_analyst_memory(
        {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "workbookId": workbook_id,
            "sheetName": sheet_name,
            "question": prompt,
            "focusPart": forecast_payload["selectedPart"] if forecast_payload else resolved_part or None,
            "riskLevel": risk_level,
            "answer": draft_answer,
            "evidence": evidence,
            "recommendedActions": recommended_actions,
            "followUpQuestions": follow_up_questions,
            "usedTools": used_tools,
            "warnings": warnings,
            "mode": mode,
            "model": model_name,
            "retrievedContext": retrieved_context,
            "filters": {
                "search": search,
                "brand": brand,
                "model": model,
                "modelYear": model_year,
                "part": part,
                "startDate": start_date,
                "endDate": end_date,
            },
        }
    )

    return {
        "memoryId": memory_id,
        "question": prompt,
        "answer": draft_answer,
        "evidence": evidence,
        "usedTools": used_tools,
        "focusPart": forecast_payload["selectedPart"] if forecast_payload else resolved_part or None,
        "riskLevel": risk_level,
        "recommendedActions": recommended_actions,
        "followUpQuestions": follow_up_questions,
        "mode": mode,
        "model": model_name,
        "warnings": warnings,
        "retrievedContext": retrieved_context,
    }


def _resolve_analyst_part(
    question: str,
    focus_part: str,
    anomaly_center: dict[str, Any],
    filtered: pd.DataFrame,
    roles: dict[str, str],
) -> str:
    if focus_part:
        return focus_part

    part_col = roles.get("part_number")
    if part_col and part_col in filtered.columns:
        parts = (
            filtered[part_col]
            .dropna()
            .astype(str)
            .loc[lambda s: s.str.strip() != ""]
            .unique()
            .tolist()
        )
        lowered = question.lower()
        for part_value in parts:
            if part_value and part_value.lower() in lowered:
                return part_value

    if anomaly_center.get("records"):
        return str(anomaly_center["records"][0]["part"])
    return ""


def _classify_analyst_intent(question: str) -> str:
    lowered = question.lower()
    if any(token in lowered for token in ["forecast", "predict", "next month", "next year", "confidence", "wape", "bias", "mae", "trust"]):
        return "forecast"
    if any(token in lowered for token in ["why", "drop", "decline", "down", "rose", "rise", "increase", "anomaly", "alert", "abnormal", "change"]):
        return "change"
    return "overview"


def _derive_analyst_risk(
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
) -> str:
    if forecast_payload:
        forecast_risk = str(forecast_payload["summary"].get("forecastRisk", "")).lower()
        confidence = str(forecast_payload["summary"].get("confidence", "")).lower()
        wape = forecast_payload["summary"].get("wape")
        if forecast_risk == "high" or confidence == "low" or (wape is not None and wape >= 0.55):
            return "High"
        if forecast_risk == "medium" or confidence == "medium" or (wape is not None and wape >= 0.3):
            return "Medium"

    top_alert = (anomaly_center.get("records") or [None])[0]
    if top_alert:
        if top_alert.get("forecastRisk") == "High" or top_alert.get("regimeCode") in {"structural_drop", "structural_ramp"}:
            return "High"
        if top_alert.get("forecastRisk") == "Medium" or top_alert.get("regimeCode") in {"declining", "accelerating", "volatile"}:
            return "Medium"
    return "Low"


def _derive_recommended_actions(
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
) -> list[str]:
    actions: list[str] = []
    top_alert = (anomaly_center.get("records") or [None])[0]
    if top_alert:
        actions.append(f"Review the latest monthly change for part {top_alert['part']} before using it in a planning decision.")
        if top_alert.get("modelDrivers"):
            driver = top_alert["modelDrivers"][0]
            actions.append(f"Check whether the shift is concentrated in model {driver['name']} because it is currently the top demand driver.")
        if top_alert.get("wholesaleSignal") and top_alert["wholesaleSignal"].get("relationshipStrength") == "Weak":
            actions.append("Do not assume wholesale alone explains the movement; inspect part-specific factors such as mix shift or program timing.")
        if top_alert.get("regimeCode") == "structural_drop":
            actions.append("Treat the series as a potential structural decline and avoid extrapolating older higher-volume months into near-term supply plans.")
        elif top_alert.get("regimeCode") == "structural_ramp":
            actions.append("Treat the series as a ramping part and review whether new-program demand is distorting the baseline.")

    if forecast_payload:
        summary = forecast_payload["summary"]
        if summary.get("forecastRisk") == "High":
            actions.append("Use the point forecast as a high-risk baseline only; apply planner override or scenario ranges before committing inventory.")
        elif summary.get("forecastRisk") == "Medium":
            actions.append("Compare the point forecast with recent 3-month average and anomaly notes before locking next-month demand.")
        if summary.get("bias") is not None and summary["bias"] <= -0.25:
            actions.append("The model has a meaningful under-forecast tendency, so review upside risk before finalizing replenishment.")
        if summary.get("bias") is not None and summary["bias"] >= 0.25:
            actions.append("The model has a meaningful over-forecast tendency, so sanity-check downside risk before finalizing replenishment.")

    if not actions:
        actions.append("No urgent risk is surfaced in the current slice, so the next step is to review the top parts and confirm the filter scope.")
    return actions[:4]


def _build_follow_up_questions(
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
) -> list[str]:
    top_alert = (anomaly_center.get("records") or [None])[0]
    follow_ups: list[str] = []

    if top_alert:
        follow_ups.append(f"Is the latest change in {top_alert['part']} driven by one model or broad-based demand?")
        follow_ups.append(f"Does {top_alert['part']} look like a structural shift or a one-month anomaly?")
    if forecast_payload:
        focus = forecast_payload["selectedPart"]
        follow_ups.append(f"What planner override range would be reasonable for {focus} given the current forecast risk?")
        follow_ups.append(f"How does {focus} compare with its recent 3-month average and anomaly pattern?")

    if not follow_ups:
        follow_ups = [
            "Which part deserves planner review first in the current slice?",
            "Can the current forecast be trusted for the top alert part?",
        ]
    return follow_ups[:4]


def _compose_analyst_answer(
    question: str,
    intent: str,
    kpis: dict[str, Any],
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
    retrieved_context: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    records = anomaly_center.get("records", [])
    top_alert = records[0] if records else None
    evidence: list[str] = []

    total_records = int(kpis.get("Total Records") or 0)
    total_qty = kpis.get("Total Installation Quantity")
    total_revenue = kpis.get("Total Sales Revenue")
    part_count = kpis.get("Distinct Part Count")

    evidence.append(f"Current filtered scope contains {total_records:,} rows, {part_count or 0:,} distinct parts, {total_qty:,.0f} installation units, and ${total_revenue:,.0f} revenue." if total_qty is not None and total_revenue is not None else f"Current filtered scope contains {total_records:,} rows.")

    if top_alert:
        evidence.append(
            f"Top anomaly lead is {top_alert['part']} ({top_alert['regime']}) with {top_alert['forecastRisk'].lower()} forecast risk and {(top_alert['deltaPct'] or 0):+.1f}% latest-month change."
        )
        for line in top_alert.get("evidence", [])[:2]:
            evidence.append(line)

    if forecast_payload:
        summary = forecast_payload["summary"]
        if summary.get("wape") is not None and summary.get("bias") is not None:
            evidence.append(
                f"Forecast focus part {forecast_payload['selectedPart']} uses {summary['modelName']} with {(summary['wape'] * 100):.1f}% WAPE, {(summary['bias'] * 100):+.1f}% bias, {summary['confidence'].lower()} confidence, and {summary['forecastRisk'].lower()} risk."
            )
        else:
            evidence.append(
                f"Forecast focus part {forecast_payload['selectedPart']} is available with {summary['confidence'].lower()} confidence."
            )

    for snippet in retrieved_context[:2]:
        evidence.append(f"Retrieved context [{snippet['source']}]: {snippet['content']}")

    if intent == "forecast" and forecast_payload:
        summary = forecast_payload["summary"]
        change_analysis = forecast_payload.get("changeAnalysis") or {}
        quality_note = (
            f"The backtest WAPE is {(summary['wape'] * 100):.1f}% and bias is {(summary['bias'] * 100):+.1f}% when available, "
            if summary.get("wape") is not None and summary.get("bias") is not None
            else "The backtest diagnostics are incomplete for this slice, "
        )
        answer = (
            f"For the current slice, the most relevant forecast lead is part {forecast_payload['selectedPart']}. "
            f"Next month is projected at {summary['nextForecast']:,.0f} units versus {summary['latestActual']:,.0f} in the latest actual month. "
            f"{quality_note}so this should be read as a {summary['confidence'].lower()}-confidence, {summary['forecastRisk'].lower()}-risk baseline rather than a guaranteed outcome."
        )
        if change_analysis.get("notes"):
            answer += f" The latest demand shift context is: {change_analysis['notes'][0]}"
        return answer, evidence[:5]

    if intent == "change" and top_alert:
        answer = (
            f"The strongest current explanation lead is part {top_alert['part']}"
            f"{f' ({top_alert['partDescription']})' if top_alert.get('partDescription') else ''}. "
            f"It is classified as {top_alert['regime'].lower()} with {top_alert['forecastRisk'].lower()} forecast risk. "
            f"The latest month moved {(top_alert['deltaPct'] or 0):+.1f}% versus the prior month, which is large enough that the product is treating it as a planner-review signal rather than routine noise."
        )
        if top_alert.get("brandDrivers"):
            driver = top_alert["brandDrivers"][0]
            answer += f" Brand contribution is led by {driver['name']} at {driver['delta']:+,.0f} units."
        if top_alert.get("modelDrivers"):
            driver = top_alert["modelDrivers"][0]
            answer += f" Model contribution is led by {driver['name']} at {driver['delta']:+,.0f} units."
        return answer, evidence[:5]

    answer = (
        f"In the current filtered slice, the workspace covers {total_records:,} rows"
        + (f", {total_qty:,.0f} installation units" if total_qty is not None else "")
        + (f", and ${total_revenue:,.0f} revenue" if total_revenue is not None else "")
        + ". "
    )
    if top_alert:
        answer += (
            f"The highest-priority issue to investigate is part {top_alert['part']}, which currently looks {top_alert['regime'].lower()} and carries {top_alert['forecastRisk'].lower()} forecast risk. "
        )
    if forecast_payload:
        answer += (
            f"The current forecast focus part is {forecast_payload['selectedPart']}, where confidence is {forecast_payload['summary']['confidence'].lower()}."
        )
    else:
        answer += "No part-level forecast could be built from the current slice."
    return answer, evidence[:5]


def _ai_gateway_configured() -> bool:
    return bool(os.getenv("PIO_AI_API_KEY") and (os.getenv("PIO_AI_BASE_URL") or os.getenv("LOVABLE_BASE_URL")))


def _maybe_rewrite_with_llm(
    question: str,
    draft_answer: str,
    evidence: list[str],
    used_tools: list[str],
    kpis: dict[str, Any],
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
    retrieved_context: list[dict[str, Any]],
) -> dict[str, str] | None:
    api_key = os.getenv("PIO_AI_API_KEY") or os.getenv("LOVABLE_API_KEY")
    base_url = os.getenv("PIO_AI_BASE_URL") or os.getenv("LOVABLE_BASE_URL") or "https://ai.gateway.lovable.dev"
    model = os.getenv("PIO_AI_MODEL") or os.getenv("LOVABLE_MODEL") or "openai/gpt-5-mini"
    if not api_key:
        return None

    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    endpoint = f"{endpoint}/chat/completions"

    system_prompt = (
        "You are an automotive parts planning analyst. Rewrite the grounded answer clearly and professionally. "
        "Use only the provided facts. Do not invent any values, causes, or dates. If evidence is weak, say so."
    )
    user_prompt = json.dumps(
        {
            "question": question,
            "draft_answer": draft_answer,
            "evidence": evidence,
            "used_tools": used_tools,
            "kpis": kpis,
            "top_alert": anomaly_center.get("records", [])[:1],
            "forecast_summary": forecast_payload.get("summary") if forecast_payload else None,
            "retrieved_context": retrieved_context[:4],
        },
        ensure_ascii=False,
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    request = urllib_request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        answer = payload["choices"][0]["message"]["content"].strip()
        if not answer:
            return None
        return {"answer": answer, "mode": "llm_assisted", "model": model}
    except (TimeoutError, urllib_error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError):
        return None


def _infer_start_year(session: WorkbookSession, exclude_sheet: str | None = None) -> int | None:
    """First calendar year seen in a sibling sheet that has a real date field.

    Used to label the month columns of wide wholesale/fleet matrices (whose own
    year headers are lost during parsing) with real years.
    """
    for candidate in session.sheet_names:
        if exclude_sheet and candidate == exclude_sheet:
            continue
        try:
            other = _get_bundle(session, candidate)
        except Exception:
            continue
        date_col = other.roles.get("date")
        if date_col and date_col in other.date_candidates:
            parsed = other.date_candidates[date_col].dropna()
            if not parsed.empty:
                return int(parsed.min().year)
    return None


def _find_wholesale_bundle(session: WorkbookSession, exclude_sheet: str | None = None) -> DatasetBundle | None:
    for candidate in session.sheet_names:
        if exclude_sheet and candidate == exclude_sheet:
            continue
        if "wholesale" in candidate.lower():
            try:
                return _get_bundle(session, candidate)
            except Exception:
                return None
    return None


def _forecast_sales_sheet_name(session: WorkbookSession, requested_sheet: str) -> str:
    """Resolve Forecast Center to the governed PIO sales source.

    Data Workspace may browse any sheet, but Forecast Center must not reinterpret
    a wholesale, working-days, or legend sheet as the PIO transaction fact.
    """
    for candidate in session.sheet_names:
        if candidate.strip().lower() == "pio_sales_data":
            return candidate

    ordered_candidates = [
        requested_sheet,
        *[candidate for candidate in session.sheet_names if candidate != requested_sheet],
    ]
    for candidate in ordered_candidates:
        try:
            bundle = _get_bundle(session, candidate)
        except Exception:
            continue
        columns = _resolve_eda_sales_columns(bundle)
        date_col = columns.get("date")
        if (
            date_col
            and date_col in bundle.date_candidates
            and columns.get("model")
            and columns.get("quantity")
            and columns.get("revenue")
        ):
            return candidate
    raise ValueError("Forecast Center requires a PIO sales sheet with date, model, quantity, and revenue fields.")


def _all_wholesale_long(session: WorkbookSession, sales_sheet: str) -> pd.DataFrame:
    sales_sheet = _forecast_sales_sheet_name(session, sales_sheet)
    sales_bundle = _get_bundle(session, sales_sheet)
    date_col = sales_bundle.roles.get("date")
    latest_sales_year = None
    if date_col and date_col in sales_bundle.date_candidates:
        parsed = sales_bundle.date_candidates[date_col].dropna()
        if not parsed.empty:
            latest_sales_year = int(parsed.max().year)

    frames: list[pd.DataFrame] = []
    for candidate in session.sheet_names:
        if candidate == sales_sheet or "wholesale" not in candidate.lower():
            continue
        try:
            bundle = _get_bundle(session, candidate)
        except Exception:
            continue
        frame = build_wholesale_long(
            bundle.dataframe,
            candidate,
            latest_sales_year=latest_sales_year,
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=[
                "month", "brand", "anchorBrand", "modelName", "modelKey", "modelCode",
                "wholesaleUnits", "channel", "sourceSheet",
            ]
        )
    combined = pd.concat(frames, ignore_index=True)
    return (
        combined.groupby(["month", "anchorBrand", "modelKey"], as_index=False)
        .agg(
            brand=("brand", lambda values: " / ".join(sorted({str(value) for value in values if str(value)}))),
            modelName=("modelName", "first"),
            modelCode=("modelCode", lambda values: " / ".join(sorted({str(value) for value in values if str(value)}))),
            wholesaleUnits=("wholesaleUnits", "sum"),
            channel=("channel", "first"),
            sourceSheet=("sourceSheet", lambda values: " / ".join(sorted({str(value) for value in values if str(value)}))),
        )
    )


def _working_days_long(session: WorkbookSession, sales_sheet: str) -> pd.DataFrame:
    sales_sheet = _forecast_sales_sheet_name(session, sales_sheet)
    for candidate in session.sheet_names:
        if candidate == sales_sheet:
            continue
        normalized = candidate.lower().replace(" ", "_")
        if "working_day" not in normalized:
            continue
        try:
            return build_working_days_long(_get_bundle(session, candidate).dataframe)
        except Exception:
            return pd.DataFrame(columns=["month", "workingDays"])
    return pd.DataFrame(columns=["month", "workingDays"])


def _get_monthly_fact_table(session: WorkbookSession, sheet_name: str) -> pd.DataFrame:
    sales_sheet = _forecast_sales_sheet_name(session, sheet_name)
    if sales_sheet in session.monthly_facts:
        return session.monthly_facts[sales_sheet]
    bundle = _get_bundle(session, sales_sheet)
    columns = _resolve_eda_sales_columns(bundle)
    date_series = _eda_date_series(bundle, bundle.dataframe, columns["date"])
    lifecycle = build_model_lifecycle(
        bundle.dataframe,
        date_series,
        model_col=columns["model"],
        qty_col=columns["quantity"],
        brand_col=columns["brand"],
        model_code_col=columns["model_code"],
        cutoff_year=2024,
    )
    facts = build_monthly_fact_table(
        bundle.dataframe,
        date_series,
        brand_col=columns["brand"],
        model_col=columns["model"],
        model_code_col=columns["model_code"],
        part_number_col=columns["part_number"],
        part_description_col=columns["part_description"],
        plc_col=columns["plc"],
        qty_col=columns["quantity"],
        revenue_col=columns["revenue"],
        wholesale_long=_all_wholesale_long(session, sales_sheet),
        working_days_long=_working_days_long(session, sales_sheet),
        lifecycle_records=lifecycle["records"],
        start_year=2023,
        end_year=2026,
    )
    session.monthly_facts[sales_sheet] = facts
    return facts


def _latest_sales_month_is_complete(session: WorkbookSession, sheet_name: str) -> bool:
    bundle = _get_bundle(session, _forecast_sales_sheet_name(session, sheet_name))
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return False
    values = bundle.date_candidates[date_col].dropna()
    if values.empty:
        return False
    latest = values.max()
    return bool(latest.normalize() >= (latest + pd.offsets.MonthEnd(0)).normalize())


def _latest_sales_date(session: WorkbookSession, sheet_name: str) -> pd.Timestamp | None:
    bundle = _get_bundle(session, _forecast_sales_sheet_name(session, sheet_name))
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return None
    values = bundle.date_candidates[date_col].dropna()
    return pd.Timestamp(values.max()) if not values.empty else None


def _forecast_cutoff_context(
    session: WorkbookSession,
    sheet_name: str,
    end_date: str = "",
) -> tuple[bool, pd.Timestamp | None]:
    latest_sales_date = _latest_sales_date(session, sheet_name)
    if latest_sales_date is None or not end_date:
        return _latest_sales_month_is_complete(session, sheet_name), latest_sales_date
    try:
        requested_end = pd.Timestamp(end_date)
    except (TypeError, ValueError):
        return _latest_sales_month_is_complete(session, sheet_name), latest_sales_date
    requested_month = requested_end.to_period("M")
    latest_month = latest_sales_date.to_period("M")
    if requested_month < latest_month:
        complete_month_end = requested_month.end_time.normalize()
        return True, complete_month_end
    return _latest_sales_month_is_complete(session, sheet_name), latest_sales_date


def _filter_fact_brand_values(
    facts: pd.DataFrame,
    brand: list[str],
) -> pd.DataFrame:
    if not brand or facts.empty:
        return facts
    governed_anchors = {"HMA", "GMA", "KUS"}
    requested_anchor_values = {value for value in brand if value in governed_anchors}
    requested_source_values = {value for value in brand if value not in governed_anchors}
    fact_mask = pd.Series(False, index=facts.index)
    if requested_anchor_values and "anchorBrand" in facts.columns:
        fact_mask |= facts["anchorBrand"].isin(requested_anchor_values)
    if requested_source_values and "brand" in facts.columns:
        fact_mask |= facts["brand"].isin(requested_source_values)
    return facts[fact_mask]


def _filter_forecast_sources(
    facts: pd.DataFrame,
    wholesale_long: pd.DataFrame,
    *,
    brand: list[str],
    model: list[str],
    part: list[str],
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    filtered_facts = facts.copy()
    filtered_wholesale = wholesale_long.copy()
    if brand:
        governed_anchors = {"HMA", "GMA", "KUS"}
        requested_anchor_values = {value for value in brand if value in governed_anchors}
        filtered_facts = _filter_fact_brand_values(filtered_facts, brand)
        resolved_anchors = set(requested_anchor_values)
        if "anchorBrand" in filtered_facts.columns:
            resolved_anchors.update(
                str(value)
                for value in filtered_facts["anchorBrand"].dropna().unique()
                if str(value) in governed_anchors
            )
        if resolved_anchors and "anchorBrand" in filtered_wholesale.columns:
            filtered_wholesale = filtered_wholesale[
                filtered_wholesale["anchorBrand"].isin(resolved_anchors)
            ]
    if model:
        filtered_facts = filtered_facts[filtered_facts["modelName"].isin(model)]
        filtered_wholesale = filtered_wholesale[filtered_wholesale["modelName"].isin(model)]
    if part:
        filtered_facts = filtered_facts[
            filtered_facts["partNumber"].isin(part) | filtered_facts["plc"].isin(part)
        ]
    if start_date:
        start_month = str(start_date)[:7]
        filtered_facts = filtered_facts[filtered_facts["month"] >= start_month]
        filtered_wholesale = filtered_wholesale[filtered_wholesale["month"] >= start_month]
    if end_date:
        end_month = str(end_date)[:7]
        filtered_facts = filtered_facts[filtered_facts["month"] <= end_month]
        filtered_wholesale = filtered_wholesale[filtered_wholesale["month"] <= end_month]
    return filtered_facts, filtered_wholesale


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in df.to_dict("records"):
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if pd.isna(value):
                clean[key] = None
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        records.append(clean)
    return records


def _build_part_number_options(
    df: pd.DataFrame,
    part_number_col: str,
    qty_col: str,
    description_col: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    working = df.copy()
    working["__part"] = working[part_number_col].fillna("").astype(str)
    working["__qty"] = pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0)
    working = working[working["__part"] != ""]
    if working.empty:
        return []

    grouped = (
        working.groupby("__part", dropna=True)
        .agg(count=("__part", "size"), quantity=("__qty", "sum"))
        .sort_values(by=["quantity", "count"], ascending=False)
        .head(limit)
        .reset_index()
    )

    descriptions: dict[str, str] = {}
    if description_col and description_col in working.columns:
        desc_df = working[[part_number_col, description_col]].dropna().copy()
        if not desc_df.empty:
            desc_df[part_number_col] = desc_df[part_number_col].astype(str)
            descriptions = (
                desc_df.groupby(part_number_col)[description_col]
                .agg(lambda values: values.astype(str).mode().iloc[0])
                .to_dict()
            )

    options = []
    for row in grouped.to_dict("records"):
        part_value = row["__part"]
        description = descriptions.get(part_value)
        label = f"{part_value} · {description}" if description else part_value
        options.append(
            {
                "label": label,
                "value": part_value,
                "description": description,
                "count": int(row["count"]),
                "quantity": float(row["quantity"]),
            }
        )
    return options



def _filter_date_range(bundle: DatasetBundle) -> dict[str, str | None]:
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return {"min": None, "max": None}
    parsed = bundle.date_candidates[date_col].dropna()
    if parsed.empty:
        return {"min": None, "max": None}
    return {
        "min": parsed.min().strftime("%Y-%m-%d"),
        "max": parsed.max().strftime("%Y-%m-%d"),
    }


def _build_value_options(
    series: pd.Series,
    limit: int,
    sort_by_count: bool = True,
) -> list[dict[str, Any]]:
    clean = series.dropna().astype(str)
    clean = clean[clean.str.strip() != ""]
    if clean.empty:
        return []
    counts = clean.value_counts()
    if sort_by_count:
        counts = counts.head(limit)
    else:
        counts = counts.sort_index().head(limit)
    return [
        {"label": value, "value": value, "count": int(count)}
        for value, count in counts.items()
    ]


def _display_series_for_column(bundle: DatasetBundle, column: str) -> pd.Series:
    if (
        column == bundle.roles.get("brand")
        and is_wide_month_matrix(bundle.dataframe, bundle.roles)
    ):
        return wide_brand_series(bundle.dataframe)
    if column == bundle.roles.get("model_year") and column in bundle.date_candidates:
        return bundle.date_candidates[column].dt.year.astype("Int64").astype(str)
    return bundle.dataframe[column].fillna("").astype(str)


def _date_summary(bundle: DatasetBundle, filtered_df: pd.DataFrame) -> str:
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return "No reliable date coverage was detected for this worksheet."
    parsed = bundle.date_candidates[date_col].loc[filtered_df.index].dropna()
    if parsed.empty:
        return "No rows remain inside the current date filters."
    return (
        f"Coverage runs from {parsed.min().strftime('%Y-%m-%d')} to {parsed.max().strftime('%Y-%m-%d')} "
        f"across {parsed.dt.to_period('M').nunique()} active months."
    )


def _dtype_name(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    return "text"


def _serialize_cell(
    value: Any,
    date_fields: list[str],
    column: str,
    parsed_date: Any = None,
    model_year_col: str | None = None,
) -> Any:
    if pd.isna(value):
        return None
    if model_year_col and column == model_year_col:
        if parsed_date is not None and pd.notna(parsed_date):
            return int(pd.to_datetime(parsed_date).year)
        if isinstance(value, (int, float)):
            return int(value)
        return str(value)
    if column in date_fields:
        parsed = pd.to_datetime(parsed_date if parsed_date is not None else value, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)
