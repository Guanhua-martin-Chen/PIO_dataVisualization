import assert from "node:assert/strict";
import test from "node:test";

import {
  buildExecutiveViewModel,
  type ExecutiveSummaryEnvelope,
  type ExecutiveViewModel,
  type LatestRunResponse,
  type GovernedWholesaleRecord,
  type RevenueEnvelope,
  type TopMover,
  type TopMoverComparison,
} from "../contract.ts";
import {
  buildExecutiveBrandSnapshots,
  buildExecutiveBrandTrend,
  buildExecutivePnvwHistory,
  buildWholesaleInputSummary,
  buildRevenueTrend,
  defaultPlanningMonth,
  landingRevenueRows,
  primaryRevenueRows,
  rangeState,
  selectOverviewMovers,
  wholesaleSourceDisplay,
} from "../viewModels.ts";
import { forecastComponentLabel, plcMethodLabel } from "../formatters.ts";
import { monthQueryValue, officialHref, resolveChoiceQuery, resolveMonthQuery } from "../officialQuery.ts";

const meta = {
  schema_version: "1.2.0",
  run_id: "synthetic-run",
  approval_status: "approved" as const,
  registry_version: "synthetic-registry",
  generated_at: "2026-04-21T00:00:00Z",
  published_at: "2026-04-21T01:00:00Z",
  actual_data_through: "2026-04-20",
  completed_training_data_through: "2026-03-31",
  forecast_start: "2026-04-01",
  forecast_end: "2026-09-01",
  source_git_commit: "synthetic",
};

