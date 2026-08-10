from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.governed_forecast_client import DATA_ENDPOINTS
from backend.app.governed_forecast_config import (
    GovernedForecastConfig,
    GovernedForecastConfigurationError,
)
from backend.app.governed_forecast_routes import create_governed_forecast_router


SCHEMA_VERSION = "1.2.0"
PROXY_PREFIX = "/api/official-forecast/v1"
RUN_METADATA = {
    "schema_version": SCHEMA_VERSION,
    "run_id": "approved-run-1",
    "approval_status": "approved",
    "registry_version": "2026.07.29.1",
    "generated_at": "2026-07-29T10:00:00Z",
    "published_at": "2026-07-29T11:00:00Z",
    "actual_data_through": "2026-07-22",
    "completed_training_data_through": "2026-06-30",
    "forecast_start": "2026-07-01",
    "forecast_end": "2027-06-01",
    "source_git_commit": "synthetic",
}
UPDATE_JOB = {
    "job_id": "a" * 32,
    "status": "validated",
    "created_at": "2030-01-01T00:00:00Z",
    "updated_at": "2030-01-01T00:00:00Z",
    "files": [
        {
            "role": role,
            "filename": f"synthetic-{role}.xlsx",
            "size_bytes": 10,
            "sha256": "a" * 64,
            "valid": True,
            "summary": "Synthetic role passed.",
            "details": {},
        }
        for role in ("capstone", "hma_plan", "gma_plan", "kia_plan")
    ],
    "progress": {"stage": "validation", "percent": 10, "message": "Validated"},
    "qa": None,
    "draft": None,
    "approved_run_id": None,
    "error": None,
}


def _config() -> GovernedForecastConfig:
    return GovernedForecastConfig(
        base_url="https://forecast.example",
        api_key="server-only-secret",
        timeout_seconds=1.0,
        expected_schema_version=SCHEMA_VERSION,
    )


def _client(handler) -> TestClient:
    application = FastAPI()
    application.include_router(
        create_governed_forecast_router(
            _config(),
            transport=httpx.MockTransport(handler),
        )
    )
    return TestClient(application)


