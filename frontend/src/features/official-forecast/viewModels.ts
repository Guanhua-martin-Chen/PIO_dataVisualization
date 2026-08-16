import type {
  ExecutiveSummaryEnvelope,
  ExecutiveViewModel,
  GovernedForecastRecord,
  GovernedWholesaleRecord,
  PnvwActualRecord,
  RevenueEnvelope,
  TopMover,
  TopMoverComparison,
} from "./contract";
import { finite, firstNumber } from "./formatters.ts";

export type RangeState =
  | { available: true; low: number; high: number }
  | { available: false; low: null; high: null };

export type RevenueTrendPoint = {
  month: string;
  value: number;
  periodType: "actual" | "nowcast" | "forecast";
  horizon: "Primary" | "Exploratory";
  low: number | null;
  high: number | null;
};

export type ExecutiveBrandTrendPoint = {
  month: string;
  totalValue: number;
  periodType: "actual" | "nowcast" | "forecast";
  brandValues: Record<"HMA" | "GMA" | "KUS", number | null>;
};

export type ExecutiveBrandSnapshot = {
  brand: "HMA" | "GMA" | "KUS";
  currentValue: number | null;
  previousValue: number | null;
  changeValue: number | null;
  changePercent: number | null;
  nextValue: number | null;
};

export type ExecutivePnvwPoint = {
  month: string;
  periodType: "actual" | "nowcast";
  brand: string;
  value: number;
  numerator: number | null;
  denominator: number | null;
};

export type WholesaleSourceDisplay =
  | "Sponsor Plan only"
  | "Sponsor Plan + Internal fallback"
  | "Internal fallback only"
  | "Unavailable";

export type WholesaleInputRow = {
  brand: "HMA" | "GMA" | "KUS";
  selected: number | null;
  sponsorPlan: number | null;
  internalReference: number | null;
  source: WholesaleSourceDisplay;
  fallbackModelCount: number | null;
};

export type WholesaleInputSummary = {
  rows: WholesaleInputRow[];
  totalSelected: number | null;
  brandsUsingFallback: number | null;
  modelsUsingFallback: number | null;
};

export function rangeState(view: Pick<ExecutiveViewModel, "rangeLow" | "rangeHigh">): RangeState {
  if (view.rangeLow === null || view.rangeHigh === null) {
    return { available: false, low: null, high: null };
  }
  return { available: true, low: view.rangeLow, high: view.rangeHigh };
}

export function revenueValue(record: GovernedForecastRecord | null | undefined) {
  return firstNumber(record?.final_revenue_nowcast, record?.forecast_pio_revenue);
}

export function primaryRevenueRows(records: GovernedForecastRecord[], month: string) {
  return records.filter(
    (row) => row.forecast_month === month && row.record_type.startsWith("forecast_"),
  );
}

export function landingRevenueRows(records: GovernedForecastRecord[], month: string) {
  const monthRows = records.filter((row) => row.forecast_month === month);
  const nowcasts = monthRows.filter((row) => row.record_type.startsWith("nowcast_"));
  return nowcasts.length ? nowcasts : primaryRevenueRows(records, month);
}

export function uniqueMonths(records: Array<{ forecast_month: string }>) {
  return [...new Set(records.map((row) => row.forecast_month))].sort();
}

export function defaultPlanningMonth(months: string[], actualDataThrough: string) {
  const cutoffMonth = actualDataThrough.slice(0, 7);
  return months.find((month) => month.slice(0, 7) > cutoffMonth) ?? months[0] ?? "";
}

export function wholesaleSourceDisplay(value: unknown): WholesaleSourceDisplay {
  if (typeof value !== "string" || value.trim() === "") return "Unavailable";
  const hasSponsor = value.includes("sponsor_plan_official");
  const hasFallback = value.includes("internal_forecast_fallback");
  if (hasSponsor && hasFallback) return "Sponsor Plan + Internal fallback";
  if (hasSponsor) return "Sponsor Plan only";
  if (hasFallback) return "Internal fallback only";
  return "Unavailable";
}

export function buildWholesaleInputSummary(
  records: GovernedWholesaleRecord[],
  month: string,
): WholesaleInputSummary {
  const publishedRows = records.filter(
    (row) => row.forecast_month === month && row.record_type === "forecast_brand",
  );
  const rows = (["HMA", "GMA", "KUS"] as const).map((brand): WholesaleInputRow => {
    const record = publishedRows.find((row) => row.brand_group === brand);
    return {
      brand,
      selected: firstNumber(
        record?.selected_hybrid_wholesale,
        record?.forecast_vehicle_wholesale,
      ),
      sponsorPlan: finite(record?.sponsor_reported_brand_total),
      internalReference: finite(record?.internal_forecast_wholesale),
      source: wholesaleSourceDisplay(record?.wholesale_source),
      fallbackModelCount: finite(record?.fallback_model_count),
    };
  });
  const selectedAvailable = rows.every((row) => row.selected !== null);
  const fallbackAvailable = rows.every((row) => row.fallbackModelCount !== null);
  return {
    rows,
    totalSelected: selectedAvailable
      ? rows.reduce((sum, row) => sum + (row.selected as number), 0)
      : null,
    brandsUsingFallback: fallbackAvailable
      ? rows.filter((row) => (row.fallbackModelCount as number) > 0).length
      : null,
    modelsUsingFallback: fallbackAvailable
      ? rows.reduce((sum, row) => sum + (row.fallbackModelCount as number), 0)
      : null,
  };
}

