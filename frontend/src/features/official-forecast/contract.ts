export type GovernedRunMetadata = {
  schema_version: string;
  run_id: string;
  approval_status: "approved";
  registry_version: string;
  generated_at: string;
  published_at: string;
  actual_data_through: string;
  completed_training_data_through: string;
  forecast_start: string;
  forecast_end: string;
  source_git_commit: string;
};

export type GovernedForecastRecord = {
  record_type: string;
  forecast_month: string;
  period_type: "actual" | "nowcast" | "forecast";
  forecast_component: string;
  confidence_level: string;
  confidence_detail: string;
  forecast_level: string | null;
  brand_group: string | null;
  normalized_model: string | null;
  plc: string | null;
  forecast_pio_revenue?: number | null;
  forecast_pio_revenue_regular_nonfleet?: number | null;
  kia_fleet_adjustment_revenue?: number | null;
  premonth_forecast?: number | null;
  premonth_revenue_forecast?: number | null;
  final_revenue_nowcast?: number | null;
  low_revenue_nowcast?: number | null;
  high_revenue_nowcast?: number | null;
  change_from_premonth?: number | null;
  historical_nowcast_WAPE?: number | null;
  selected_brand_revenue_regular?: number | null;
  selected_revenue_model?: string | null;
  pnvw?: number | null;
  revenue_forecast_source?: string | null;
};

export type GovernedQuantityRecord = GovernedForecastRecord & {
  forecast_pio_quantity?: number | null;
  forecast_pio_quantity_regular_nonfleet?: number | null;
  kia_fleet_adjustment_quantity?: number | null;
  forecast_pio_quantity_rounded?: number | null;
  forecast_vehicle_wholesale?: number | null;
  accessory_units_per_wholesale_vehicle?: number | null;
  quantity_model?: string | null;
  quantity_forecast_source?: string | null;
};

export type GovernedWholesaleRecord = GovernedForecastRecord & {
  forecast_vehicle_wholesale?: number | null;
  selected_hybrid_wholesale?: number | null;
  sponsor_reported_brand_total?: number | null;
  internal_forecast_wholesale?: number | null;
  wholesale_source?: string | null;
  fallback_model_count?: number | null;
  fleet_vehicle_volume?: number | null;
  fleet_model_vehicle_plan?: number | null;
};

export type GovernedPlcRecord = GovernedForecastRecord & {
  forecast_plc_quantity?: number | null;
  forecast_plc_quantity_rounded?: number | null;
  forecast_plc_revenue?: number | null;
  expected_plc_unit_revenue?: number | null;
  pnvw?: number | null;
  plc_units_per_wholesale_vehicle?: number | null;
  fleet_cfm_units_per_fleet_vehicle?: number | null;
  fleet_cfm_revenue_per_fleet_vehicle?: number | null;
  brand_plc_quantity_method?: string | null;
  model_plc_allocation_method?: string | null;
  plc_unit_revenue_method?: string | null;
};

export type DataEnvelope<T> = {
  meta: GovernedRunMetadata;
  data: T;
};

export type RevenueEnvelope = DataEnvelope<GovernedForecastRecord[]>;
export type QuantityEnvelope = DataEnvelope<GovernedQuantityRecord[]>;
export type WholesaleEnvelope = DataEnvelope<GovernedWholesaleRecord[]>;
export type PlcEnvelope = DataEnvelope<GovernedPlcRecord[]>;

export type RegistryRecord = Record<string, unknown> & {
  brand_group?: string;
  brand?: string;
  selected_model?: string;
  recommended_method?: string;
  forecast_horizon?: number | string;
  WAPE?: number | null;
  Bias?: number | null;
  fold_count?: number | null;
  prediction_coverage?: number | null;
  deployable_flag?: boolean;
  selection_reason?: string;
  fallback_rule?: string;
};

export type ModelPerformanceEnvelope = DataEnvelope<{
  brand_revenue_registry: RegistryRecord[];
  model_selection_registry: RegistryRecord[];
  plc_method_registry: RegistryRecord[];
  nowcast_registry: RegistryRecord[];
  selected_portfolio_metrics: RegistryRecord[];
}>;

export type QaEnvelope = DataEnvelope<{
  release_check_count: number;
  release_checks_passed: number;
  workbook_sha256_verified: boolean;
  source_hash_reconciled: boolean;
  brand_registry_deployable: boolean;
  governed_plc_count: number;
  plc_blank_count: number;
  plc_legend_description_conflict_count: number;
  kia_fleet_component_present: boolean;
  api_contains_exact_part_level: boolean;
}>;

