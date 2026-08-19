import assert from "node:assert/strict";
import test from "node:test";

import type { PlcEnvelope, TopMoversEnvelope } from "../contract.ts";
import type { HistoricalReportingEnvelope } from "../modelPlcSummary.ts";
import { buildMoverComparisonGroups, defaultMoverComparisonId } from "../topMoverAnalysis.ts";

const meta = {
  schema_version: "1.2.0",
  run_id: "synthetic-run",
  approval_status: "approved" as const,
  registry_version: "synthetic-registry",
  generated_at: "2026-07-29T00:00:00Z",
  published_at: "2026-07-29T01:00:00Z",
  actual_data_through: "2026-07-28",
  completed_training_data_through: "2026-06-30",
  forecast_start: "2026-07-01",
  forecast_end: "2026-12-01",
  source_git_commit: "synthetic",
};

const historical: HistoricalReportingEnvelope = {
  meta,
  data: {
    status: "available",
    latest_complete_month: "2026-06-01",
    available_months: ["2026-04-01", "2026-05-01", "2026-06-01"],
    history_month_count: 3,
    period_policy: "completed actual months only",
    model_grain: "month + brand + model",
    plc_grain: "month + brand + PLC",
    component_policy: "observed all-in",
    model_records: [],
    plc_records: [
      { record_type: "actual_brand_plc", period_type: "actual", month: "2026-04-01", brand_group: "HMA", model_scope: "All Models", plc: "Carpet Floor Mat", pio_quantity: 1, pio_revenue: 100, revenue_share_of_month: 0.5 },
      { record_type: "actual_brand_plc", period_type: "actual", month: "2026-05-01", brand_group: "HMA", model_scope: "All Models", plc: "Carpet Floor Mat", pio_quantity: 1, pio_revenue: 130, revenue_share_of_month: 0.5 },
      { record_type: "actual_brand_plc", period_type: "actual", month: "2026-06-01", brand_group: "HMA", model_scope: "All Models", plc: "Carpet Floor Mat", pio_quantity: 1, pio_revenue: 150, revenue_share_of_month: 0.5 },
      { record_type: "actual_brand_plc", period_type: "actual", month: "2026-05-01", brand_group: "KUS", model_scope: "All Models", plc: "EC Mirror", pio_quantity: 1, pio_revenue: 80, revenue_share_of_month: 0.3 },
      { record_type: "actual_brand_plc", period_type: "actual", month: "2026-06-01", brand_group: "KUS", model_scope: "All Models", plc: "EC Mirror", pio_quantity: 1, pio_revenue: 60, revenue_share_of_month: 0.2 },
    ],
    reconciliation: [],
  },
};

const plc: PlcEnvelope = {
  meta,
  data: [
    { record_type: "forecast_brand_plc", forecast_month: "2026-07-01", period_type: "forecast", forecast_component: "regular", confidence_level: "planning", confidence_detail: "synthetic", forecast_level: "brand_plc", brand_group: "HMA", normalized_model: null, plc: "Carpet Floor Mat", forecast_plc_revenue: 180 },
    { record_type: "forecast_brand_plc", forecast_month: "2026-07-01", period_type: "forecast", forecast_component: "regular", confidence_level: "planning", confidence_detail: "synthetic", forecast_level: "brand_plc", brand_group: "KUS", normalized_model: null, plc: "EC Mirror", forecast_plc_revenue: 75 },
    { record_type: "forecast_brand_plc", forecast_month: "2026-07-01", period_type: "forecast", forecast_component: "kia_fleet_cfm_adjustment", confidence_level: "low", confidence_detail: "synthetic", forecast_level: "brand_plc", brand_group: "KUS", normalized_model: null, plc: "Carpet Floor Mat", forecast_plc_revenue: 20 },
  ],
};

const forecast: TopMoversEnvelope = {
  meta,
  data: {
    status: "available",
    default_comparison_id: "2026-08_vs_2026-07_brand_plc",
    ranking_metric: "absolute_revenue_change",
    top_n: 5,
    currency: "USD",
    percentage_change_formula: "change / baseline",
    thresholds_applied: false,
    classifications_applied: false,
    component_policy: "component matched",
    comparisons: [{
      comparison_id: "2026-08_vs_2026-07_brand_plc",
      comparison_type: "adjacent_forecast_month",
      comparison_context: "next_month_forecast_vs_current_month_premonth_forecast",
      grain: "brand_plc",
      target_month: "2026-08-01",
      comparison_month: "2026-07-01",
      target_period_type: "forecast",
      comparison_period_type: "forecast",
      candidate_count: 1,
      matched_candidate_count: 1,
      excluded_unmatched_count: 0,
      excluded_missing_revenue_count: 0,
      available_upside_count: 1,
      available_downside_count: 0,
      zero_change_count: 0,
      nonpositive_baseline_count: 0,
      upside: [{ rank: 1, direction: "upside", grain: "brand_plc", brand_group: "HMA", plc: "Carpet Floor Mat", forecast_component: "regular", model_scope: null, target_month: "2026-08-01", comparison_month: "2026-07-01", target_revenue: 210, comparison_revenue: 180, revenue_change: 30, absolute_revenue_change: 30, revenue_change_pct: 30 / 180, percentage_change_status: "available", confidence_level: "planning", confidence_detail: "synthetic" }],
      downside: [],
    }],
  },
};

const payload = { forecast, historical, plc };

test("Top Movers groups include Actual, bridge, and API Forecast comparisons", () => {
  const groups = buildMoverComparisonGroups(payload);
  assert.deepEqual(groups.map((group) => group.label), ["Actual movement", "Actual → Plan bridge", "Forecast movement"]);
  assert.equal(groups[0].comparisons.length, 2);
  assert.equal(groups[1].comparisons.length, 1);
  assert.equal(groups[2].comparisons.length, 1);
});

test("Actual comparison ranks observed Brand + PLC changes", () => {
  const groups = buildMoverComparisonGroups(payload);
  const mayToJune = groups[0].comparisons[1];
  assert.equal(mayToJune.title, "Jun 2026 Actual vs May 2026 Actual");
  assert.equal(mayToJune.upside[0].brand_group, "HMA");
  assert.equal(mayToJune.upside[0].absolute_revenue_change, 20);
  assert.equal(mayToJune.downside[0].brand_group, "KUS");
  assert.equal(mayToJune.downside[0].absolute_revenue_change, 20);
});

test("Actual-to-Plan bridge combines planning components at Brand + PLC all-in grain", () => {
  const groups = buildMoverComparisonGroups(payload);
  const bridge = groups[1].comparisons[0];
  assert.equal(bridge.title, "Jul 2026 Original Forecast vs Jun 2026 Actual");
  assert.equal(bridge.upside[0].brand_group, "HMA");
  assert.equal(bridge.upside[0].comparison_revenue, 150);
  assert.equal(bridge.upside[0].target_revenue, 180);
});

test("Default comparison remains the governed July-to-August Forecast comparison", () => {
  assert.equal(defaultMoverComparisonId(payload), "2026-08_vs_2026-07_brand_plc");
});
