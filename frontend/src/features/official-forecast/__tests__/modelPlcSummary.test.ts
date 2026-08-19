import assert from "node:assert/strict";
import test from "node:test";

import type { PlcEnvelope, RevenueEnvelope } from "../contract.ts";
import {
  modelPlcMonths,
  planningPeriodForMonth,
  topActualModels,
  topActualPlcs,
  topForecastModels,
  topForecastPlcs,
  type HistoricalReportingEnvelope,
} from "../modelPlcSummary.ts";

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

function historical(): HistoricalReportingEnvelope {
  return {
    meta,
    data: {
      status: "available",
      latest_complete_month: "2026-06-01",
      available_months: ["2026-05-01", "2026-06-01"],
      history_month_count: 2,
      period_policy: "completed actual months only; current partial month excluded",
      model_grain: "month + brand_group + normalized_model",
      plc_grain: "month + brand_group + PLC",
      component_policy: "observed all-in PIO actual; no row-level Fleet/dealer classification is asserted",
      model_records: [
        { record_type: "actual_model", period_type: "actual", month: "2026-06-01", brand_group: "HMA", normalized_model: "tucson", pio_quantity: 1, pio_revenue: 300, revenue_share_of_month: 0.3 },
        { record_type: "actual_model", period_type: "actual", month: "2026-06-01", brand_group: "KUS", normalized_model: "telluride", pio_quantity: 1, pio_revenue: 200, revenue_share_of_month: 0.2 },
        { record_type: "actual_model", period_type: "actual", month: "2026-05-01", brand_group: "GMA", normalized_model: "gv70", pio_quantity: 1, pio_revenue: 999, revenue_share_of_month: 0.9 },
      ],
      plc_records: [
        { record_type: "actual_brand_plc", period_type: "actual", month: "2026-06-01", brand_group: "HMA", model_scope: "All Models", plc: "Carpet Floor Mat", pio_quantity: 1, pio_revenue: 250, revenue_share_of_month: 0.25 },
        { record_type: "actual_brand_plc", period_type: "actual", month: "2026-06-01", brand_group: "KUS", model_scope: "All Models", plc: "Carpet Floor Mat", pio_quantity: 1, pio_revenue: 150, revenue_share_of_month: 0.15 },
        { record_type: "actual_brand_plc", period_type: "actual", month: "2026-06-01", brand_group: "GMA", model_scope: "All Models", plc: "Crossbar", pio_quantity: 1, pio_revenue: 100, revenue_share_of_month: 0.1 },
      ],
      reconciliation: [],
    },
  };
}

function revenue(): RevenueEnvelope {
  const base = {
    confidence_level: "primary",
    confidence_detail: "synthetic",
    forecast_level: "model",
    plc: null,
  };
  return {
    meta,
    data: [
      { ...base, record_type: "forecast_model", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "regular", brand_group: "HMA", normalized_model: "tucson", forecast_pio_revenue: 500 },
      { ...base, record_type: "forecast_model", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "regular", brand_group: "KUS", normalized_model: "telluride", forecast_pio_revenue: 400 },
      { ...base, record_type: "forecast_model", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "kia_fleet_cfm_adjustment", brand_group: "KUS", normalized_model: "fabricated-fleet-model", forecast_pio_revenue: 900 },
      { ...base, record_type: "forecast_model", forecast_month: "2026-07-01", period_type: "forecast", forecast_component: "regular", brand_group: "GMA", normalized_model: "gv70", forecast_pio_revenue: 800 },
    ],
  };
}

function plc(): PlcEnvelope {
  const base = {
    confidence_level: "primary",
    confidence_detail: "synthetic",
    forecast_level: "brand_plc",
    normalized_model: null,
  };
  return {
    meta,
    data: [
      { ...base, record_type: "forecast_brand_plc", forecast_month: "2026-07-01", period_type: "forecast", forecast_component: "regular", brand_group: "HMA", plc: "Crossbar", forecast_plc_revenue: 150 },
      { ...base, record_type: "forecast_brand_plc", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "regular", brand_group: "HMA", plc: "Carpet Floor Mat", forecast_plc_revenue: 300 },
      { ...base, record_type: "forecast_brand_plc", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "regular", brand_group: "KUS", plc: "Carpet Floor Mat", forecast_plc_revenue: 200 },
      { ...base, record_type: "forecast_brand_plc", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "kia_fleet_cfm_adjustment", brand_group: "KUS", plc: "Carpet Floor Mat", forecast_plc_revenue: 100 },
      { ...base, record_type: "forecast_brand_plc", forecast_month: "2026-08-01", period_type: "forecast", forecast_component: "regular", brand_group: "GMA", plc: "Crossbar", forecast_plc_revenue: 250 },
    ],
  };
}

function payload() {
  return { historical: historical(), revenue: revenue(), plc: plc() };
}

test("unified Model PLC month list combines completed Actual and planning months", () => {
  assert.deepEqual(modelPlcMonths(payload()), ["2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01"]);
});

test("month semantics distinguish Actual, current-month Original Forecast, and later Forecast", () => {
  const history = historical();
  assert.equal(planningPeriodForMonth(history, "2026-07-28", "2026-06-01"), "actual");
  assert.equal(planningPeriodForMonth(history, "2026-07-28", "2026-07-01"), "original_forecast");
  assert.equal(planningPeriodForMonth(history, "2026-07-28", "2026-08-01"), "forecast");
});

test("actual summary uses only the selected completed month", () => {
  assert.deepEqual(topActualModels(historical(), "2026-06-01").map((row) => row.name), ["tucson", "telluride"]);
  const rows = topActualPlcs(historical(), "2026-06-01");
  assert.equal(rows[0].plc, "Carpet Floor Mat");
  assert.equal(rows[0].total, 400);
  assert.deepEqual(rows[0].brandValues, { HMA: 250, KUS: 150 });
});

test("forecast model ranking excludes Kia Fleet model attribution", () => {
  const rows = topForecastModels(revenue(), "2026-08-01");
  assert.deepEqual(rows.map((row) => `${row.brand}:${row.name}`), ["HMA:tucson", "KUS:telluride"]);
});

test("forecast PLC ranking keeps Kia Fleet as a separate stack component", () => {
  const rows = topForecastPlcs(plc(), "2026-08-01");
  assert.equal(rows[0].plc, "Carpet Floor Mat");
  assert.equal(rows[0].total, 600);
  assert.deepEqual(rows[0].brandValues, { HMA: 300, KUS: 200, "Kia Fleet": 100 });
  assert.equal(rows[1].plc, "Crossbar");
});
