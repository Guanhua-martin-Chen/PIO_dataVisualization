from __future__ import annotations

from typing import Any, Callable

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.app.governed_forecast_client import (
    DATA_ENDPOINTS,
    GovernedForecastClient,
    GovernedForecastProxyError,
)
from backend.app.governed_forecast_config import (
    GovernedForecastConfig,
    GovernedForecastConfigurationError,
)


def create_governed_forecast_router(
    config: GovernedForecastConfig | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/official-forecast/v1",
        tags=["Official Forecast"],
    )

    def client() -> GovernedForecastClient:
        try:
            resolved_config = config or GovernedForecastConfig.from_env()
        except GovernedForecastConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "governed_forecast_not_configured",
                    "message": "The governed Forecast API proxy is not configured.",
                },
            ) from exc
        return GovernedForecastClient(resolved_config, transport=transport)

    def execute(action: Callable[[GovernedForecastClient], dict[str, Any]]) -> dict[str, Any]:
        try:
            return action(client())
        except GovernedForecastProxyError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc

    def execute_update(
        token: str | None,
        action: Callable[[GovernedForecastClient, str], dict[str, Any]],
    ) -> dict[str, Any]:
        if not token:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "forecast_update_unauthorized",
                    "message": "Enter the protected operator access code.",
                },
            )
        try:
            return action(client(), token)
        except GovernedForecastProxyError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc

    @router.get("/health")
    def health() -> dict[str, Any]:
        return execute(lambda proxy: proxy.health())

    @router.get("/runs/latest")
    def latest_run() -> dict[str, Any]:
        return execute(lambda proxy: proxy.latest_run())

    def endpoint_handler(endpoint_name: str) -> Callable[[], dict[str, Any]]:
        def handler() -> dict[str, Any]:
            return execute(lambda proxy: proxy.endpoint(endpoint_name))

        return handler

    for endpoint_name in sorted(DATA_ENDPOINTS):
        router.add_api_route(
            f"/{endpoint_name}",
            endpoint_handler(endpoint_name),
            methods=["GET"],
            name=f"official_forecast_{endpoint_name.replace('-', '_')}",
        )

    @router.get("/downloads/sponsor-workbook")
    def sponsor_workbook() -> StreamingResponse:
        try:
            download = client().sponsor_workbook()
        except GovernedForecastProxyError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        return StreamingResponse(
            download.iter_bytes(),
            media_type=download.content_type,
            headers=download.safe_headers,
        )

    @router.get("/admin/forecast-updates")
    def list_forecast_updates(
        x_forecast_update_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return execute_update(
            x_forecast_update_token,
            lambda proxy, token: proxy.list_forecast_updates(token=token),
        )

    @router.post("/admin/forecast-updates")
    def create_forecast_update(
        capstone: UploadFile = File(...),
        hma_plan: UploadFile = File(...),
        gma_plan: UploadFile = File(...),
        kia_plan: UploadFile = File(...),
        x_forecast_update_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        files = {
            "capstone": (
                capstone.filename or "capstone.xlsx",
                capstone.file,
                capstone.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "hma_plan": (
                hma_plan.filename or "hma_plan.xlsx",
                hma_plan.file,
                hma_plan.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "gma_plan": (
                gma_plan.filename or "gma_plan.xlsx",
                gma_plan.file,
                gma_plan.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "kia_plan": (
                kia_plan.filename or "kia_plan.xlsx",
                kia_plan.file,
                kia_plan.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        }
        return execute_update(
            x_forecast_update_token,
            lambda proxy, token: proxy.create_forecast_update(token=token, files=files),
        )

    @router.get("/admin/forecast-updates/{job_id}")
    def get_forecast_update(
        job_id: str,
        x_forecast_update_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return execute_update(
            x_forecast_update_token,
            lambda proxy, token: proxy.forecast_update(job_id, token=token),
        )

    @router.post("/admin/forecast-updates/{job_id}/run")
    def run_forecast_update(
        job_id: str,
        x_forecast_update_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return execute_update(
            x_forecast_update_token,
            lambda proxy, token: proxy.run_forecast_update(job_id, token=token),
        )

    @router.post("/admin/forecast-updates/{job_id}/approve")
    def approve_forecast_update(
        job_id: str,
        x_forecast_update_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return execute_update(
            x_forecast_update_token,
            lambda proxy, token: proxy.approve_forecast_update(job_id, token=token),
        )

    return router