export type TopMover = {
  rank: number;
  direction: "upside" | "downside";
  grain: string;
  brand_group: string;
  plc: string;
  forecast_component: string;
  model_scope: string | null;
  target_month: string;
  comparison_month: string;
  target_revenue: number;
  comparison_revenue: number;
  revenue_change: number;
  absolute_revenue_change: number;
  revenue_change_pct: number | null;
  percentage_change_status: string;
  confidence_level: string;
  confidence_detail: string;
};

export type TopMoverComparison = {
  comparison_id: string;
  comparison_type: string;
  comparison_context: string;
  grain: string;
  target_month: string;
  comparison_month: string;
  target_period_type: "actual" | "nowcast" | "forecast";
  comparison_period_type: "actual" | "nowcast" | "forecast";
  candidate_count: number;
  matched_candidate_count: number;
  excluded_unmatched_count: number;
  excluded_missing_revenue_count: number;
  available_upside_count: number;
  available_downside_count: number;
  zero_change_count: number;
  nonpositive_baseline_count: number;
  upside: TopMover[];
  downside: TopMover[];
};

export type TopMoversEnvelope = DataEnvelope<{
  status: string;
  default_comparison_id: string;
  ranking_metric: string;
  top_n: number;
  currency: string;
  percentage_change_formula: string;
  thresholds_applied: boolean;
  classifications_applied: boolean;
  component_policy: string;
  comparisons: TopMoverComparison[];
}>;

export type RevenueComparison = {
  current_revenue: number | null;
  previous_revenue: number | null;
  revenue_change: number | null;
  absolute_change: number | null;
  change_pct: number | null;
};

export type ExecutiveTrendPoint = {
  month: string;
  period_type: "actual" | "nowcast" | "forecast";
  window_role: "historical_actual" | "current_nowcast" | "future_forecast";
  total_revenue: number | null;
  brand_revenue: Record<string, number | null>;
  reconciliation_difference: number | null;
};

export type CumulativeRevenuePoint = {
  month: string;
  period_type: "actual" | "nowcast" | "forecast";
  projection_status: "actual" | "projected_nowcast" | "projected_forecast";
  monthly_revenue: number | null;
  cumulative_revenue: number | null;
};

export type PnvwActualRecord = {
  month: string;
  period_type: "actual";
  brand_group: string;
  forecast_component: "regular";
  numerator: number | null;
  denominator: number | null;
  pnvw: number | null;
};

export type ExecutiveSummaryEnvelope = {
  meta: GovernedRunMetadata;
  data: {
    current_month: {
      month: string;
      period_type: "actual" | "nowcast" | "forecast";
      forecast: GovernedForecastRecord | null;
      nowcast: GovernedForecastRecord | null;
      brand_forecasts: GovernedForecastRecord[];
      brand_nowcasts: GovernedForecastRecord[];
    };
    next_month: {
      month: string;
      period_type: "forecast";
      revenue: GovernedForecastRecord | null;
      quantity: GovernedQuantityRecord | null;
      brand_forecasts: GovernedForecastRecord[];
    };
    headline_performance: Array<{
      score_scope: string;
      forecast_horizon: number | string;
      WAPE: number | null;
      MAE: number | null;
      Bias: number | null;
      fold_count: number | null;
      prediction_coverage: number | null;
    }>;
    previous_completed_month: {
      month: string;
      period_type: "actual";
      total_actual_revenue: number | null;
      brand_actual_revenue: Record<string, number | null>;
      reconciliation_difference: number | null;
    };
    current_vs_previous_actual: {
      status: string;
      current_month: string;
      comparison_month: string;
      current_period_type: "nowcast";
      comparison_period_type: "actual";
      total: RevenueComparison;
      brands: Array<RevenueComparison & { brand_group: string }>;
    };
    trend_window: ExecutiveTrendPoint[];
    cumulative_revenue: {
      calendar_year: number;
      benchmark: null;
      benchmark_status: string;
      points: CumulativeRevenuePoint[];
    };
    pnvw_actual_history: {
      formula: string;
      kia_fleet_policy: string;
      records: PnvwActualRecord[];
    };
  };
};

export type LatestRunResponse = {
  meta: GovernedRunMetadata;
  available_endpoints: string[];
  sponsor_workbook_filename: string;
  sponsor_workbook_sha256: string;
  validation: Record<string, unknown>;
};

export type BrandContribution = {
  brand: string;
  value: number;
  share: number | null;
  fleetRevenue: number | null;
  confidence: string;
};