function executive(): ExecutiveSummaryEnvelope {
  return {
    meta,
    data: {
      current_month: {
        month: "2026-04-01",
        period_type: "nowcast",
        forecast: null,
        nowcast: {
          record_type: "nowcast_total",
          forecast_month: "2026-04-01",
          period_type: "nowcast",
          forecast_component: "all_components",
          confidence_level: "primary",
          confidence_detail: "synthetic",
          forecast_level: "total",
          brand_group: null,
          normalized_model: null,
          plc: null,
          final_revenue_nowcast: 110,
          premonth_forecast: 100,
          change_from_premonth: 10,
          low_revenue_nowcast: 100,
          high_revenue_nowcast: 120,
        },
        brand_forecasts: [],
        brand_nowcasts: [{
          record_type: "nowcast_brand",
          forecast_month: "2026-04-01",
          period_type: "nowcast",
          forecast_component: "all_components",
          confidence_level: "primary",
          confidence_detail: "synthetic",
          forecast_level: "brand",
          brand_group: "HMA",
          normalized_model: null,
          plc: null,
          final_revenue_nowcast: 70,
          forecast_pio_revenue_regular_nonfleet: 68,
          kia_fleet_adjustment_revenue: 0,
          selected_hybrid_wholesale: 12,
          pnvw: 21.5,
          premonth_forecast: 60,
          change_from_premonth: 10,
        }, {
          record_type: "nowcast_brand",
          forecast_month: "2026-04-01",
          period_type: "nowcast",
          forecast_component: "all_components",
          confidence_level: "primary",
          confidence_detail: "synthetic",
          forecast_level: "brand",
          brand_group: "GMA",
          normalized_model: null,
          plc: null,
          final_revenue_nowcast: 20,
          forecast_pio_revenue_regular_nonfleet: 20,
          kia_fleet_adjustment_revenue: 0,
          selected_hybrid_wholesale: 8,
          pnvw: 22.5,
          premonth_forecast: 15,
          change_from_premonth: 5,
        }, {
          record_type: "nowcast_brand",
          forecast_month: "2026-04-01",
          period_type: "nowcast",
          forecast_component: "all_components",
          confidence_level: "primary",
          confidence_detail: "synthetic",
          forecast_level: "brand",
          brand_group: "KUS",
          normalized_model: null,
          plc: null,
          final_revenue_nowcast: 20,
          forecast_pio_revenue_regular_nonfleet: 18,
          kia_fleet_adjustment_revenue: 2,
          selected_hybrid_wholesale: 6,
          pnvw: 23.5,
          premonth_forecast: 15,
          change_from_premonth: 5,
        }],
      },
      next_month: {
        month: "2026-05-01",
        period_type: "forecast",
        revenue: null,
        quantity: null,
        brand_forecasts: [],
      },
      headline_performance: [],
      previous_completed_month: {
        month: "2026-03-01",
        period_type: "actual",
        total_actual_revenue: 90,
        brand_actual_revenue: { HMA: 60, GMA: 15, KUS: 15 },
        reconciliation_difference: 0,
      },
      current_vs_previous_actual: {
        status: "available",
        current_month: "2026-04-01",
        comparison_month: "2026-03-01",
        current_period_type: "nowcast",
        comparison_period_type: "actual",
        total: {
          current_revenue: 110,
          previous_revenue: 90,
          revenue_change: 20,
          absolute_change: 20,
          change_pct: 0.2222,
        },
        brands: [
          {
            brand_group: "HMA",
            current_revenue: 70,
            previous_revenue: 60,
            revenue_change: 10,
            absolute_change: 10,
            change_pct: 0.1667,
          },
          {
            brand_group: "GMA",
            current_revenue: 20,
            previous_revenue: 15,
            revenue_change: 5,
            absolute_change: 5,
            change_pct: 0.3333,
          },
          {
            brand_group: "KUS",
            current_revenue: 20,
            previous_revenue: 15,
            revenue_change: 5,
            absolute_change: 5,
            change_pct: 0.3333,
          },
        ],
      },
      trend_window: [
        { month: "2026-01-01", period_type: "actual", window_role: "historical_actual", total_revenue: 70, brand_revenue: { HMA: 40, GMA: 15, KUS: 15 }, reconciliation_difference: 0 },
        { month: "2026-02-01", period_type: "actual", window_role: "historical_actual", total_revenue: 80, brand_revenue: { HMA: 45, GMA: 17, KUS: 18 }, reconciliation_difference: 0 },
        { month: "2026-03-01", period_type: "actual", window_role: "historical_actual", total_revenue: 90, brand_revenue: { HMA: 60, GMA: 15, KUS: 15 }, reconciliation_difference: 0 },
        { month: "2026-04-01", period_type: "nowcast", window_role: "current_nowcast", total_revenue: 110, brand_revenue: { HMA: 70, GMA: 20, KUS: 20 }, reconciliation_difference: 0 },
        { month: "2026-05-01", period_type: "forecast", window_role: "future_forecast", total_revenue: 120, brand_revenue: { HMA: 75, GMA: 22, KUS: 23 }, reconciliation_difference: 0 },
        { month: "2026-06-01", period_type: "forecast", window_role: "future_forecast", total_revenue: 130, brand_revenue: { HMA: 80, GMA: 24, KUS: 26 }, reconciliation_difference: 0 },
      ],
      cumulative_revenue: {
        calendar_year: 2026,
        benchmark: null,
        benchmark_status: "not_provided",
        points: [
          { month: "2026-01-01", period_type: "actual", projection_status: "actual", monthly_revenue: 70, cumulative_revenue: 70 },
          { month: "2026-02-01", period_type: "actual", projection_status: "actual", monthly_revenue: 80, cumulative_revenue: 150 },
          { month: "2026-03-01", period_type: "actual", projection_status: "actual", monthly_revenue: 90, cumulative_revenue: 240 },
          { month: "2026-04-01", period_type: "nowcast", projection_status: "projected_nowcast", monthly_revenue: 110, cumulative_revenue: 350 },
          { month: "2026-05-01", period_type: "forecast", projection_status: "projected_forecast", monthly_revenue: 120, cumulative_revenue: 470 },
        ],
      },
      pnvw_actual_history: {
        formula: "regular revenue / regular Wholesale",
        kia_fleet_policy: "excluded_once",
        records: ["01", "02", "03"].flatMap((month, monthIndex) => ["HMA", "GMA", "KUS"].map((brand, brandIndex) => ({
          month: `2026-${month}-01`,
          period_type: "actual" as const,
          brand_group: brand,
          forecast_component: "regular" as const,
          numerator: 100 + monthIndex * 10 + brandIndex,
          denominator: 10,
          pnvw: 10 + monthIndex + brandIndex / 10,
        }))),
      },
    },
  };
}

function revenue(): RevenueEnvelope {
  return {
    meta,
    data: ["01", "02", "03", "04", "05", "06"].map((month, index) => ({
      record_type: "forecast_total",
      forecast_month: `2026-${month}-01`,
      period_type: "forecast",
      forecast_component: "all_components",
      confidence_level: "primary",
      confidence_detail: "synthetic",
      forecast_level: "total",
      brand_group: null,
      normalized_model: null,
      plc: null,
      forecast_pio_revenue: 100 + index,
    })),
  };
}

function latestRun(): LatestRunResponse {
  return {
    meta,
    available_endpoints: ["executive-summary"],
    sponsor_workbook_filename: "synthetic.xlsx",
    sponsor_workbook_sha256: "a".repeat(64),
    validation: {
      release_checks_passed: 22,
      release_check_count: 22,
      workbook_sha256_verified: true,
    },
  };
}

test("range state requires both governed bounds", () => {
  assert.equal(rangeState({ rangeLow: 100, rangeHigh: 120 }).available, true);
  assert.deepEqual(rangeState({ rangeLow: null, rangeHigh: 120 }), {
    available: false,
    low: null,
    high: null,
  });
});

