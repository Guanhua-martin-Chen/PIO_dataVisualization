from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.governed_forecast_config import GovernedForecastConfig
from backend.app.governed_forecast_contracts import (
    GovernedEndpointEnvelope,
    GovernedHealthResponse,
    GovernedRunSummaryResponse,
)


TContract = TypeVar("TContract", bound=BaseModel)

DATA_ENDPOINTS = frozenset(
    {
        "executive-summary",
        "revenue",
        "quantity",
        "plc-planning",
        "wholesale-drivers",
        "model-performance",
        "top-movers",
        "qa",
    }
)


class GovernedForecastProxyError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class GovernedForecastDownload:
    response: httpx.Response
    client: httpx.Client

    def iter_bytes(self) -> Iterator[bytes]:
        try:
            yield from self.response.iter_bytes()
        finally:
            self.response.close()
            self.client.close()

    @property
    def content_type(self) -> str:
        return self.response.headers.get(
            "content-type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @property
    def safe_headers(self) -> dict[str, str]:
        allowed = {"content-disposition", "content-length", "etag", "last-modified"}
        return {
            name: value
            for name, value in self.response.headers.items()
            if name.lower() in allowed
        }


class GovernedForecastClient:
    def __init__(
        self,
        config: GovernedForecastConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    def health(self) -> dict[str, Any]:
        return self._get_json(
            "/api/v1/health",
            GovernedHealthResponse,
            protected=False,
        )

    def latest_run(self) -> dict[str, Any]:
        return self._get_json(
            "/api/v1/runs/latest",
            GovernedRunSummaryResponse,
            protected=True,
        )

    def endpoint(self, endpoint_name: str) -> dict[str, Any]:
        if endpoint_name not in DATA_ENDPOINTS:
            raise ValueError(f"Unsupported governed endpoint: {endpoint_name}")
        return self._get_json(
            f"/api/v1/{endpoint_name}",
            GovernedEndpointEnvelope,
            protected=True,
        )

    def sponsor_workbook(self) -> GovernedForecastDownload:
        client = self._new_http_client()
        request = client.build_request(
            "GET",
            self._url("/api/v1/downloads/sponsor-workbook"),
            headers=self._headers(protected=True),
        )
        try:
            response = client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            client.close()
            raise GovernedForecastProxyError(
                504,
                "governed_forecast_timeout",
                "The governed Forecast API timed out.",
            ) from exc
        except httpx.RequestError as exc:
            client.close()
            raise GovernedForecastProxyError(
                502,
                "governed_forecast_unavailable",
                "The governed Forecast API is unavailable.",
            ) from exc

        if not response.is_success:
            response.read()
            response.close()
            client.close()
            raise _upstream_http_error(response.status_code)
        return GovernedForecastDownload(response=response, client=client)

    def _get_json(
        self,
        path: str,
        contract: type[TContract],
        *,
        protected: bool,
    ) -> dict[str, Any]:
        try:
            with self._new_http_client() as client:
                response = client.get(
                    self._url(path),
                    headers=self._headers(protected=protected),
                )
        except httpx.TimeoutException as exc:
            raise GovernedForecastProxyError(
                504,
                "governed_forecast_timeout",
                "The governed Forecast API timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise GovernedForecastProxyError(
                502,
                "governed_forecast_unavailable",
                "The governed Forecast API is unavailable.",
            ) from exc

        if not response.is_success:
            raise _upstream_http_error(response.status_code)
        try:
            raw_payload = response.json()
        except ValueError as exc:
            raise GovernedForecastProxyError(
                502,
                "governed_forecast_invalid_json",
                "The governed Forecast API returned invalid JSON.",
            ) from exc

        try:
            payload = contract.model_validate(raw_payload)
        except ValidationError as exc:
            raise GovernedForecastProxyError(
                502,
                "governed_forecast_contract_error",
                "The governed Forecast API response does not match the supported contract.",
            ) from exc

        schema_version = (
            payload.schema_version
            if isinstance(payload, GovernedHealthResponse)
            else payload.meta.schema_version
        )
        if schema_version != self.config.expected_schema_version:
            raise GovernedForecastProxyError(
                502,
                "unsupported_schema_version",
                "The governed Forecast API schema version is not supported.",
            )
        return payload.model_dump(mode="json")

    def _new_http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self.config.timeout_seconds),
            transport=self.transport,
            follow_redirects=False,
        )

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}{path}"

    def _headers(self, *, protected: bool) -> dict[str, str]:
        if protected and self.config.api_key:
            return {"X-API-Key": self.config.api_key}
        return {}


def _upstream_http_error(status_code: int) -> GovernedForecastProxyError:
    if status_code in {401, 403}:
        return GovernedForecastProxyError(
            status_code,
            "governed_forecast_unauthorized",
            "The website proxy is not authorized to access the governed Forecast API.",
        )
    if status_code == 404:
        return GovernedForecastProxyError(
            404,
            "governed_forecast_not_found",
            "The requested governed Forecast API resource was not found.",
        )
    if status_code == 503:
        return GovernedForecastProxyError(
            503,
            "governed_forecast_no_approved_run",
            "No approved governed forecast run is currently available.",
        )
    return GovernedForecastProxyError(
        502,
        "governed_forecast_upstream_error",
        "The governed Forecast API request failed.",
    )
