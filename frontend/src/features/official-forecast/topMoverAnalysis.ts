import type { PlcEnvelope, TopMover, TopMoverComparison, TopMoversEnvelope } from "./contract";
import type { HistoricalReportingEnvelope } from "./modelPlcSummary";

export type TopMoversAnalysisPayload = {
  forecast: TopMoversEnvelope;
  historical: HistoricalReportingEnvelope;
  plc: PlcEnvelope;
};

export type MoverComparisonKind = "actual" | "bridge" | "forecast";

export type MoverRow = {
  rank: number;
  direction: "upside" | "downside";
  brand_group: string;
  plc: string;
  target_month: string;
  comparison_month: string;
  target_revenue: number;
  comparison_revenue: number;
  revenue_change: number;
  absolute_revenue_change: number;
  revenue_change_pct: number | null;
  forecast_component?: string;
  confidence_level?: string;
};

export type MoverComparisonView = {
  comparison_id: string;
  kind: MoverComparisonKind;
  target_month: string;
  comparison_month: string;
  target_label: string;
  comparison_label: string;
  title: string;
  context: string;
  upside: MoverRow[];
  downside: MoverRow[];
};

export type MoverComparisonGroup = {
  label: string;
  comparisons: MoverComparisonView[];
};

type RevenuePoint = { brand_group: string; plc: string; revenue: number };

function monthKey(value: string) {
  return value.slice(0, 7);
}