export function buildRevenueTrend(
  executive: ExecutiveSummaryEnvelope,
  revenue: RevenueEnvelope,
): RevenueTrendPoint[] {
  const current = executive.data.current_month;
  const currentRecord = current.nowcast ?? current.forecast;
  const forecastTotals = revenue.data
    .filter((row) => row.record_type === "forecast_total")
    .sort((left, right) => left.forecast_month.localeCompare(right.forecast_month));

  return forecastTotals.slice(0, 6).flatMap((row, index) => {
    const useCurrent = row.forecast_month === current.month && currentRecord;
    const record = useCurrent ? currentRecord : row;
    const value = revenueValue(record);
    if (value === null) return [];
    return [{
      month: row.forecast_month,
      value,
      periodType: useCurrent ? current.period_type : row.period_type,
      horizon: index < 3 ? "Primary" : "Exploratory",
      low: useCurrent ? finite(currentRecord?.low_revenue_nowcast) : finite(row.low_revenue_nowcast),
      high: useCurrent ? finite(currentRecord?.high_revenue_nowcast) : finite(row.high_revenue_nowcast),
    }];
  });
}

export function buildExecutiveBrandTrend(
  executive: ExecutiveSummaryEnvelope,
): ExecutiveBrandTrendPoint[] {
  return executive.data.trend_window.flatMap((point) => {
    const totalValue = finite(point.total_revenue);
    if (totalValue === null) return [];
    return [{
      month: point.month,
      totalValue,
      periodType: point.period_type,
      brandValues: {
        HMA: finite(point.brand_revenue.HMA),
        GMA: finite(point.brand_revenue.GMA),
        KUS: finite(point.brand_revenue.KUS),
      },
    }];
  });
}

export function buildExecutiveBrandSnapshots(
  executive: ExecutiveSummaryEnvelope,
): ExecutiveBrandSnapshot[] {
  const brands = ["HMA", "GMA", "KUS"] as const;
  const comparisons = new Map(
    executive.data.current_vs_previous_actual.brands.map((row) => [row.brand_group, row]),
  );
  const currentRows = new Map(
    (executive.data.current_month.brand_nowcasts.length
      ? executive.data.current_month.brand_nowcasts
      : executive.data.current_month.brand_forecasts)
      .flatMap((row) => row.brand_group ? [[row.brand_group, row] as const] : []),
  );
  const nextRows = new Map(
    executive.data.next_month.brand_forecasts
      .flatMap((row) => row.brand_group ? [[row.brand_group, row] as const] : []),
  );

  return brands.map((brand) => {
    const comparison = comparisons.get(brand);
    return {
      brand,
      currentValue: finite(comparison?.current_revenue) ?? revenueValue(currentRows.get(brand)),
      previousValue: finite(comparison?.previous_revenue),
      changeValue: finite(comparison?.revenue_change),
      changePercent: finite(comparison?.change_pct),
      nextValue: revenueValue(nextRows.get(brand)),
    };
  });
}

export function buildExecutivePnvwHistory(
  executive: ExecutiveSummaryEnvelope,
): ExecutivePnvwPoint[] {
  const actualRecords = executive.data.pnvw_actual_history.records;
  const actualMonths = [...new Set(actualRecords.map((record) => record.month))]
    .sort()
    .slice(-2);
  const actualPoints = actualRecords.flatMap((record: PnvwActualRecord) => {
    if (!actualMonths.includes(record.month)) return [];
    const value = finite(record.pnvw);
    return value === null ? [] : [{
      month: record.month,
      periodType: "actual" as const,
      brand: record.brand_group,
      value,
      numerator: finite(record.numerator),
      denominator: finite(record.denominator),
    }];
  });
  const currentMonth = executive.data.current_month.month;
  const governedBrands = new Set(["HMA", "GMA", "KUS"]);
  const nowcastPoints = executive.data.current_month.brand_nowcasts.flatMap((record) => {
    const value = finite(record.pnvw);
    if (
      record.period_type !== "nowcast"
      || record.forecast_month !== currentMonth
      || !record.brand_group
      || !governedBrands.has(record.brand_group)
      || value === null
    ) return [];
    return [{
      month: record.forecast_month,
      periodType: "nowcast" as const,
      brand: record.brand_group,
      value,
      numerator: finite(record.forecast_pio_revenue_regular_nonfleet),
      denominator: finite(record.selected_hybrid_wholesale),
    }];
  });
  return [...actualPoints, ...nowcastPoints];
}

export function selectOverviewMovers(
  comparison: TopMoverComparison | undefined,
): TopMover[] {
  if (!comparison) return [];
  const selected: TopMover[] = [];
  let upsideIndex = 0;
  let downsideIndex = 0;

  while (selected.length < 5) {
    const upside = comparison.upside[upsideIndex];
    const downside = comparison.downside[downsideIndex];
    if (!upside && !downside) break;

    if (
      !downside
      || (upside && upside.absolute_revenue_change >= downside.absolute_revenue_change)
    ) {
      selected.push(upside);
      upsideIndex += 1;
    } else {
      selected.push(downside);
      downsideIndex += 1;
    }
  }

  return selected;
}
