from __future__ import annotations

from typing import Any, Callable

import httpx
from fastapi import APIRouter, HTTPException
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

    return router