test("executive KPI model uses API previous-Actual movement and the published Original Forecast baseline", () => {
  const view = buildExecutiveViewModel(executive(), latestRun());
  assert.equal(view.previousActualValue, 90);
  assert.equal(view.changeVsPreviousActual, 20);
  assert.equal(view.changeVsPreviousActualPercent, 0.2222);
  assert.equal(view.preMonthValue, 100);
  assert.equal(view.changeValue, 10);
});

test("forecast view trend uses current nowcast and keeps future months as forecast", () => {
  const trend = buildRevenueTrend(executive(), revenue());
  assert.equal(trend.length, 6);
  assert.equal(trend[3].value, 110);
  assert.equal(trend[3].periodType, "nowcast");
  assert.equal(trend[3].low, 100);
  assert.equal(trend[3].horizon, "Exploratory");
  assert.equal(trend[1].low, null);
});

test("executive brand history keeps API period types, brand values, and published totals", () => {
  const payload = executive();
  payload.data.trend_window[0].total_revenue = 71;
  const trend = buildExecutiveBrandTrend(payload);
  assert.deepEqual(trend.map((point) => point.periodType), [
    "actual", "actual", "actual", "nowcast", "forecast", "forecast",
  ]);
  assert.deepEqual(trend.map((point) => point.totalValue), [71, 80, 90, 110, 120, 130]);
  assert.equal(trend[0].brandValues.HMA, 40);
  assert.equal(trend[0].brandValues.GMA, 15);
  assert.equal(trend[0].brandValues.KUS, 15);
  assert.equal(trend[0].totalValue, 71, "the UI must preserve the API total instead of summing brand values");
});

test("brand KPI snapshots preserve API comparison values and fixed brand order", () => {
  const snapshots = buildExecutiveBrandSnapshots(executive());
  assert.deepEqual(snapshots.map((row) => row.brand), ["HMA", "GMA", "KUS"]);
  assert.deepEqual(snapshots.map((row) => row.currentValue), [70, 20, 20]);
  assert.deepEqual(snapshots.map((row) => row.changeValue), [10, 5, 5]);
  assert.deepEqual(snapshots.map((row) => row.changePercent), [0.1667, 0.3333, 0.3333]);
});

test("executive PNVW view shows two Actual months and the API-published current Nowcast", () => {
  const pnvw = buildExecutivePnvwHistory(executive());
  assert.equal(pnvw.length, 9);
  assert.deepEqual([...new Set(pnvw.map((row) => row.month))], ["2026-02-01", "2026-03-01", "2026-04-01"]);
  assert.deepEqual([...new Set(pnvw.map((row) => row.periodType))], ["actual", "nowcast"]);
  assert.equal(pnvw[0].value, 11);
  assert.equal(pnvw[0].numerator, 110);
  assert.equal(pnvw[0].denominator, 10);
  const hmaNowcast = pnvw.find((row) => row.month === "2026-04-01" && row.brand === "HMA");
  assert.equal(hmaNowcast?.value, 21.5);
  assert.equal(hmaNowcast?.numerator, 68);
  assert.equal(hmaNowcast?.denominator, 12);
});

test("overview movers show up to four upside and one real downside without re-ranking", () => {
  const mover = (rank: number, direction: "upside" | "downside"): TopMover => ({
    rank,
    direction,
    grain: "brand_plc",
    brand_group: "HMA",
    plc: `PLC-${rank}`,
    forecast_component: "regular",
    model_scope: null,
    target_month: "2026-05-01",
    comparison_month: "2026-04-01",
    target_revenue: 10,
    comparison_revenue: 5,
    revenue_change: direction === "upside" ? 5 : -5,
    absolute_revenue_change: 5,
    revenue_change_pct: direction === "upside" ? 1 : -1,
    percentage_change_status: "available",
    confidence_level: "primary",
    confidence_detail: "synthetic",
  });
  const comparison = {
    upside: [mover(1, "upside"), mover(2, "upside"), mover(3, "upside"), mover(4, "upside"), mover(5, "upside")],
    downside: [mover(1, "downside")],
  } as TopMoverComparison;
  const selected = selectOverviewMovers(comparison);
  assert.deepEqual(selected.map((item) => `${item.direction}-${item.rank}`), ["upside-1", "upside-2", "upside-3", "upside-4", "downside-1"]);

  const shortComparison = { upside: [mover(1, "upside")], downside: [] } as unknown as TopMoverComparison;
  assert.deepEqual(selectOverviewMovers(shortComparison).map((item) => `${item.direction}-${item.rank}`), ["upside-1"]);
});

