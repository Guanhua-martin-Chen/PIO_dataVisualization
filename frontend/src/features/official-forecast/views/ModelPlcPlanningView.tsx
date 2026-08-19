"use client";

import { Tag } from "antd";
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
      formatter: (params: any) => {
        const row = typeof params?.dataIndex === "number" ? rows[params.dataIndex] : undefined;
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
        </div>
        <label className={styles.monthField}>
          <span>Month</span>
          <MonthControl months={months} value={month} onChange={(value) => onSelectionChange({ month: value })} />
        </label>
      </div>
      <div className={styles.summaryTags}>
        <Tag color={period === "actual" ? "blue" : "geekblue"}>{label}</Tag>
        {period === "actual" ? <Tag>Completed month</Tag> : period === "original_forecast" ? <Tag>Pre-month planning view</Tag> : <Tag>Official planning forecast</Tag>}
      </div>
      <div className={styles.chartGrid}>
        <OfficialChart
          eyebrow={`${monthLabel(month)} / USD / ${label}`}
          title={`Top Models by ${label} Revenue`}
          option={modelBarOption(models)}
          height={300}
          summary={period === "actual"
            ? "Observed all-in PIO actual by Brand + Model. No row-level Fleet/dealer classification is asserted."
            : "Official model revenue from the approved Revenue endpoint. Kia Fleet is not manufactured into model allocations."}
        />
        <OfficialChart
          eyebrow={`${monthLabel(month)} / USD / ${label}`}
          title={`Top PLCs by ${label} Revenue`}
          option={plcStackOption(plcs, period)}
          height={300}
          summary={period === "actual"
            ? "Observed all-in PLC actual, stacked by brand for display."
            : "Official Brand + PLC revenue, with the governed Kia Fleet component kept separate in amber."}
        />
      </div>
    </section>

    <section className={styles.detailDivider}>
      <span>Detailed planning</span>
      <p>Use Brand and Planning Level to inspect the governed forecast records for this planning month.</p>
    </section>

    <PlcPlanningView payload={payload.plc} month={month} brand={brand} level={level} showMonthControl={false} showSummaryChart={false} onSelectionChange={onSelectionChange} />
  </div>;
}