class GovernedForecastConfigurationTests(unittest.TestCase):
    def test_environment_configuration_normalizes_versioned_base_url(self) -> None:
        environment = {
            "GOVERNED_FORECAST_API_URL": "https://forecast.example/root/api/v1/",
            "GOVERNED_FORECAST_API_KEY": " secret ",
            "GOVERNED_FORECAST_API_TIMEOUT_SECONDS": "12.5",
            "GOVERNED_FORECAST_SCHEMA_VERSION": SCHEMA_VERSION,
        }
        with patch.dict("os.environ", environment, clear=True):
            config = GovernedForecastConfig.from_env()

        self.assertEqual(config.base_url, "https://forecast.example/root")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.timeout_seconds, 12.5)

    def test_environment_configuration_rejects_credentials_in_url(self) -> None:
        environment = {
            "GOVERNED_FORECAST_API_URL": "https://user:secret@forecast.example",
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(GovernedForecastConfigurationError):
                GovernedForecastConfig.from_env()


class GovernedForecastProxyTests(unittest.TestCase):
    def test_forecast_update_upload_is_protected_and_streamed_to_private_backend(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.path, "/api/v1/admin/forecast-updates")
            self.assertEqual(
                request.headers.get("x-forecast-update-token"), "synthetic-token"
            )
            self.assertNotIn("x-api-key", request.headers)
            body = request.content
            for role in ("capstone", "hma_plan", "gma_plan", "kia_plan"):
                self.assertIn(role.encode(), body)
                self.assertIn(f"synthetic-{role}.xlsx".encode(), body)
            return httpx.Response(200, json={"job": UPDATE_JOB})

        client = _client(handler)
        files = {
            role: (
                f"synthetic-{role}.xlsx",
                f"synthetic-{role}".encode(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            for role in ("capstone", "hma_plan", "gma_plan", "kia_plan")
        }
        unauthorized = client.post(
            f"{PROXY_PREFIX}/admin/forecast-updates", files=files
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(requests, [])

        response = client.post(
            f"{PROXY_PREFIX}/admin/forecast-updates",
            files=files,
            headers={"X-Forecast-Update-Token": "synthetic-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["status"], "validated")
        self.assertEqual(len(requests), 1)

    def test_top_movers_is_proxied_without_reordering_and_watchlist_is_removed(self) -> None:
        upstream_movers = [
            {"rank": 1, "plc": "PLC-B", "absolute_revenue_change": 900.0},
            {"rank": 2, "plc": "PLC-A", "absolute_revenue_change": 800.0},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/top-movers")
            return httpx.Response(
                200,
                json={
                    "meta": RUN_METADATA,
                    "data": {
                        "status": "available",
                        "default_comparison_id": "next-vs-current",
                        "comparisons": [{"upside": upstream_movers, "downside": []}],
                    },
                },
            )

        client = _client(handler)
        response = client.get(f"{PROXY_PREFIX}/top-movers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["comparisons"][0]["upside"], upstream_movers)
        self.assertEqual(client.get(f"{PROXY_PREFIX}/watchlist").status_code, 404)

    def test_health_is_public_upstream_and_contract_validated(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "pio-governed-forecast-api",
                    "schema_version": SCHEMA_VERSION,
                    "approved_run_available": True,
                    "run_id": "approved-run-1",
                },
            )

        response = _client(handler).get(f"{PROXY_PREFIX}/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(requests[0].url.path, "/api/v1/health")
        self.assertNotIn("x-api-key", requests[0].headers)

    def test_protected_routes_use_server_side_key_and_fixed_allowlist(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"meta": RUN_METADATA, "data": {"source": "approved-run"}},
            )

        client = _client(handler)
        for endpoint in DATA_ENDPOINTS:
            response = client.get(f"{PROXY_PREFIX}/{endpoint}")
            self.assertEqual(response.status_code, 200, endpoint)
            self.assertEqual(response.json()["meta"]["approval_status"], "approved")

        self.assertEqual(
            {request.url.path.removeprefix("/api/v1/") for request in requests},
            set(DATA_ENDPOINTS),
        )
        self.assertTrue(
            all(
                request.headers.get("x-api-key") == "server-only-secret"
                for request in requests
            )
        )
        self.assertEqual(
            client.get(f"{PROXY_PREFIX}/arbitrary-upstream-path").status_code,
            404,
        )

    def test_latest_run_contract_is_validated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/runs/latest")
            return httpx.Response(
                200,
                json={
                    "meta": RUN_METADATA,
                    "available_endpoints": sorted(DATA_ENDPOINTS),
                    "sponsor_workbook_filename": "Sponsor_Forecast.xlsx",
                    "sponsor_workbook_sha256": "a" * 64,
                    "validation": {
                        "release_check_count": 22,
                        "release_checks_passed": 22,
                    },
                },
            )

        response = _client(handler).get(f"{PROXY_PREFIX}/runs/latest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["run_id"], "approved-run-1")

    def test_schema_drift_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "meta": {**RUN_METADATA, "schema_version": "2.0.0"},
                    "data": {},
                },
            )

        response = _client(handler).get(f"{PROXY_PREFIX}/executive-summary")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"]["code"],
            "unsupported_schema_version",
        )

    def test_invalid_contract_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"meta": RUN_METADATA, "unexpected": "field"},
            )

        response = _client(handler).get(f"{PROXY_PREFIX}/revenue")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"]["code"],
            "governed_forecast_contract_error",
        )

    def test_timeout_and_authorization_errors_are_safely_mapped(self) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("upstream detail", request=request)

        timeout_response = _client(timeout_handler).get(
            f"{PROXY_PREFIX}/executive-summary"
        )
        self.assertEqual(timeout_response.status_code, 504)
        self.assertEqual(
            timeout_response.json()["detail"]["code"],
            "governed_forecast_timeout",
        )
        self.assertNotIn("upstream detail", timeout_response.text)

        def unauthorized_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "private upstream detail"})

        unauthorized_response = _client(unauthorized_handler).get(
            f"{PROXY_PREFIX}/revenue"
        )
        self.assertEqual(unauthorized_response.status_code, 401)
        self.assertEqual(
            unauthorized_response.json()["detail"]["code"],
            "governed_forecast_unauthorized",
        )
        self.assertNotIn("private upstream detail", unauthorized_response.text)

    def test_upstream_redirect_is_not_followed_or_forwarded(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                302,
                headers={"location": "https://unapproved.example/data"},
            )

        response = _client(handler).get(f"{PROXY_PREFIX}/executive-summary")

        self.assertEqual(len(requests), 1)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"]["code"],
            "governed_forecast_upstream_error",
        )
        self.assertNotIn("location", response.headers)

    def test_workbook_download_streams_approved_bytes_and_safe_headers(self) -> None:
        workbook_bytes = b"synthetic-approved-workbook"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/api/v1/downloads/sponsor-workbook",
            )
            self.assertEqual(
                request.headers.get("x-api-key"),
                "server-only-secret",
            )
            return httpx.Response(
                200,
                content=workbook_bytes,
                headers={
                    "content-type": (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    "content-disposition": (
                        'attachment; filename="Sponsor_Forecast.xlsx"'
                    ),
                    "etag": '"approved-hash"',
                    "x-private-upstream-header": "do-not-forward",
                },
            )

        response = _client(handler).get(
            f"{PROXY_PREFIX}/downloads/sponsor-workbook"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, workbook_bytes)
        self.assertIn("Sponsor_Forecast.xlsx", response.headers["content-disposition"])
        self.assertEqual(response.headers["etag"], '"approved-hash"')
        self.assertNotIn("x-private-upstream-header", response.headers)

    def test_missing_configuration_returns_safe_503(self) -> None:
        application = FastAPI()
        application.include_router(create_governed_forecast_router())

        with patch.dict("os.environ", {}, clear=True):
            response = TestClient(application).get(f"{PROXY_PREFIX}/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"]["code"],
            "governed_forecast_not_configured",
        )


if __name__ == "__main__":
    unittest.main()
