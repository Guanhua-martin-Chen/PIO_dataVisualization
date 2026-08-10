import type { EChartsOption } from "echarts";

const navy = "#174795";
const blue = "#3b78db";
const paleBlue = "#9fc2f4";
const green = "#23824b";
const amber = "#c58a25";
const red = "#b94a51";
const gridColor = "#e7edf4";

function compact(value: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function currency(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  return `$${compact(value)}`;
}

function tooltipCurrency(value: unknown) {
  return typeof value === "number" ? currency(value) : String(value ?? "");
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

function signedPercent(value: number | null) {
  if (value === null) return "Percentage unavailable";
  return `${value >= 0 ? "+" : "−"}${new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.abs(value))}`;
}

function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
  }[character] ?? character));
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

function periodColor(periodType: string) {
  return periodType === "actual" ? navy : periodType === "nowcast" ? amber : blue;
}

const base: EChartsOption = {
  animationDuration: 450,
  textStyle: { color: "#52647a", fontFamily: "IBM Plex Sans, sans-serif" },
  tooltip: { trigger: "axis", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" } },
};

export function revenueTrendOption(points: Array<{ month: string; value: number; periodType: string; horizon: string }>): EChartsOption {
  const labels = points.map((point) => point.month.slice(0, 7));
  return {
    ...base,
    grid: { left: 62, right: 22, top: 44, bottom: 44 },
    xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "#cbd6e3" } }, axisLabel: { color: "#65758a" } },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    series: [{
      name: "Official revenue",
      type: "line",
      smooth: 0.2,
      symbolSize: 8,
      data: points.map((point) => ({
        value: point.value,
        itemStyle: { color: point.periodType === "nowcast" ? amber : point.horizon === "Primary" ? navy : paleBlue },
      })),
      lineStyle: { color: navy, width: 3 },
      areaStyle: { color: "rgba(59,120,219,0.08)" },
      label: {
        show: true,
        position: "top",
        distance: 7,
        formatter: (params: { value?: unknown }) => typeof params.value === "number" ? currency(params.value) : "",
        color: "#243750",
        fontSize: 10,
        fontWeight: 700,
        textBorderColor: "#fff",
        textBorderWidth: 3,
      },
      labelLayout: { hideOverlap: true },
    }],
  };
}

