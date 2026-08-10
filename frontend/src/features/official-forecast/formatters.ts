export function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const numeric = finite(value);
    if (numeric !== null) return numeric;
  }
  return null;
}

export function compactCurrency(value: unknown) {
  const numeric = finite(value);
  if (numeric === null) return "Not provided";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(numeric);
}

export function exactCurrency(value: unknown) {
  const numeric = finite(value);
  if (numeric === null) return "Not provided";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(numeric);
}

export function formatNumber(value: unknown, compact = false) {
  const numeric = finite(value);
  if (numeric === null) return "Not provided";
  return new Intl.NumberFormat("en-US", {
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 0,
  }).format(numeric);
}

export function formatPercent(value: unknown, digits = 1) {
  const numeric = finite(value);
  if (numeric === null) return "Not provided";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numeric);
}

export function formatText(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function wholesaleSourceLabel(value: unknown) {
  if (value === "sponsor_plan_official") return "Sponsor plan";
  if (value === "internal_forecast_fallback") return "Governed fallback";
  if (typeof value === "string" && value.includes("sponsor_plan_official") && value.includes("internal_forecast_fallback")) {
    return "Sponsor plan + governed fallback";
  }
  return formatText(value);
}

export function revenueSourceLabel(value: unknown) {
  if (value === "frozen_brand_registry_pooled_model_month_to_brand" || value === "frozen_brand_registry_working_day_adjusted_seasonal") {
    return "Governed brand selection";
  }
  if (value === "selected_bottom_up_model") return "Selected model plan";
  return typeof value === "string" ? value.replaceAll("_", " ") : formatText(value);
}

const plcMethodLabels: Record<string, string> = {
  previous_month_share: "Previous-month PLC share",
  historical_mix_fallback: "Historical mix fallback",
  annual_average_share: "Annual average share",
  selected_method: "Selected method",
};

export function plcMethodLabel(value: unknown) {
  if (typeof value !== "string" || value === "") return "Not available";
  return plcMethodLabels[value] ?? value
    .split("_")
    .filter(Boolean)
    .map((part, index) => index === 0 ? `${part.charAt(0).toUpperCase()}${part.slice(1)}` : part)
    .join(" ");
}

export function forecastComponentLabel(value: unknown) {
  if (value === "regular") return "Regular";
  if (value === "kia_fleet_cfm_adjustment") return "Kia Fleet CFM adjustment";
  if (typeof value !== "string" || value === "") return "Not available";
  return value.split("_").filter(Boolean).join(" ");
}

export function monthLabel(value: string, short = false) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: short ? "short" : "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function dateLabel(value: string) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function timestampLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
