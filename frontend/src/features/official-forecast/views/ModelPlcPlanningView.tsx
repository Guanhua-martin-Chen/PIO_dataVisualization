"use client";

import { Segmented, Tag } from "antd";
import type { EChartsOption } from "echarts";
import { useMemo, useState } from "react";

import OfficialChart from "../charts/OfficialChart";
import type { GovernedForecastRecord, GovernedPlcRecord, GovernedRunMetadata, PlcEnvelope, RevenueEnvelope } from "../contract";
import { finite, monthLabel } from "../formatters";
import PlcPlanningView from "./PlcPlanningView";
import styles from "./OfficialViews.module.css";

type PlanningLevel = "brand-plc" | "model-plc";
type SummaryMode = "actual" | "forecast";

type HistoricalModelRecord = {
  record_type: "actual_model";
  period_type: "actual";
  month: string;
  brand_group: string;
  normalized_model: string;
  pio_quantity: number;
  pio_revenue: number;
  revenue_share_of_month: number | null;
};

type HistoricalPlcRecord = {
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
    model_records: HistoricalModelRecord[];
    plc_records: HistoricalPlcRecord[];
    reconciliation: Array<{
      month: string;
      passes: boolean;
      model_reconciliation_difference: number;
      brand_plc_reconciliation_difference: number;
      max_brand_reconciliation_difference: number;
    }>;
  };
};

export type ModelPlcPlanningPayload = {
  plc: PlcEnvelope;
  revenue: RevenueEnvelope;
  historical: HistoricalReportingEnvelope;
};

type RankedModel = { name: string; brand: string; value: number };
type RankedPlc = { plc: string; total: number; brandValues: Record<string, number> };

const BRAND_COLORS: Record<string, string> = {
  HMA: "#0057B8",
  KUS: "#D33F49",
  GMA: "#495464",
  "Kia Fleet": "#D79A24",
};