export function brandRevenueTrendOption(
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
  const actualValues = points.map((point) => point.periodType === "actual" ? point.totalValue : null);
  const transitionValues = points.map((point, index) => (
    index === nowcastIndex - 1 || index === nowcastIndex ? point.totalValue : null
  ));
  const forecastValues = points.map((point, index) => index >= nowcastIndex ? point.totalValue : null);
  const brandColors: Record<"HMA" | "GMA" | "KUS", string> = { HMA: navy, GMA: blue, KUS: paleBlue };
  const tooltip = (params: unknown) => {
    const items = Array.isArray(params) ? params as Array<{ dataIndex?: number }> : [];
    const index = items.find((item) => typeof item.dataIndex === "number")?.dataIndex;
    const point = typeof index === "number" ? points[index] : undefined;
    if (!point) return "";
    const brandDetail = (["HMA", "GMA", "KUS"] as const)
      .map((brand) => {
        const value = point.brandValues[brand];
        return `<br/>${brand}: ${value === null ? "Not available" : exactCurrency(value)}`;
      })
      .join("");
    const rangeDetail = range && point.month === range.month
      ? `<br/>Expected range: ${exactCurrency(range.low)} - ${exactCurrency(range.high)}`
      : "";
    return `<strong>${escapeHtml(shortMonth(point.month))} ${escapeHtml(point.periodType)}</strong><br/>Official Total: ${exactCurrency(point.totalValue)}${brandDetail}${rangeDetail}`;
  };
  const periodAreas: any[] = [
    ...(nowcastIndex > 0 ? [[
      { xAxis: labels[0], itemStyle: { color: "rgba(23,71,149,0.025)" } },
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
    color: [navy, blue, paleBlue],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" }, formatter: tooltip },
    legend: { data: ["HMA", "GMA", "KUS", "Official Total"], top: 0, right: 8, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
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
    series: [
      ...(["HMA", "GMA", "KUS"] as const).map((brand, brandIndex) => ({
        name: brand,
        type: "bar" as const,
        z: 2,
        barMaxWidth: 24,
        itemStyle: { color: brandColors[brand], borderRadius: [3, 3, 0, 0] },
        label: {
          show: true,
          position: "top" as const,
          distance: 3,
          formatter: (params: { value?: unknown }) => typeof params.value === "number" ? currency(params.value) : "",
          color: "#455a72",
          fontSize: 8,
          fontWeight: 650,
        },
        data: points.map((point) => point.brandValues[brand]),
        ...(brandIndex === 0 ? { markArea: { silent: true, label: { show: false }, data: periodAreas } } : {}),
      })),
      {
        name: "Total Actual",
        type: "line",
        z: 6,
        symbol: "none",
        silent: true,
        data: actualValues,
        lineStyle: { color: "#102139", width: 3, type: "solid" },
      },
      {
        name: "Total to Nowcast",
        type: "line",
        z: 6,
        symbol: "none",
        silent: true,
        data: transitionValues,
        lineStyle: { color: amber, width: 3, type: "solid" },
      },
      {
        name: "Total Forecast",
        type: "line",
        z: 6,
        symbol: "none",
        silent: true,
        data: forecastValues,
        lineStyle: { color: blue, width: 3, type: "dashed" },
      },
      {
        name: "Official Total",
        type: "scatter",
        symbolSize: 8,
        z: 7,
        data: points.map((point) => ({
          value: point.totalValue,
          itemStyle: { color: periodColor(point.periodType), borderColor: "#fff", borderWidth: 1.5 },
          label: {
            show: true,
            position: "top",
            distance: 5,
            formatter: currency(point.totalValue),
            color: "#102139",
            fontSize: 9,
            fontWeight: 700,
          },
        })),
      },
    ],
  };
}

export function executiveRevenueTrendOption(
  points: Array<{ month: string; value: number; periodType: string }>,
  range?: { month: string; low: number; high: number },
): EChartsOption {
  const actualEnd = points.findIndex((point) => point.periodType === "nowcast");
  const actualValues = points.map((point) => point.periodType === "actual" ? point.value : null);
  const transitionValues = points.map((point, index) => (
    index === actualEnd - 1 || index === actualEnd ? point.value : null
  ));
  const outlookValues = points.map((point, index) => index >= actualEnd ? point.value : null);
  const rangeIndex = range ? points.findIndex((point) => point.month === range.month) : -1;
  const tooltip = (params: unknown) => {
    const item = params as { data?: { month?: string; periodType?: string; rawValue?: number } };
    const datum = item.data;
    if (!datum || typeof datum.rawValue !== "number") return "";
    const rangeDetail = range && datum.month === range.month
      ? `<br/>Expected range: ${exactCurrency(range.low)} – ${exactCurrency(range.high)}`
      : "";
    return `<strong>${escapeHtml(shortMonth(datum.month ?? ""))} ${escapeHtml(datum.periodType ?? "")}</strong><br/>PIO Revenue: ${exactCurrency(datum.rawValue)}${rangeDetail}`;
  };
  return {
    ...base,
    tooltip: { trigger: "item", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" }, formatter: tooltip },
    grid: { left: 64, right: 24, top: 48, bottom: 54 },
    xAxis: {
      type: "category",
      data: points.map((point) => periodTick(point.month, point.periodType)),
      axisLine: { lineStyle: { color: "#cbd6e3" } },
      axisLabel: { color: "#65758a", lineHeight: 16 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: [
      ...(range && rangeIndex >= 0 ? [{
        name: "Expected range",
        type: "line" as const,
        data: [[rangeIndex, range.low], [rangeIndex, range.high]],
        symbol: "circle",
        symbolSize: 7,
        silent: true,
        z: 1,
        lineStyle: { color: paleBlue, width: 8, opacity: 0.8 },
        itemStyle: { color: paleBlue, borderColor: "#fff", borderWidth: 1 },
      }] : []),
      {
        name: "Actual",
        type: "line",
        smooth: 0.12,
        symbol: "none",
        connectNulls: false,
        silent: true,
        data: actualValues,
        lineStyle: { color: navy, width: 3, type: "solid" },
      },
      {
        name: "Actual to Nowcast",
        type: "line",
        symbol: "none",
        connectNulls: false,
        silent: true,
        data: transitionValues,
        lineStyle: { color: amber, width: 3, type: "solid" },
      },
      {
        name: "Approved Forecast",
        type: "line",
        smooth: 0.12,
        symbol: "none",
        connectNulls: false,
        silent: true,
        data: outlookValues,
        lineStyle: { color: blue, width: 3, type: "dashed" },
      },
      {
        name: "Published value",
        type: "scatter",
        symbolSize: 10,
        z: 4,
        data: points.map((point) => ({
          value: point.value,
          rawValue: point.value,
          month: point.month,
          periodType: point.periodType,
          itemStyle: { color: periodColor(point.periodType), borderColor: "#fff", borderWidth: 2 },
          label: {
            show: true,
            position: "top",
            distance: 8,
            formatter: currency(point.value),
            color: "#243750",
            fontSize: 11,
            fontWeight: 700,
          },
        })),
      },
    ],
  };
}

export function revenueWaterfallOption(points: Array<{
  label: string;
  kind: "total" | "change";
  value: number;
  start: number;
  end: number;
  percent: number | null;
  periodType?: "actual" | "nowcast";
}>): EChartsOption {
  const labels = points.map((point) => point.kind === "total"
    ? periodTick(point.label, point.periodType ?? "")
    : point.label);
  const tooltip = (params: unknown) => {
    const item = params as { dataIndex?: number };
    const point = typeof item.dataIndex === "number" ? points[item.dataIndex] : undefined;
    if (!point) return "";
    if (point.kind === "total") {
      return `<strong>${escapeHtml(labels[item.dataIndex ?? 0]).replace("\n", " ")}</strong><br/>PIO Revenue: ${exactCurrency(point.value)}`;
    }
    return `<strong>${escapeHtml(point.label)} contribution</strong><br/>Revenue change: ${exactCurrency(point.value)}<br/>Change vs prior brand Actual: ${escapeHtml(signedPercent(point.percent))}`;
  };
  return {
    ...base,
    tooltip: { trigger: "item", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" }, formatter: tooltip },
    grid: { left: 62, right: 20, top: 50, bottom: 58 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: "#65758a", lineHeight: 16 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: [
      {
        name: "Offset",
        type: "bar",
        stack: "waterfall",
        silent: true,
        itemStyle: { color: "transparent" },
        emphasis: { itemStyle: { color: "transparent" } },
        data: points.map((point) => point.kind === "total" ? 0 : Math.min(point.start, point.end)),
      },
      {
        name: "Revenue",
        type: "bar",
        stack: "waterfall",
        barMaxWidth: 44,
        data: points.map((point) => ({
          value: point.kind === "total" ? point.value : Math.abs(point.value),
          itemStyle: {
            color: point.kind === "total"
              ? point.periodType === "nowcast" ? amber : navy
              : point.value >= 0 ? blue : "#7b8798",
            borderRadius: [5, 5, 0, 0],
          },
          label: {
            show: true,
            position: "top",
            distance: 6,
            formatter: point.kind === "total"
              ? currency(point.value)
              : `${signedCurrency(point.value)}\n${signedPercent(point.percent)}`,
            color: "#243750",
            fontSize: 10,
            fontWeight: 700,
            lineHeight: 14,
          },
        })),
      },
    ],
  };
}

export function annualRevenueCompositionOption(data: {
  completedActual: number;
  currentNowcast: number;
  remainingForecast: number;
}): EChartsOption {
  const rows = [
    { name: "Completed Actual", value: data.completedActual, color: navy },
    { name: "Current Nowcast", value: data.currentNowcast, color: amber },
    { name: "Remaining Forecast", value: data.remainingForecast, color: paleBlue },
  ];
  return {
    ...base,
    tooltip: { trigger: "item", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" } },
    legend: { bottom: 0, textStyle: { color: "#65758a", fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
    grid: { left: 16, right: 16, top: 30, bottom: 50 },
    xAxis: { type: "value", show: false, max: "dataMax" },
    yAxis: { type: "category", data: ["Revenue"], show: false },
    series: rows.map((row, index) => ({
      name: row.name,
      type: "bar",
      stack: "outlook",
      data: [row.value],
      barWidth: 46,
      itemStyle: {
        color: row.color,
        borderRadius: index === 0 ? [7, 0, 0, 7] : index === rows.length - 1 ? [0, 7, 7, 0] : 0,
      },
      label: {
        show: true,
        position: "inside",
        formatter: currency(row.value),
        color: index === 2 ? "#17304f" : "#fff",
        fontSize: 10,
        fontWeight: 700,
      },
      tooltip: { valueFormatter: tooltipCurrency },
    })),
  };
}

export function pnvwBarOption(points: Array<{ month: string; brand: string; value: number; numerator: number | null; denominator: number | null }>): EChartsOption {
  const months = [...new Set(points.map((point) => point.month))].sort();
  const brands = ["HMA", "GMA", "KUS"].filter((brand) => points.some((point) => point.brand === brand));
  const colors: Record<string, string> = { HMA: navy, GMA: blue, KUS: paleBlue };
  const tooltip = (params: unknown) => {
    const item = params as { data?: { month?: string; brand?: string; rawValue?: number; numerator?: number | null; denominator?: number | null } };
    const datum = item.data;
    if (!datum || typeof datum.rawValue !== "number") return "";
    const numerator = datum.numerator;
    const denominator = datum.denominator;
    return `<strong>${escapeHtml(datum.brand)} · ${escapeHtml(shortMonth(datum.month ?? ""))} Actual</strong><br/>Regular PNVW: ${exactCurrency(datum.rawValue)} / vehicle<br/>Regular PIO Revenue: ${numerator === null || numerator === undefined ? "Not available" : exactCurrency(numerator)}<br/>Regular Wholesale: ${denominator === null || denominator === undefined ? "Not available" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(denominator)} vehicles`;
  };
  return {
    ...base,
    tooltip: { trigger: "item", backgroundColor: "#102139", borderWidth: 0, textStyle: { color: "#fff" }, formatter: tooltip },
    legend: { top: 0, right: 4, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 55, right: 22, top: 35, bottom: 38 },
    xAxis: {
      type: "category",
      data: months.map(shortMonth),
      boundaryGap: true,
      axisLabel: { color: "#65758a", fontSize: 10 },
      axisLine: { lineStyle: { color: "#cbd6e3" } },
    },
    yAxis: {
      type: "value",
      min: 0,
      name: "USD / vehicle",
      nameTextStyle: { color: "#718095", fontSize: 9, padding: [0, 0, 0, 4] },
      axisLabel: { formatter: (value: number) => `$${compact(value)}`, color: "#65758a", fontSize: 9 },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: brands.map((brand) => ({
      name: brand,
      type: "bar",
      itemStyle: { color: colors[brand], borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 28,
      data: months.map((month) => {
        const point = points.find((item) => item.month === month && item.brand === brand);
        return point ? {
          value: point.value,
          rawValue: point.value,
          month: point.month,
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

export function landingRangeOption({ preMonth, nowcast, low, high }: { preMonth: number; nowcast: number; low: number | null; high: number | null }): EChartsOption {
  const values = [preMonth, nowcast, ...(low === null ? [] : [low]), ...(high === null ? [] : [high])];
  const min = Math.min(...values) * 0.94;
  const max = Math.max(...values) * 1.06;
  const rangeSeries = low !== null && high !== null ? [{
    name: "Expected range",
    type: "line" as const,
    data: [[low, "Landing"], [high, "Landing"]],
    symbolSize: 10,
    lineStyle: { color: paleBlue, width: 10 },
    itemStyle: { color: paleBlue },
    tooltip: { valueFormatter: tooltipCurrency },
  }] : [];
  return {
    ...base,
    grid: { left: 24, right: 24, top: 32, bottom: 48 },
    xAxis: { type: "value", min, max, axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    yAxis: { type: "category", data: ["Landing"], axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
    series: [
      ...rangeSeries,
      {
        name: "Original Forecast",
        type: "scatter",
        data: [[preMonth, "Landing"]],
        symbolSize: 16,
        itemStyle: { color: "#8191a5" },
        label: { show: true, position: "bottom", distance: 10, formatter: currency(preMonth), color: "#52647a", fontSize: 10, fontWeight: 700 },
      },
      {
        name: "Nowcast",
        type: "scatter",
        data: [[nowcast, "Landing"]],
        symbolSize: 20,
        itemStyle: { color: navy },
        label: { show: true, position: "top", distance: 10, formatter: currency(nowcast), color: "#243750", fontSize: 10, fontWeight: 700 },
      },
    ],
  };
}

export function donutOption(rows: Array<{ name: string; value: number }>): EChartsOption {
  return {
    ...base,
    tooltip: { trigger: "item", valueFormatter: tooltipCurrency },
    legend: { bottom: 0, textStyle: { color: "#65758a" } },
    color: [navy, blue, paleBlue],
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
      data: rows,
    }],
  };
}

export function divergingBarOption(rows: Array<{ name: string; value: number }>): EChartsOption {
  return {
    ...base,
    grid: { left: 76, right: 76, top: 22, bottom: 36 },
    xAxis: { type: "value", axisLabel: { formatter: (value: number) => currency(value), color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    yAxis: { type: "category", data: rows.map((row) => row.name), axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: "bar",
      data: rows.map((row) => ({
        value: row.value,
        itemStyle: { color: row.value >= 0 ? green : red, borderRadius: row.value >= 0 ? [0, 5, 5, 0] : [5, 0, 0, 5] },
        label: {
          show: true,
          position: row.value >= 0 ? "right" : "left",
          distance: 6,
          formatter: signedCurrency(row.value),
          color: "#334860",
          fontSize: 10,
          fontWeight: 700,
        },
      })),
      barMaxWidth: 26,
    }],
  };
}

export function stackedBarOption(categories: string[], series: Array<{ name: string; values: Array<number | null>; color: string }>, valueLabel = "units"): EChartsOption {
  return {
    ...base,
    legend: { bottom: 0 },
    grid: { left: 62, right: 22, top: 34, bottom: 54 },
    xAxis: { type: "category", data: categories, axisLabel: { color: "#65758a" } },
    yAxis: { type: "value", name: valueLabel, axisLabel: { formatter: compact, color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    series: series.map((item) => ({
      name: item.name,
      type: "bar",
      stack: "total",
      data: item.values,
      itemStyle: { color: item.color },
      barMaxWidth: 42,
      label: {
        show: true,
        position: "inside",
        formatter: (params: { value?: unknown }) => typeof params.value === "number" && params.value !== 0 ? compact(params.value) : "",
        color: item.color === paleBlue ? "#17304f" : "#fff",
        fontSize: 9,
        fontWeight: 700,
      },
      labelLayout: { hideOverlap: true },
    })),
  };
}

export function groupedBarOption(categories: string[], series: Array<{ name: string; values: number[]; color: string }>, currencyValues = false): EChartsOption {
  return {
    ...base,
    legend: { bottom: 0 },
    grid: { left: 64, right: 22, top: 38, bottom: 54 },
    xAxis: { type: "category", data: categories, axisLabel: { color: "#65758a" } },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => currencyValues ? currency(value) : compact(value), color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    series: series.map((item) => ({
      name: item.name,
      type: "bar",
      data: item.values,
      itemStyle: { color: item.color, borderRadius: [5, 5, 0, 0] },
      barMaxWidth: 34,
      label: {
        show: true,
        position: "top",
        distance: 4,
        formatter: (params: { value?: unknown }) => typeof params.value === "number" ? (currencyValues ? currency(params.value) : compact(params.value)) : "",
        color: "#334860",
        fontSize: 9,
        fontWeight: 700,
        textBorderColor: "#fff",
        textBorderWidth: 3,
      },
      labelLayout: { hideOverlap: true },
    })),
  };
}

export function horizontalBarOption(rows: Array<{ name: string; value: number; color?: string }>, currencyValues = false): EChartsOption {
  const ordered = [...rows].sort((left, right) => left.value - right.value);
  return {
    ...base,
    grid: { left: 145, right: currencyValues ? 82 : 68, top: 18, bottom: 32 },
    xAxis: { type: "value", axisLabel: { formatter: (value: number) => currencyValues ? currency(value) : compact(value), color: "#65758a" }, splitLine: { lineStyle: { color: gridColor } } },
    yAxis: { type: "category", data: ordered.map((row) => row.name), axisLabel: { color: "#52647a", width: 120, overflow: "truncate" }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: "bar",
      data: ordered.map((row) => ({ value: row.value, itemStyle: { color: row.color ?? blue, borderRadius: [0, 5, 5, 0] } })),
      barMaxWidth: 22,
      label: {
        show: true,
        position: "right",
        distance: 6,
        formatter: (params: { value?: unknown }) => typeof params.value === "number" ? (currencyValues ? currency(params.value) : compact(params.value)) : "",
        color: "#334860",
        fontSize: 9,
        fontWeight: 700,
      },
      labelLayout: { hideOverlap: true },
    }],
  };
}

export const chartColors = { navy, blue, paleBlue, green, amber, red };
