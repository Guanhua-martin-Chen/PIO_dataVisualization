import type { EChartsOption } from "echarts";

export const BRAND_COLORS = {
  HMA: "#002C5F",
  KUS: "#8C1D40",
  GMA: "#4B5563",
} as const;

const gridColor = "#e7edf4";
const amber = "#c58a25";

function compact(value: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function currency(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  return `$${compact(value)}`;
}

function exactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function shortMonth(value: string) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value.slice(0, 7);
  return new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" }).format(date);
}

function periodTick(month: string, periodType: string) {
  const label = periodType === "actual" ? "Actual" : periodType === "nowcast" ? "Nowcast" : "Forecast";
  return `${shortMonth(month)}\n${label}`;
}

function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>\"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '\"': "&quot;",
  }[character] ?? character));
}

const base: EChartsOption = {
  animationDuration: 450,
  textStyle: { color: "#52647a", fontFamily: "IBM Plex Sans, sans-serif" },
  tooltip: { trigger: "axis", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" } },
};

export function sponsorBrandRevenueTrendOption(
  points: Array<{
    month: string;
    totalValue: number;
    periodType: "actual" | "nowcast" | "forecast";
    brandValues: Record<"HMA" | "GMA" | "KUS", number | null>;
  }>,
  range?: { month: string; low: number; high: number },
): EChartsOption {
  const labels = points.map((point) => periodTick(point.month, point.periodType));
  const nowcastIndex = points.findIndex((point) => point.periodType === "nowcast");
  const forecastIndex = points.findIndex((point) => point.periodType === "forecast");
  const tooltip = (params: unknown) => {
    const items = Array.isArray(params) ? params as Array<{ dataIndex?: number }> : [];
    const index = items.find((item) => typeof item.dataIndex === "number")?.dataIndex;
    const point = typeof index === "number" ? points[index] : undefined;
    if (!point) return "";
    const brandDetail = (["HMA", "KUS", "GMA"] as const)
      .map((brand) => `<br/>${brand}: ${point.brandValues[brand] === null ? "Not available" : exactCurrency(point.brandValues[brand] as number)}`)
      .join("");
    const rangeDetail = range && point.month === range.month
      ? `<br/>Expected range: ${exactCurrency(range.low)} - ${exactCurrency(range.high)}`
      : "";
    return `<strong>${escapeHtml(shortMonth(point.month))} ${escapeHtml(point.periodType)}</strong><br/>Official Total: ${exactCurrency(point.totalValue)}${brandDetail}${rangeDetail}`;
  };
  const periodAreas: any[] = [
    ...(nowcastIndex > 0 ? [[
      { xAxis: labels[0], itemStyle: { color: "rgba(0,44,95,0.025)" } },
      { xAxis: labels[nowcastIndex - 1] },
    ]] : []),
    ...(nowcastIndex >= 0 ? [[
      { xAxis: labels[nowcastIndex], itemStyle: { color: "rgba(197,138,37,0.08)" } },
      { xAxis: labels[nowcastIndex] },
    ]] : []),
    ...(forecastIndex >= 0 ? [[
      { xAxis: labels[forecastIndex], itemStyle: { color: "rgba(59,120,219,0.045)" } },
      { xAxis: labels[labels.length - 1] },
    ]] : []),
  ];

  return {
    ...base,
    color: [BRAND_COLORS.HMA, BRAND_COLORS.KUS, BRAND_COLORS.GMA],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" }, formatter: tooltip },
    legend: { data: ["HMA", "KUS", "GMA"], top: 0, right: 8, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 62, right: 20, top: 42, bottom: 48 },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#cbd6e3" } },
      axisLabel: { color: "#65758a", lineHeight: 14, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: (["HMA", "KUS", "GMA"] as const).map((brand, brandIndex) => ({
      name: brand,
      type: "bar" as const,
      stack: "brandRevenue",
      z: 2,
      barMaxWidth: 46,
      itemStyle: {
        color: BRAND_COLORS[brand],
        borderRadius: brand === "GMA" ? [4, 4, 0, 0] : 0,
      },
      data: points.map((point) => ({
        value: point.brandValues[brand],
        label: brand === "GMA" ? {
          show: true,
          position: "top",
          distance: 5,
          formatter: currency(point.totalValue),
          color: "#102139",
          fontSize: 10,
          fontWeight: 700,
          textBorderColor: "#fff",
          textBorderWidth: 3,
        } : { show: false },
      })),
      ...(brandIndex === 0 ? { markArea: { silent: true, label: { show: false }, data: periodAreas } } : {}),
    })),
  };
}

export function regularWholesaleWeightOption(rows: Array<{ brand: "HMA" | "GMA" | "KUS"; wholesale: number | null }>): EChartsOption {
  const available = rows.filter((row): row is { brand: "HMA" | "GMA" | "KUS"; wholesale: number } => row.wholesale !== null);
  const total = available.reduce((sum, row) => sum + row.wholesale, 0);
  const ordered = ["HMA", "KUS", "GMA"] as const;
  return {
    ...base,
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const item = params as { data?: { brand?: string; value?: number; share?: number } };
        const datum = item.data;
        if (!datum || typeof datum.value !== "number") return "";
        return `<strong>${escapeHtml(datum.brand)}</strong><br/>Regular Wholesale: ${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(datum.value)} vehicles<br/>Volume share: ${typeof datum.share === "number" ? `${(datum.share * 100).toFixed(1)}%` : "N/A"}`;
      },
    },
    grid: { left: 78, right: 82, top: 18, bottom: 28 },
    xAxis: { type: "value", axisLabel: { formatter: compact, color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    yAxis: { type: "category", data: ordered, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#52647a", fontWeight: 700 } },
    series: [{
      type: "bar",
      barMaxWidth: 28,
      data: ordered.map((brand) => {
        const row = rows.find((item) => item.brand === brand);
        const value = row?.wholesale ?? 0;
        const share = total > 0 ? value / total : 0;
        return {
          brand,
          value,
          share,
          itemStyle: { color: BRAND_COLORS[brand], borderRadius: [0, 5, 5, 0] },
          label: {
            show: true,
            position: "right",
            distance: 7,
            formatter: `${compact(value)} · ${(share * 100).toFixed(1)}%`,
            color: "#334860",
            fontSize: 10,
            fontWeight: 700,
          },
        };
      }),
    }],
  };
}