test("forecast pages keep model rows when a same-month nowcast also exists", () => {
  const forecastModel = {
    ...revenue().data[0],
    record_type: "forecast_model",
    forecast_level: "model",
    brand_group: "HMA",
    normalized_model: "Synthetic model",
  };
  const nowcastTotal = {
    ...revenue().data[0],
    record_type: "nowcast_total",
    period_type: "nowcast" as const,
  };
  const rows = [forecastModel, nowcastTotal];

  assert.deepEqual(primaryRevenueRows(rows, "2026-01-01"), [forecastModel]);
  assert.deepEqual(landingRevenueRows(rows, "2026-01-01"), [nowcastTotal]);
});

test("planning pages default to the first month after the actual-data month", () => {
  assert.equal(
    defaultPlanningMonth(["2026-07-01", "2026-08-01", "2026-09-01"], "2026-07-28"),
    "2026-08-01",
  );
});

function wholesaleRecord(
  brand: "HMA" | "GMA" | "KUS",
  overrides: Partial<GovernedWholesaleRecord> = {},
): GovernedWholesaleRecord {
  return {
    record_type: "forecast_brand",
    forecast_month: "2026-05-01",
    period_type: "forecast",
    forecast_component: "regular",
    confidence_level: "primary",
    confidence_detail: "synthetic",
    forecast_level: "brand",
    brand_group: brand,
    normalized_model: null,
    plc: null,
    selected_hybrid_wholesale: 10,
    forecast_vehicle_wholesale: 10,
    sponsor_reported_brand_total: 10,
    internal_forecast_wholesale: 12,
    wholesale_source: "sponsor_plan_official",
    fallback_model_count: 0,
    fleet_vehicle_volume: 1000,
    ...overrides,
  };
}

test("Wholesale Inputs preserves explicit zero and excludes Fleet from the selected total", () => {
  const summary = buildWholesaleInputSummary([
    wholesaleRecord("HMA", { selected_hybrid_wholesale: 0, forecast_vehicle_wholesale: 0 }),
    wholesaleRecord("GMA", { selected_hybrid_wholesale: 20, forecast_vehicle_wholesale: 20 }),
    wholesaleRecord("KUS", { selected_hybrid_wholesale: 30, forecast_vehicle_wholesale: 30, fleet_vehicle_volume: 999999 }),
  ], "2026-05-01");
  assert.equal(summary.rows[0].selected, 0);
  assert.equal(summary.totalSelected, 50);
});

test("Wholesale Inputs keeps missing values unavailable instead of coercing them to zero", () => {
  const summary = buildWholesaleInputSummary([
    wholesaleRecord("HMA"),
    wholesaleRecord("GMA", { selected_hybrid_wholesale: null, forecast_vehicle_wholesale: null }),
    wholesaleRecord("KUS", { fallback_model_count: null }),
  ], "2026-05-01");
  assert.equal(summary.totalSelected, null);
  assert.equal(summary.brandsUsingFallback, null);
  assert.equal(summary.modelsUsingFallback, null);
});

test("Wholesale source badges translate only the API-published source code", () => {
  assert.equal(wholesaleSourceDisplay("sponsor_plan_official"), "Sponsor Plan only");
  assert.equal(wholesaleSourceDisplay("internal_forecast_fallback | sponsor_plan_official"), "Sponsor Plan + Internal fallback");
  assert.equal(wholesaleSourceDisplay("internal_forecast_fallback"), "Internal fallback only");
  assert.equal(wholesaleSourceDisplay(null), "Unavailable");
});

test("Official query helpers preserve and validate governed selections", () => {
  const months = ["2026-08-01", "2026-09-01"];
  assert.equal(monthQueryValue(months[1]), "2026-09");
  assert.equal(resolveMonthQuery("2026-09", months, months[0]), months[1]);
  assert.equal(resolveMonthQuery("2099-01", months, months[0]), months[0]);
  assert.equal(resolveChoiceQuery("KUS", ["HMA", "GMA", "KUS"], "HMA"), "KUS");
  assert.equal(resolveChoiceQuery("INVALID", ["HMA", "GMA", "KUS"], "HMA"), "HMA");
  assert.equal(
    officialHref("/official-forecast/plc", { month: months[0], brand: "KUS", level: "model-plc" }),
    "/official-forecast/plc?month=2026-08&brand=KUS&level=model-plc",
  );
});

test("PLC display labels hide raw method and component codes", () => {
  assert.equal(plcMethodLabel("previous_month_share"), "Previous-month PLC share");
  assert.equal(plcMethodLabel("historical_mix_fallback"), "Historical mix fallback");
  assert.equal(plcMethodLabel("annual_average_share"), "Annual average share");
  assert.equal(plcMethodLabel("selected_method"), "Selected method");
  assert.equal(forecastComponentLabel("regular"), "Regular");
  assert.equal(forecastComponentLabel("kia_fleet_cfm_adjustment"), "Kia Fleet CFM adjustment");
});
