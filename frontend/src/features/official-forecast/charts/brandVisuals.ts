import type { EChartsOption } from "echarts";

export const BRAND_COLORS = {
  HMA: "#0057B8",
  KUS: "#D33F49",
  GMA: "#495464",
} as const;

export const FLEET_COLOR = "#D79A24";

const gridColor = "#e7edf4";

type Brand = keyof typeof BRAND_COLORS;

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

function signedCurrency(value: number) {
  return `${value >= 0 ? "+" : "−"}${currency(Math.abs(value))}`;
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
      { xAxis: labels[0], itemStyle: { color: "rgba(0,87,184,0.012)" } },
      { xAxis: labels[nowcastIndex - 1] },
    ]] : []),
    ...(nowcastIndex >= 0 ? [[
      { xAxis: labels[nowcastIndex], itemStyle: { color: "rgba(215,154,36,0.055)" } },
      { xAxis: labels[nowcastIndex] },
    ]] : []),
    ...(forecastIndex >= 0 ? [[
      { xAxis: labels[forecastIndex], itemStyle: { color: "rgba(0,87,184,0.025)" } },
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
      barMaxWidth: 42,
      itemStyle: {
        color: BRAND_COLORS[brand],
        borderColor: "rgba(255,255,255,.92)",
        borderWidth: 1,
        borderRadius: brand === "GMA" ? [4, 4, 0, 0] : 0,
      },
      data: points.map((point) => ({
        value: point.brandValues[brand],
        label: brand === "GMA" ? {
          show: true,
          position: "top",
          distance: 6,
          formatter: currency(point.totalValue),
          color: "#263a52",
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

export function sponsorPnvwBarOption(points: Array<{ month: string; periodType: "actual" | "nowcast"; brand: string; value: number; numerator: number | null; denominator: number | null }>): EChartsOption {
  const months = [...new Set(points.map((point) => point.month))].sort();
  const brands = (["HMA", "KUS", "GMA"] as const).filter((brand) => points.some((point) => point.brand === brand));
  return {
    ...base,
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const item = params as { data?: { month?: string; periodType?: string; brand?: string; value?: number; numerator?: number | null; denominator?: number | null } };
        const datum = item.data;
        if (!datum || typeof datum.value !== "number") return "";
        return `<strong>${escapeHtml(datum.brand)} · ${escapeHtml(shortMonth(datum.month ?? ""))} ${datum.periodType === "nowcast" ? "Nowcast" : "Actual"}</strong><br/>Regular PNVW: ${exactCurrency(datum.value)} / vehicle<br/>Regular PIO Revenue: ${datum.numerator === null || datum.numerator === undefined ? "Not available" : exactCurrency(datum.numerator)}<br/>Regular Wholesale: ${datum.denominator === null || datum.denominator === undefined ? "Not available" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(datum.denominator)} vehicles`;
      },
    },
    legend: { top: 0, right: 4, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 55, right: 22, top: 35, bottom: 38 },
    xAxis: {
      type: "category",
      data: months.map((month) => {
        const periodType = points.find((point) => point.month === month)?.periodType;
        return `${shortMonth(month)}\n${periodType === "nowcast" ? "Nowcast" : "Actual"}`;
      }),
      axisLabel: { color: "#65758a", fontSize: 10, lineHeight: 14, interval: 0 },
      axisLine: { lineStyle: { color: "#cbd6e3" } },
    },
    yAxis: {
      type: "value",
      min: 0,
      name: "USD / vehicle",
      nameTextStyle: { color: "#718095", fontSize: 9 },
      axisLabel: { formatter: (value: number) => `$${compact(value)}`, color: "#65758a", fontSize: 9 },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: brands.map((brand) => ({
      name: brand,
      type: "bar",
      itemStyle: { color: BRAND_COLORS[brand], borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 28,
      data: months.map((month) => {
        const point = points.find((item) => item.month === month && item.brand === brand);
        return point ? {
          value: point.value,
          month: point.month,
          periodType: point.periodType,
          brand: point.brand,
          numerator: point.numerator,
          denominator: point.denominator,
          label: {
            show: true,
            position: "top",
            distance: 4,
            formatter: `$${Math.round(point.value)}`,
            color: "#334860",
            fontSize: 9,
            fontWeight: 700,
          },
        } : null;
      }),
    })),
  };
}

export function sponsorBrandDonutOption(rows: Array<{ name: string; value: number }>): EChartsOption {
  return {
    ...base,
    tooltip: { trigger: "item", valueFormatter: (value: unknown) => typeof value === "number" ? currency(value) : String(value ?? "") },
    legend: { bottom: 0, textStyle: { color: "#65758a" } },
    color: [BRAND_COLORS.HMA, BRAND_COLORS.KUS, BRAND_COLORS.GMA],
    series: [{
      type: "pie",
      radius: ["46%", "68%"],
      center: ["50%", "43%"],
      avoidLabelOverlap: true,
      label: {
        formatter: (params: { name?: string; value?: unknown; percent?: number }) => {
          const value = typeof params.value === "number" ? currency(params.value) : "";
          const percent = typeof params.percent === "number" ? `${params.percent.toFixed(1)}%` : "";
          return `${params.name ?? ""}\n${value}${value && percent ? " · " : ""}${percent}`;
        },
        color: "#334860",
        fontSize: 10,
        lineHeight: 14,
        fontWeight: 650,
      },
      labelLine: { length: 10, length2: 8 },
      data: (["HMA", "KUS", "GMA"] as const).flatMap((brand) => {
        const row = rows.find((item) => item.name === brand);
        return row ? [{ ...row, itemStyle: { color: BRAND_COLORS[brand] } }] : [];
      }),
    }],
  };
}

export function regularWholesaleWeightOption(rows: Array<{ brand: Brand; wholesale: number | null }>): EChartsOption {
  const available = rows.filter((row): row is { brand: Brand; wholesale: number } => row.wholesale !== null);
  const total = available.reduce((sum, row) => sum + row.wholesale, 0);
  const displayOrder: Brand[] = ["GMA", "KUS", "HMA"];
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
    yAxis: { type: "category", data: displayOrder, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#52647a", fontWeight: 700 } },
    series: [{
      type: "bar",
      barMaxWidth: 26,
      data: displayOrder.map((brand) => {
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

export function sponsorBrandMovementOption(rows: Array<{ brand: Brand; value: number }>): EChartsOption {
  const displayOrder: Brand[] = ["GMA", "KUS", "HMA"];
  return {
    ...base,
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const item = params as { data?: { brand?: string; value?: number } };
        const datum = item.data;
        if (!datum || typeof datum.value !== "number") return "";
        return `<strong>${escapeHtml(datum.brand)}</strong><br/>Revenue change: ${exactCurrency(datum.value)}`;
      },
    },
    grid: { left: 88, right: 88, top: 18, bottom: 32 },
    xAxis: { type: "value", axisLabel: { formatter: currency, color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    yAxis: { type: "category", data: displayOrder, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#52647a", fontWeight: 700 } },
    series: [{
      type: "bar",
      barMaxWidth: 26,
      data: displayOrder.map((brand) => {
        const value = rows.find((row) => row.brand === brand)?.value ?? 0;
        return {
          brand,
          value,
          itemStyle: {
            color: BRAND_COLORS[brand],
            borderRadius: value >= 0 ? [0, 5, 5, 0] : [5, 0, 0, 5],
          },
          label: {
            show: true,
            position: value >= 0 ? "right" : "left",
            distance: 7,
            formatter: signedCurrency(value),
            color: "#334860",
            fontSize: 10,
            fontWeight: 700,
          },
        };
      }),
    }],
  };
}

export function sponsorQuantityDecompositionOption(rows: Array<{
  brand: Brand;
  regular: number | null;
  fleet: number | null;
}>): EChartsOption {
  const brandOrder: Brand[] = ["HMA", "KUS", "GMA"];
  const regularSeries = brandOrder.map((brand) => ({
    name: brand,
    type: "bar" as const,
    stack: "quantity",
    barMaxWidth: 42,
    itemStyle: { color: BRAND_COLORS[brand] },
    data: brandOrder.map((category) => {
      if (category !== brand) return null;
      const value = rows.find((row) => row.brand === brand)?.regular ?? null;
      return value === null ? null : {
        value,
        label: {
          show: true,
          position: "inside" as const,
          formatter: compact(value),
          color: "#fff",
          fontSize: 9,
          fontWeight: 700,
        },
      };
    }),
  }));
  const fleetSeries = {
    name: "Kia Fleet",
    type: "bar" as const,
    stack: "quantity",
    barMaxWidth: 42,
    itemStyle: { color: FLEET_COLOR, borderRadius: [4, 4, 0, 0] },
    data: brandOrder.map((brand) => {
      const value = brand === "KUS" ? rows.find((row) => row.brand === brand)?.fleet ?? null : null;
      return value === null || value === 0 ? null : {
        value,
        label: {
          show: true,
          position: "inside" as const,
          formatter: compact(value),
          color: "#fff",
          fontSize: 9,
          fontWeight: 700,
        },
      };
    }),
  };

  return {
    ...base,
    legend: {
      data: ["HMA", "KUS", "GMA", "Kia Fleet"],
      bottom: 0,
      selectedMode: false,
      textStyle: { color: "#65758a", fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    grid: { left: 68, right: 28, top: 28, bottom: 58 },
    xAxis: {
      type: "category",
      data: brandOrder,
      axisLabel: { color: "#52647a", fontWeight: 700 },
      axisLine: { lineStyle: { color: "#cbd6e3" } },
    },
    yAxis: {
      type: "value",
      name: "accessory units",
      nameTextStyle: { color: "#718095", fontSize: 9 },
      axisLabel: { formatter: compact, color: "#65758a" },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: [...regularSeries, fleetSeries],
  };
}
