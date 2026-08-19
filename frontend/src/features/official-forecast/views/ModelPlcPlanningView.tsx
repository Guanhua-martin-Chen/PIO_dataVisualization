"use client";

import { Segmented, Tag } from "antd";
import type { EChartsOption } from "echarts";
import { useMemo, useState } from "react";

import OfficialChart from "../charts/OfficialChart";
import { monthLabel } from "../formatters";
import {
  topActualModels,
  topActualPlcs,
  topForecastModels,
  topForecastPlcs,
  type ModelPlcPlanningPayload,
  type RankedModel,
  type RankedPlc,
} from "../modelPlcSummary";
import PlcPlanningView from "./PlcPlanningView";
import styles from "./ModelPlcPlanningView.module.css";

export type { HistoricalReportingEnvelope, ModelPlcPlanningPayload } from "../modelPlcSummary";

type PlanningLevel = "brand-plc" | "model-plc";
type SummaryMode = "actual" | "forecast";

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
