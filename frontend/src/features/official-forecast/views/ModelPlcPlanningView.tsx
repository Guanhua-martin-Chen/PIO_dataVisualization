"use client";

import { Alert, Tag } from "antd";
import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import OfficialChart from "../charts/OfficialChart";
import { monthLabel } from "../formatters";
import {
  modelPlcMonths,
  planningPeriodForMonth,
  topActualModels,
  topActualPlcs,
  topForecastModels,
  topForecastPlcs,
  type ModelPlcPlanningPayload,
  type PlanningPeriod,
  type RankedModel,
  type RankedPlc,
} from "../modelPlcSummary";
import { MonthControl } from "./controls";
import PlcPlanningView from "./PlcPlanningView";
import styles from "./ModelPlcPlanningView.module.css";

export type { HistoricalReportingEnvelope, ModelPlcPlanningPayload } from "../modelPlcSummary";

type PlanningLevel = "brand-plc" | "model-plc";

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

function periodLabel(period: PlanningPeriod) {
  if (period === "actual") return "Actual";
  if (period === "original_forecast") return "Original Forecast";
  return "Forecast";
}

function periodContext(period: PlanningPeriod) {
  if (period === "actual") return "Completed Actual";
  if (period === "original_forecast") return "Pre-month planning view";
  return "Official planning Forecast";
}

function modelDisplayName(value: string) {
  return value
    .split(/\s+/)
    .map((token) => {
      if (!token) return token;
      if (token.toLowerCase() === "ioniq") return "IONIQ";
      if (/\d/.test(token)) return token.toUpperCase();
      return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
    })
    .join(" ");
}

function modelBarOption(rows: RankedModel[]): EChartsOption | null {
  if (!rows.length) return null;
  return {
    animationDuration: 400,
    grid: { left: 138, right: 58, top: 8, bottom: 22 },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => money(value), color: "#65758a" },
      splitLine: { lineStyle: { color: "#e7edf4" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map((row) => `${row.brand} · ${modelDisplayName(row.name)}`),
      axisLabel: { color: "#344a63" },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: {
      trigger: "item",
      formatter: (params: any) => {
        const row = typeof params?.dataIndex === "number" ? rows[params.dataIndex] : undefined;
        return row ? `${row.brand} · ${modelDisplayName(row.name)}<br/><strong>${money(row.value)}</strong>` : "";
      },
    },
    series: [{
      type: "bar",
      barMaxWidth: 22,
      data: rows.map((row) => ({
        value: row.value,
        itemStyle: { color: BRAND_COLORS[row.brand] ?? "#64748b", borderRadius: [0, 4, 4, 0] },
      })),
      label: { show: true, position: "right", formatter: (params: any) => typeof params?.value === "number" ? money(params.value) : "", color: "#344a63", fontWeight: 700 },
    }],
  };
}

function plcStackOption(rows: RankedPlc[], period: PlanningPeriod): EChartsOption | null {
  if (!rows.length) return null;
  const keys = period === "actual" ? ["HMA", "KUS", "GMA"] : ["HMA", "KUS", "GMA", "Kia Fleet"];
  return {
    animationDuration: 400,
    color: keys.map((key) => BRAND_COLORS[key]),
    legend: { top: 0, right: 4, data: keys, selectedMode: false, textStyle: { color: "#65758a", fontSize: 10 } },
    grid: { left: 176, right: 66, top: 38, bottom: 22 },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (value: number) => money(value), color: "#65758a" },
      splitLine: { lineStyle: { color: "#e7edf4" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map((row) => row.plc),
      axisLabel: { color: "#344a63", width: 164, overflow: "truncate" },
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
      data: rows.map((row) => {
        const value = row.brandValues[key] ?? 0;
        const lastVisibleKey = [...keys].reverse().find((candidate) => (row.brandValues[candidate] ?? 0) > 0);
        return {
          value,
          label: key === lastVisibleKey
            ? {
                show: true,
                position: "right" as const,
                formatter: money(row.total),
                color: "#344a63",
                fontWeight: 700,
                distance: 6,
              }
            : { show: false },
        };
      }),
    })),
  };
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
  const months = modelPlcMonths(payload);
  const period = planningPeriodForMonth(payload.historical, payload.plc.meta.actual_data_through, month);
  const label = periodLabel(period);
  const models = useMemo(
    () => period === "actual" ? topActualModels(payload.historical, month) : topForecastModels(payload.revenue, month),
    [month, payload.historical, payload.revenue, period],
  );
  const plcs = useMemo(
    () => period === "actual" ? topActualPlcs(payload.historical, month) : topForecastPlcs(payload.plc, month),
    [month, payload.historical, payload.plc, period],
  );

  return <div className={styles.stack}>
    <section className={styles.summaryHero}>
      <div className={styles.summaryHeading}>
        <div>
          <span>Model & PLC summary</span>
          <h2>{monthLabel(month)} {label}</h2>
          <div className={styles.summaryTags}><Tag color={period === "actual" ? "blue" : "geekblue"}>{periodContext(period)}</Tag></div>
        </div>
        <label className={styles.monthField}>
          <span>Month</span>
          <MonthControl months={months} value={month} onChange={(value) => onSelectionChange({ month: value })} />
        </label>
      </div>
      <div className={styles.chartGrid}>
        <OfficialChart
          eyebrow={`${monthLabel(month)} / USD / ${label}`}
          title={`Top Models by ${label} Revenue`}
          option={modelBarOption(models)}
          height={300}
          summary={period === "actual"
            ? "Completed observed PIO detail by Brand + Model; no Fleet/dealer split is asserted."
            : "Official model revenue; Kia Fleet is not allocated to vehicle models."}
        />
        <OfficialChart
          eyebrow={`${monthLabel(month)} / USD / ${label}`}
          title={`Top PLCs by ${label} Revenue`}
          option={plcStackOption(plcs, period)}
          height={300}
          summary={period === "actual"
            ? "Completed observed PLC detail, stacked by brand."
            : "Official Brand + PLC revenue; governed Kia Fleet is shown separately in amber."}
        />
      </div>
    </section>

    <section className={styles.detailDivider}>
      <span>Detailed planning</span>
      <p>{period === "actual"
        ? "Detailed Brand + PLC and Brand + Model + PLC planning is available for Original Forecast and future Forecast months."
        : "Use Brand and Planning Level to inspect the governed forecast records for this planning month."}</p>
    </section>

    {period === "actual"
      ? <Alert type="info" showIcon message="Select the current-month Original Forecast or a later Forecast month to open the detailed planning table." />
      : <PlcPlanningView payload={payload.plc} month={month} brand={brand} level={level} showMonthControl={false} onSelectionChange={onSelectionChange} />}
  </div>;
}
