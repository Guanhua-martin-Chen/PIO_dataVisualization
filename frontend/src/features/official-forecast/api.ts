import { API_BASE_URL } from "../../app/shared";

export const OFFICIAL_PROXY_BASE = `${API_BASE_URL}/api/official-forecast/v1`;

export class ForecastRequestError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ForecastRequestError";
    this.code = code;
    this.status = status;
  }
}

export async function governedFetch<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(`${OFFICIAL_PROXY_BASE}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let code = "governed_forecast_request_failed";
    let message = "The approved forecast could not be loaded.";
    try {
      const payload = await response.json() as {
        detail?: { code?: string; message?: string } | string;
      };
      if (typeof payload.detail === "string") message = payload.detail;
      if (payload.detail && typeof payload.detail === "object") {
        code = payload.detail.code ?? code;
        message = payload.detail.message ?? message;
      }
    } catch {
      // Keep the safe, user-facing fallback above.
    }
    throw new ForecastRequestError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}

export function officialErrorContent(error: ForecastRequestError) {
  if (error.code === "governed_forecast_not_configured") {
    return {
      title: "Official Forecast connection is not configured",
      detail: "The website backend needs its governed API URL and server-side key before this page can load.",
    };
  }
  if (error.code === "governed_forecast_no_approved_run") {
    return {
      title: "No approved forecast run is available",
      detail: "The previous approved view is not replaced by local or experimental forecast values.",
    };
  }
  if (error.code === "governed_forecast_unauthorized") {
    return {
      title: "Official Forecast authorization failed",
      detail: "A server administrator must verify the governed API credential. No key is stored in the browser.",
    };
  }
  if (error.code === "unsupported_schema_version") {
    return {
      title: "Forecast contract version is not supported",
      detail: "The dashboard stopped safely instead of interpreting an unknown response shape.",
    };
  }
  if (
    error.code === "governed_forecast_timeout"
    || error.code === "governed_forecast_unavailable"
  ) {
    return {
      title: "Official Forecast service is temporarily unavailable",
      detail: "Try again shortly. This page will not substitute results from the legacy website forecast engine.",
    };
  }
  return {
    title: "Official Forecast could not be loaded",
    detail: error.message,
  };
}
