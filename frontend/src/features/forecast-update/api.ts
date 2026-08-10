import { OFFICIAL_PROXY_BASE, ForecastRequestError } from "../official-forecast/api";
import type { ForecastUpdateJobEnvelope } from "./contract";

async function updateRequest(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<ForecastUpdateJobEnvelope> {
  const response = await fetch(`${OFFICIAL_PROXY_BASE}/admin/forecast-updates${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "X-Forecast-Update-Token": token,
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    let code = "forecast_update_request_failed";
    let message = "The forecast update request failed.";
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
      // Keep the safe fallback.
    }
    throw new ForecastRequestError(response.status, code, message);
  }
  return response.json() as Promise<ForecastUpdateJobEnvelope>;
}

export async function createForecastUpdate(
  token: string,
  files: Record<"capstone" | "hma_plan" | "gma_plan" | "kia_plan", File>,
) {
  const body = new FormData();
  Object.entries(files).forEach(([role, file]) => body.append(role, file));
  return updateRequest("", token, { method: "POST", body });
}

export async function getForecastUpdate(token: string, jobId: string) {
  return updateRequest(`/${jobId}`, token);
}

export async function runForecastUpdate(token: string, jobId: string) {
  return updateRequest(`/${jobId}/run`, token, { method: "POST" });
}

export async function approveForecastUpdate(token: string, jobId: string) {
  return updateRequest(`/${jobId}/approve`, token, { method: "POST" });
}