function money(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

function modelBarOption(rows: RankedModel[]): EChartsOption | null {
  if (!rows.length) return null;
  return {
    animationDuration: 400,
    grid: { left: 130, right: 54, top: 8, bottom: 22 },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => money(value), color: "#65758a" },
      splitLine: { lineStyle: { color: "#e7edf4" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map((row) => `${row.brand} · ${row.name}`),
      axisLabel: { color: "#344a63", width: 116, overflow: "truncate" },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: {
      trigger: "item",
      formatter: (params: { dataIndex?: number }) => {
        const row = typeof params.dataIndex === "number" ? rows[params.dataIndex] : undefined;
        return row ? `${row.brand} · ${row.name}<br/><strong>${money(row.value)}</strong>` : "";
      },
    },
    series: [{
      type: "bar",
      barMaxWidth: 22,
      data: rows.map((row) => ({
        value: row.value,
        itemStyle: { color: BRAND_COLORS[row.brand] ?? "#64748b", borderRadius: [0, 4, 4, 0] },
      })),
      label: { show: true, position: "right", formatter: (params: { value?: unknown }) => typeof params.value === "number" ? money(params.value) : "", color: "#344a63", fontWeight: 700 },
    }],
  };
}

function plcStackOption(rows: RankedPlc[]): EChartsOption | null {
  if (!rows.length) return null;
  const keys = ["HMA", "KUS", "GMA", "Kia Fleet"];
  return {
    animationDuration: 400,
    color: keys.map((key) => BRAND_COLORS[key]),
    legend: { top: 0, right: 4, data: keys, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 } },
    grid: { left: 142, right: 54, top: 38, bottom: 22 },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => money(value), color: "#65758a" },
      splitLine: { lineStyle: { color: "#e7edf4" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map((row) => row.plc),
      axisLabel: { color: "#344a63", width: 128, overflow: "truncate" },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    series: keys.map((key) => ({
      name: key,
      type: "bar" as const,
      stack: "revenue",
      barMaxWidth: 22,
      itemStyle: { color: BRAND_COLORS[key] },
      data: rows.map((row) => row.brandValues[key] ?? 0),
    })),
  };
}

function topActualModels(historical: HistoricalReportingEnvelope, month: string): RankedModel[] {
  return historical.data.model_records
    .filter((row) => row.month === month)
    .map((row) => ({ name: row.normalized_model, brand: row.brand_group, value: row.pio_revenue }))
    .sort((left, right) => right.value - left.value)
    .slice(0, 6);
}

function topForecastModels(revenue: RevenueEnvelope, month: string): RankedModel[] {
  return revenue.data
    .filter((row: GovernedForecastRecord) => row.forecast_month === month && row.record_type === "forecast_model" && row.brand_group && row.normalized_model)
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

function topActualPlcs(historical: HistoricalReportingEnvelope, month: string): RankedPlc[] {
  return rankedPlcs(historical.data.plc_records
    .filter((row) => row.month === month)
    .map((row) => ({ plc: row.plc, brand: row.brand_group, value: row.pio_revenue })));
}

function topForecastPlcs(plc: PlcEnvelope, month: string): RankedPlc[] {
  return rankedPlcs(plc.data
    .filter((row: GovernedPlcRecord) => row.forecast_month === month && row.record_type === "forecast_brand_plc" && row.plc && row.brand_group)
    .flatMap((row) => {
      const value = finite(row.forecast_plc_revenue);
      if (value === null) return [];
      const brand = row.forecast_component === "kia_fleet_cfm_adjustment" ? "Kia Fleet" : row.brand_group as string;
      return [{ plc: row.plc as string, brand, value }];
    }));
}

export default function ModelPlcPlanningView({
  payload,
  month,
  brand,
  level,
  onSelectionChange,
}: {
  payload: ModelPlcPlanningPayload;
  month: string;
  brand: string;
  level: PlanningLevel;
  onSelectionChange: (updates: { month?: string; brand?: string; level?: PlanningLevel }) => void;
}) {
  const [mode, setMode] = useState<SummaryMode>("actual");
  const actualMonth = payload.historical.data.latest_complete_month;
  const forecastMonth = month;
  const models = useMemo(
    () => mode === "actual" ? topActualModels(payload.historical, actualMonth) : topForecastModels(payload.revenue, forecastMonth),
    [actualMonth, forecastMonth, mode, payload.historical, payload.revenue],
  );
  const plcs = useMemo(
    () => mode === "actual" ? topActualPlcs(payload.historical, actualMonth) : topForecastPlcs(payload.plc, forecastMonth),
    [actualMonth, forecastMonth, mode, payload.historical, payload.plc],
  );
  const displayMonth = mode === "actual" ? actualMonth : forecastMonth;

  return <div className={styles.stack}>
    <section className={styles.summaryHero}>
      <div className={styles.summaryHeading}>
        <div>
          <span>Executive Model & PLC detail</span>
          <h2>{mode === "actual" ? "Latest complete actual" : "Next planning forecast"}</h2>
          <p>{mode === "actual"
            ? `${monthLabel(actualMonth)} is the latest complete month available for Model / PLC actual analysis.`
            : `${monthLabel(forecastMonth)} shows official forecast concentration using the approved Revenue and PLC Planning outputs.`}</p>
        </div>
        <Segmented value={mode} onChange={(value) => setMode(value as SummaryMode)} options={[{ label: "Actual", value: "actual" }, { label: "Forecast", value: "forecast" }]} />
      </div>
      <div className={styles.summaryTags}>
        <Tag color={mode === "actual" ? "blue" : "geekblue"}>{monthLabel(displayMonth)} {mode === "actual" ? "Actual" : "Forecast"}</Tag>
        {mode === "actual" ? <Tag>Completed month only</Tag> : <Tag>Official planning detail</Tag>}
      </div>
      <div className={styles.chartGrid}>
        <OfficialChart
          eyebrow={`${monthLabel(displayMonth)} / USD / ${mode}`}
          title={`Top Models by ${mode === "actual" ? "Actual" : "Forecast"} Revenue`}
          option={modelBarOption(models)}
          height={300}
          summary={mode === "actual"
            ? "Observed all-in PIO actual by Brand + Model. No row-level Fleet/dealer classification is asserted."
            : "Official model revenue from the approved Revenue endpoint. Kia Fleet is not manufactured into model allocations."}
        />
        <OfficialChart
          eyebrow={`${monthLabel(displayMonth)} / USD / ${mode}`}
          title={`Top PLCs by ${mode === "actual" ? "Actual" : "Forecast"} Revenue`}
          option={plcStackOption(plcs)}
          height={300}
          summary={mode === "actual"
            ? "Observed all-in PLC actual, stacked by brand for display."
            : "Official Brand + PLC revenue, with the governed Kia Fleet component kept separate in amber."}
        />
      </div>
    </section>

    <section className={styles.detailDivider}>
      <span>Detailed planning workspace</span>
      <p>Forecast controls and reconciled Brand + PLC / Brand + Model + PLC detail remain unchanged below.</p>
    </section>

    <PlcPlanningView payload={payload.plc} month={month} brand={brand} level={level} onSelectionChange={onSelectionChange} />
  </div>;
}
