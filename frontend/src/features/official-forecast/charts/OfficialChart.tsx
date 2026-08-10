"use client";

import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import type { ReactNode } from "react";

import styles from "./OfficialChart.module.css";

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
  return (
    <section className={`${styles.panel} ${compact ? styles.compact : ""}`}>
      <div className={styles.heading}>
        <div><span>{eyebrow}</span><h2>{title}</h2></div>
        {badge}
      </div>
      {option ? (
        <div role="img" aria-label={`${title}. ${summary}`}>
          <ReactECharts option={option} notMerge lazyUpdate style={{ height }} className={styles.chart} />
        </div>
      ) : (
        <div className={styles.empty}>{emptyMessage ?? "Data is not available in this approved run."}</div>
      )}
      <p className={styles.summary}>{summary}</p>
    </section>
  );
}
