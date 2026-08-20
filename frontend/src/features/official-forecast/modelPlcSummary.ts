import type {
  GovernedForecastRecord,
  GovernedPlcRecord,
  GovernedRunMetadata,
  PlcEnvelope,
  RevenueEnvelope,
} from "./contract";
import { finite } from "./formatters.ts";

export type HistoricalModelRecord = {
  record_type: "actual_model";
  period_type: "actual";
  month: string;
  brand_group: string;
  normalized_model: string;
  pio_quantity: number;
  pio_revenue: number;
  revenue_share_of_month: number | null;
};

export type HistoricalPlcRecord = {
  record_type: "actual_brand_plc";
  period_type: "actual";
  month: string;
  brand_group: string;
  model_scope: "All Models";
  plc: string;
  pio_quantity: number;
  pio_revenue: number;
  revenue_share_of_month: number | null;
};

export type HistoricalPlcComponentRecord = {
  record_type: "actual_brand_plc_component";
  period_type: "actual";
  month: string;
  brand_group: string;
  model_scope: "All Models";
  plc: string;
  component: "regular" | "kia_fleet_cfm_adjustment";
  pio_quantity: number;
  pio_revenue: number;
  revenue_share_of_month: number | null;
};

export type HistoricalReportingEnvelope = {
  meta: GovernedRunMetadata;
  data: {
    status: string;
    latest_complete_month: string;
    available_months: string[];
    history_month_count: number;
    period_policy: string;
    model_grain: string;
    plc_grain: string;
    component_policy: string;
    plc_component_grain?: string;
    plc_component_policy?: string;
    model_records: HistoricalModelRecord[];
    plc_records: HistoricalPlcRecord[];
    plc_component_records?: HistoricalPlcComponentRecord[];
    reconciliation: Array<{
      month: string;
      passes: boolean;
      model_reconciliation_difference: number;
      brand_plc_reconciliation_difference: number;
      max_brand_reconciliation_difference: number;
      plc_component_actual_revenue?: number;
      plc_component_reconciliation_difference?: number;
      plc_component_max_brand_reconciliation_difference?: number;
      plc_component_passes?: boolean;
    }>;
  };
};

export type ModelPlcPlanningPayload = {
  plc: PlcEnvelope;
  revenue: RevenueEnvelope;
  historical: HistoricalReportingEnvelope;
};

export type PlanningPeriod = "actual" | "original_forecast" | "forecast";
export type RankedModel = { name: string; brand: string; value: number };
export type RankedPlc = { plc: string; total: number; brandValues: Record<string, number> };

export function modelPlcMonths(payload: ModelPlcPlanningPayload): string[] {
  const actualMonths = payload.historical.data.available_months;
  const forecastMonths = payload.plc.data.map((row) => row.forecast_month);
  return [...new Set([...actualMonths, ...forecastMonths])].sort();
}

export function planningPeriodForMonth(
  historical: HistoricalReportingEnvelope,
  actualDataThrough: string,
  month: string,
): PlanningPeriod {
  if (historical.data.available_months.includes(month)) return "actual";
  if (month.slice(0, 7) === actualDataThrough.slice(0, 7)) return "original_forecast";
  return "forecast";
}

export function topActualModels(historical: HistoricalReportingEnvelope, month: string): RankedModel[] {
  return historical.data.model_records
    .filter((row) => row.month === month)
    .map((row) => ({ name: row.normalized_model, brand: row.brand_group, value: row.pio_revenue }))
    .sort((left, right) => right.value - left.value)
    .slice(0, 6);
}

export function topForecastModels(revenue: RevenueEnvelope, month: string): RankedModel[] {
  return revenue.data
    .filter((row: GovernedForecastRecord) => row.forecast_month === month
      && row.record_type.endsWith("_model")
      && row.period_type === "forecast"
      && row.forecast_component !== "kia_fleet_cfm_adjustment"
      && row.brand_group
      && row.normalized_model)
    .flatMap((row) => {
      const value = finite(row.forecast_pio_revenue);
      return value === null ? [] : [{ name: row.normalized_model as string, brand: row.brand_group as string, value }];
    })
    .sort((left, right) => right.value - left.value)
    .slice(0, 6);
}

function rankedPlcs(rows: Array<{ plc: string; brand: string; value: number }>): RankedPlc[] {
  const grouped = new Map<string, RankedPlc>();
  rows.forEach((row) => {
    const current = grouped.get(row.plc) ?? { plc: row.plc, total: 0, brandValues: {} };
    current.total += row.value;
    current.brandValues[row.brand] = (current.brandValues[row.brand] ?? 0) + row.value;
    grouped.set(row.plc, current);
  });
  return [...grouped.values()].sort((left, right) => right.total - left.total).slice(0, 6);
}

export function topActualPlcs(historical: HistoricalReportingEnvelope, month: string): RankedPlc[] {
  const componentRows = historical.data.plc_component_records
    ?.filter((row) => row.month === month) ?? [];

  if (componentRows.length) {
    return rankedPlcs(componentRows.map((row) => ({
      plc: row.plc,
      brand: row.component === "kia_fleet_cfm_adjustment"
        ? "Kia Fleet"
        : row.brand_group,
      value: row.pio_revenue,
    })));
  }

  return rankedPlcs(historical.data.plc_records
    .filter((row) => row.month === month)
    .map((row) => ({ plc: row.plc, brand: row.brand_group, value: row.pio_revenue })));
}

export function topForecastPlcs(plc: PlcEnvelope, month: string): RankedPlc[] {
  return rankedPlcs(plc.data
    .filter((row: GovernedPlcRecord) => row.forecast_month === month
      && row.record_type === "forecast_brand_plc"
      && row.period_type === "forecast"
      && row.plc
      && row.brand_group)
    .flatMap((row) => {
      const value = finite(row.forecast_plc_revenue);
      if (value === null) return [];
      const brand = row.forecast_component === "kia_fleet_cfm_adjustment"
        ? "Kia Fleet"
        : row.brand_group as string;
      return [{ plc: row.plc as string, brand, value }];
    }));
}