export type ExecutiveViewModel = {
  meta: GovernedRunMetadata;
  currentMonth: string;
  currentPeriodType: "actual" | "nowcast" | "forecast";
  currentValue: number | null;
  preMonthValue: number | null;
  changeValue: number | null;
  changePercent: number | null;
  previousMonth: string;
  previousActualValue: number | null;
  changeVsPreviousActual: number | null;
  changeVsPreviousActualPercent: number | null;
  rangeLow: number | null;
  rangeHigh: number | null;
  nextMonth: string;
  nextMonthRevenue: number | null;
  nextMonthQuantity: number | null;
  h1Wape: number | null;
  confidence: string;
  confidenceDetail: string;
  brandContributions: BrandContribution[];
  releaseChecksPassed: number | null;
  releaseCheckCount: number | null;
  workbookVerified: boolean | null;
};

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const number = finiteNumber(value);
    if (number !== null) return number;
  }
  return null;
}

function validationNumber(
  validation: Record<string, unknown>,
  key: string,
): number | null {
  return finiteNumber(validation[key]);
}

export function buildExecutiveViewModel(
  payload: ExecutiveSummaryEnvelope,
  latestRun: LatestRunResponse,
): ExecutiveViewModel {
  const current = payload.data.current_month;
  const currentRecord = current.nowcast ?? current.forecast;
  const currentValue = firstNumber(
    currentRecord?.final_revenue_nowcast,
    currentRecord?.forecast_pio_revenue,
  );
  const preMonthValue = firstNumber(
    currentRecord?.premonth_forecast,
    currentRecord?.premonth_revenue_forecast,
  );
  const reportedChange = finiteNumber(currentRecord?.change_from_premonth);
  const changeValue = reportedChange ?? (
    currentValue !== null && preMonthValue !== null
      ? currentValue - preMonthValue
      : null
  );
  const changePercent = changeValue !== null && preMonthValue !== null && preMonthValue > 0
    ? changeValue / preMonthValue
    : null;
  const previous = payload.data.previous_completed_month;
  const previousComparison = payload.data.current_vs_previous_actual.total;
  const brandRows = current.brand_nowcasts.length > 0
    ? current.brand_nowcasts
    : current.brand_forecasts;
  const brandContributions = brandRows
    .map((row): BrandContribution | null => {
      const value = firstNumber(
        row.final_revenue_nowcast,
        row.forecast_pio_revenue,
      );
      if (!row.brand_group || value === null) return null;
      return {
        brand: row.brand_group,
        value,
        share: currentValue && currentValue > 0 ? value / currentValue : null,
        fleetRevenue: finiteNumber(row.kia_fleet_adjustment_revenue),
        confidence: row.confidence_level,
      };
    })
    .filter((row): row is BrandContribution => row !== null)
    .sort((left, right) => right.value - left.value);
  const performance = payload.data.headline_performance.find(
    (row) => String(row.forecast_horizon) === "1",
  ) ?? payload.data.headline_performance[0];
  const validation = latestRun.validation;

  return {
    meta: payload.meta,
    currentMonth: current.month,
    currentPeriodType: current.period_type,
    currentValue,
    preMonthValue,
    changeValue,
    changePercent,
    previousMonth: previous.month,
    previousActualValue: finiteNumber(previous.total_actual_revenue),
    changeVsPreviousActual: finiteNumber(previousComparison.revenue_change),
    changeVsPreviousActualPercent: finiteNumber(previousComparison.change_pct),
    rangeLow: finiteNumber(currentRecord?.low_revenue_nowcast),
    rangeHigh: finiteNumber(currentRecord?.high_revenue_nowcast),
    nextMonth: payload.data.next_month.month,
    nextMonthRevenue: finiteNumber(
      payload.data.next_month.revenue?.forecast_pio_revenue,
    ),
    nextMonthQuantity: finiteNumber(
      payload.data.next_month.quantity?.forecast_pio_quantity,
    ),
    h1Wape: finiteNumber(performance?.WAPE),
    confidence: currentRecord?.confidence_level ?? "not provided",
    confidenceDetail: currentRecord?.confidence_detail ?? "",
    brandContributions,
    releaseChecksPassed: validationNumber(
      validation,
      "release_checks_passed",
    ),
    releaseCheckCount: validationNumber(validation, "release_check_count"),
    workbookVerified: typeof validation.workbook_sha256_verified === "boolean"
      ? validation.workbook_sha256_verified
      : null,
  };
}