function monthDisplay(value: string) {
  const date = new Date(`${monthKey(value)}-01T00:00:00Z`);
  return new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

function identity(point: RevenuePoint) {
  return `${point.brand_group}\u0000${point.plc}`;
}

function groupRevenue(points: RevenuePoint[]) {
  const grouped = new Map<string, RevenuePoint>();
  points.forEach((point) => {
    const key = identity(point);
    const current = grouped.get(key);
    if (current) current.revenue += point.revenue;
    else grouped.set(key, { ...point });
  });
  return grouped;
}

function rankChanges(
  comparison: RevenuePoint[],
  target: RevenuePoint[],
  comparisonMonth: string,
  targetMonth: string,
  topN = 5,
): Pick<MoverComparisonView, "upside" | "downside"> {
  const comparisonMap = groupRevenue(comparison);
  const targetMap = groupRevenue(target);
  const rows: Omit<MoverRow, "rank" | "direction">[] = [];

  for (const [key, baseline] of comparisonMap.entries()) {
    const next = targetMap.get(key);
    if (!next) continue;
    const change = next.revenue - baseline.revenue;
    if (Math.abs(change) <= 1e-9) continue;
    rows.push({
      brand_group: baseline.brand_group,
      plc: baseline.plc,
      target_month: targetMonth,
      comparison_month: comparisonMonth,
      target_revenue: next.revenue,
      comparison_revenue: baseline.revenue,
      revenue_change: change,
      absolute_revenue_change: Math.abs(change),
      revenue_change_pct: baseline.revenue > 0 ? change / baseline.revenue : null,
    });
  }

  const ordered = [...rows].sort((left, right) =>
    right.absolute_revenue_change - left.absolute_revenue_change
      || left.brand_group.localeCompare(right.brand_group)
      || left.plc.localeCompare(right.plc));
  const ranked = (direction: "upside" | "downside") => ordered
    .filter((row) => direction === "upside" ? row.revenue_change > 0 : row.revenue_change < 0)
    .slice(0, topN)
    .map((row, index) => ({ ...row, rank: index + 1, direction }));

  return { upside: ranked("upside"), downside: ranked("downside") };
}

function actualPoints(historical: HistoricalReportingEnvelope, month: string): RevenuePoint[] {
  return historical.data.plc_records
    .filter((row) => monthKey(row.month) === monthKey(month))
    .map((row) => ({ brand_group: row.brand_group, plc: row.plc, revenue: row.pio_revenue }));
}

function forecastAllInPoints(plc: PlcEnvelope, month: string): RevenuePoint[] {
  return plc.data
    .filter((row) => row.record_type === "forecast_brand_plc"
      && monthKey(row.forecast_month) === monthKey(month)
      && row.brand_group
      && row.plc
      && typeof row.forecast_plc_revenue === "number")
    .map((row) => ({
      brand_group: row.brand_group as string,
      plc: row.plc as string,
      revenue: row.forecast_plc_revenue as number,
    }));
}

function actualComparisons(historical: HistoricalReportingEnvelope): MoverComparisonView[] {
  const months = [...historical.data.available_months].sort();
  const comparisons: MoverComparisonView[] = [];
  for (let index = 1; index < months.length; index += 1) {
    const comparisonMonth = months[index - 1];
    const targetMonth = months[index];
    comparisons.push({
      comparison_id: `actual_${monthKey(targetMonth)}_vs_${monthKey(comparisonMonth)}`,
      kind: "actual",
      comparison_month: comparisonMonth,
      target_month: targetMonth,
      comparison_label: "Actual",
      target_label: "Actual",
      title: `${monthDisplay(targetMonth)} Actual vs ${monthDisplay(comparisonMonth)} Actual`,
      context: "Completed observed month-to-month movement",
      ...rankChanges(
        actualPoints(historical, comparisonMonth),
        actualPoints(historical, targetMonth),
        comparisonMonth,
        targetMonth,
      ),
    });
  }
  return comparisons;
}

function bridgeComparison(historical: HistoricalReportingEnvelope, plc: PlcEnvelope): MoverComparisonView | null {
  const comparisonMonth = historical.data.latest_complete_month;
  const forecastMonths = [...new Set(plc.data
    .filter((row) => row.record_type === "forecast_brand_plc")
    .map((row) => row.forecast_month))]
    .sort();
  const targetMonth = forecastMonths.find((month) => monthKey(month) > monthKey(comparisonMonth));
  if (!targetMonth) return null;

  return {
    comparison_id: `bridge_${monthKey(targetMonth)}_vs_${monthKey(comparisonMonth)}`,
    kind: "bridge",
    comparison_month: comparisonMonth,
    target_month: targetMonth,
    comparison_label: "Actual",
    target_label: "Original Forecast",
    title: `${monthDisplay(targetMonth)} Original Forecast vs ${monthDisplay(comparisonMonth)} Actual`,
    context: "Latest completed Actual vs current-month pre-month planning baseline",
    ...rankChanges(
      actualPoints(historical, comparisonMonth),
      forecastAllInPoints(plc, targetMonth),
      comparisonMonth,
      targetMonth,
    ),
  };
}

function apiRow(row: TopMover): MoverRow {
  return {
    rank: row.rank,
    direction: row.direction,
    brand_group: row.brand_group,
    plc: row.plc,
    target_month: row.target_month,
    comparison_month: row.comparison_month,
    target_revenue: row.target_revenue,
    comparison_revenue: row.comparison_revenue,
    revenue_change: row.revenue_change,
    absolute_revenue_change: row.absolute_revenue_change,
    revenue_change_pct: row.revenue_change_pct,
    forecast_component: row.forecast_component,
    confidence_level: row.confidence_level,
  };
}

function forecastTitle(comparison: TopMoverComparison) {
  if (comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast") {
    return `${monthDisplay(comparison.target_month)} Forecast vs ${monthDisplay(comparison.comparison_month)} Original Forecast`;
  }
  return `${monthDisplay(comparison.target_month)} Forecast vs ${monthDisplay(comparison.comparison_month)} Forecast`;
}

function forecastComparisons(payload: TopMoversEnvelope): MoverComparisonView[] {
  return payload.data.comparisons.map((comparison) => ({
    comparison_id: comparison.comparison_id,
    kind: "forecast",
    comparison_month: comparison.comparison_month,
    target_month: comparison.target_month,
    comparison_label: comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast" ? "Original Forecast" : "Forecast",
    target_label: "Forecast",
    title: forecastTitle(comparison),
    context: comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast"
      ? "Next-month Forecast vs current-month Original Forecast"
      : "Adjacent Forecast-month planning movement",
    upside: comparison.upside.map(apiRow),
    downside: comparison.downside.map(apiRow),
  }));
}

export function buildMoverComparisonGroups(payload: TopMoversAnalysisPayload): MoverComparisonGroup[] {
  const actual = actualComparisons(payload.historical);
  const bridge = bridgeComparison(payload.historical, payload.plc);
  const forecast = forecastComparisons(payload.forecast);
  return [
    { label: "Actual movement", comparisons: actual },
    { label: "Actual → Plan bridge", comparisons: bridge ? [bridge] : [] },
    { label: "Forecast movement", comparisons: forecast },
  ].filter((group) => group.comparisons.length > 0);
}

export function defaultMoverComparisonId(payload: TopMoversAnalysisPayload) {
  return payload.forecast.data.default_comparison_id;
}
