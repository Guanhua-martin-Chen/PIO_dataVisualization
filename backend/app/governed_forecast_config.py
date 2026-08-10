from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class GovernedForecastConfigurationError(ValueError):
    """Raised when the server-side Forecast API configuration is unusable."""


@dataclass(frozen=True)
class GovernedForecastConfig:
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 10.0
    expected_schema_version: str = "1.2.0"

    @classmethod
    def from_env(cls) -> "GovernedForecastConfig":
        raw_url = os.getenv("GOVERNED_FORECAST_API_URL", "").strip()
        if not raw_url:
            raise GovernedForecastConfigurationError(
                "GOVERNED_FORECAST_API_URL is not configured."
            )

        raw_timeout = os.getenv(
            "GOVERNED_FORECAST_API_TIMEOUT_SECONDS", "10"
        ).strip()
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError as exc:
            raise GovernedForecastConfigurationError(
                "GOVERNED_FORECAST_API_TIMEOUT_SECONDS must be numeric."
            ) from exc
        if not 0 < timeout_seconds <= 120:
            raise GovernedForecastConfigurationError(
                "GOVERNED_FORECAST_API_TIMEOUT_SECONDS must be greater than 0 and at most 120."
            )

        expected_schema_version = os.getenv(
            "GOVERNED_FORECAST_SCHEMA_VERSION", "1.2.0"
        ).strip()
        if not expected_schema_version:
            raise GovernedForecastConfigurationError(
                "GOVERNED_FORECAST_SCHEMA_VERSION must not be empty."
            )

        return cls(
            base_url=_normalize_base_url(raw_url),
            api_key=os.getenv("GOVERNED_FORECAST_API_KEY", "").strip(),
            timeout_seconds=timeout_seconds,
            expected_schema_version=expected_schema_version,
        )


def _normalize_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GovernedForecastConfigurationError(
            "GOVERNED_FORECAST_API_URL must be an absolute http(s) URL."
        )
    if parsed.username or parsed.password:
        raise GovernedForecastConfigurationError(
            "GOVERNED_FORECAST_API_URL must not contain credentials."
        )
    if parsed.query or parsed.fragment:
        raise GovernedForecastConfigurationError(
            "GOVERNED_FORECAST_API_URL must not contain a query or fragment."
        )

    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[: -len("/api/v1")]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")
