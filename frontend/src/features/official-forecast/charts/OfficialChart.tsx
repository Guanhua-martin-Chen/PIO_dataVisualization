"use client";

import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import type { ReactNode } from "react";

import styles from "./OfficialChart.module.css";

function applyPeriodStyling(title: string, option: EChartsOption): EChartsOption {
  const xAxis = Array.isArray(option.xAxis) ? option.xAxis[0] : option.xAxis;
  const labels = Array.isArray((xAxis as { data?: unknown[] } | undefined)?.data)
    ? ((xAxis as { data: unknown[] }).data)
    : [];
  const sourceSeries = Array.isArray(option.series) ? option.series : [];
  const series = sourceSeries.map((entry) => ({ ...(entry as Record<string, unknown>) })) as Array<Record<string, any>>;

  if (title === "Monthly PIO Revenue by Brand") {
    series.forEach((entry) => {
      if (!Array.isArray(entry.data)) return;
      entry.data = entry.data.map((datum: unknown, index: number) => {
        if (!String(labels[index] ?? "").includes("Forecast") || !datum || typeof datum !== "object") {
          return datum;
        }
        const row = datum as Record<string, any>;
        return {
          ...row,
          itemStyle: {
            ...(row.itemStyle ?? {}),
            // Sponsor feedback: future months should be visibly unfinished,
            // but only slightly lighter than Actual/Nowcast bars.
            opacity: 0.88,
          },
        };
      });
    });
  }

  if (title === "Regular PNVW by Brand") {
    const nowcastLabel = labels.find((label) => String(label).includes("Nowcast"));
    if (nowcastLabel !== undefined && series[0]) {
      series[0].markArea = {
        silent: true,
        label: { show: false },
        data: [[
          { xAxis: nowcastLabel, itemStyle: { color: "rgba(215,154,36,0.055)" } },
          { xAxis: nowcastLabel },
        ]],
      };
    }
  }

  return { ...option, series: series as EChartsOption["series"] };
}

export default function OfficialChart({
  eyebrow,
  title,
  option,
  summary,
  badge,
  emptyMessage,
  height = 285,
  compact = false,
}: {
  eyebrow: string;
  title: string;
  option: EChartsOption | null;
  summary: string;
  badge?: ReactNode;
  emptyMessage?: string;
  height?: number;
  compact?: boolean;
}) {
  const styledOption = option ? applyPeriodStyling(title, option) : null;
  return (
    <section className={`${styles.panel} ${compact ? styles.compact : ""}`}>
      <div className={styles.heading}>
        <div><span>{eyebrow}</span><h2>{title}</h2></div>
        {badge}
      </div>
      {styledOption ? (
        <div role="img" aria-label={`${title}. ${summary}`}>
          <ReactECharts option={styledOption} notMerge lazyUpdate style={{ height }} className={styles.chart} />
        </div>
      ) : (
        <div className={styles.empty}>{emptyMessage ?? "Data is not available in this approved run."}</div>
      )}
      <p className={styles.summary}>{summary}</p>
    </section>
  );
}
