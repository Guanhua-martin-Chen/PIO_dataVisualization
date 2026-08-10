"use client";

import { Empty, Select, Tag } from "antd";
import { useState } from "react";

import type { TopMover, TopMoversEnvelope } from "../contract";
import { compactCurrency, exactCurrency, formatPercent, formatText, monthLabel } from "../formatters";
import styles from "./OfficialViews.module.css";

function componentLabel(component: string) {
  return component === "kia_fleet_cfm_adjustment" ? "Kia Fleet" : "Regular";
}

function comparisonContextLabel(context: string) {
  if (context === "next_month_forecast_vs_current_month_premonth_forecast") {
    return "Next-month Forecast vs current-month Original Forecast";
  }
  return context.replaceAll("_", " ");
}

function comparisonTitle(comparison: TopMoversEnvelope["data"]["comparisons"][number]) {
  if (comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast") {
    return `${monthLabel(comparison.target_month)} Forecast vs ${monthLabel(comparison.comparison_month)} Original Forecast`;
  }
  return `${monthLabel(comparison.target_month)} ${comparison.target_period_type} vs ${monthLabel(comparison.comparison_month)} ${comparison.comparison_period_type}`;
}

function MoverList({ direction, rows, comparison }: {
  direction: "upside" | "downside";
  rows: TopMover[];
  comparison: TopMoversEnvelope["data"]["comparisons"][number];
}) {
  const title = direction === "upside" ? "Top Upside" : "Top Downside";
  const comparisonLabel = comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast"
    ? "Original Forecast"
    : comparison.comparison_period_type;
  return (
    <section className={styles.moverPanel}>
      <div className={styles.sectionHeading}>
        <div><span>API ranking</span><h2>{title}</h2></div>
        <Tag color={direction === "upside" ? "green" : "red"}>{rows.length} returned</Tag>
      </div>
      {rows.length ? (
        <ol className={styles.moverList}>
          {rows.map((row) => (
            <li key={`${row.direction}-${row.rank}-${row.brand_group}-${row.plc}-${row.forecast_component}`}>
              <span className={styles.moverRank}>{row.rank}</span>
              <div className={styles.moverIdentity}>
                <strong>{row.brand_group} / {row.plc}</strong>
                <span>
                  <Tag color={row.forecast_component === "kia_fleet_cfm_adjustment" ? "gold" : "blue"}>{componentLabel(row.forecast_component)}</Tag>
                  <Tag>{formatText(row.confidence_level)}</Tag>
                </span>
              </div>
              <div className={direction === "upside" ? styles.moverUp : styles.moverDown}>
                <strong>{direction === "upside" ? "+" : "-"}{compactCurrency(row.absolute_revenue_change)}</strong>
                <span>{row.revenue_change_pct === null ? "Percentage unavailable" : `${direction === "upside" ? "+" : "-"}${formatPercent(Math.abs(row.revenue_change_pct))}`}</span>
              </div>
              <small>{monthLabel(row.comparison_month, true)} {comparisonLabel} {exactCurrency(row.comparison_revenue)} to {monthLabel(row.target_month, true)} {comparison.target_period_type} {exactCurrency(row.target_revenue)}</small>
            </li>
          ))}
        </ol>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`No ${direction} movers returned by the approved API`} />}
    </section>
  );
}

export default function TopMoversView({ payload }: { payload: TopMoversEnvelope }) {
  const [comparisonId, setComparisonId] = useState(payload.data.default_comparison_id);
  const comparison = payload.data.comparisons.find((item) => item.comparison_id === comparisonId) ?? null;

  if (payload.data.status !== "available" || !comparison) {
    return <section className={styles.tableCard}><Empty description="Top Movers are not available in this approved run" /></section>;
  }

  return (
    <div className={styles.stack}>
      {payload.data.comparisons.length > 1 ? (
        <div className={styles.controls}>
          <Select
            aria-label="Mover comparison"
            value={comparisonId}
            onChange={setComparisonId}
            options={payload.data.comparisons.map((item) => ({
              value: item.comparison_id,
              label: comparisonTitle(item),
            }))}
            style={{ minWidth: 320 }}
          />
        </div>
      ) : null}

      <section className={styles.moverContext}>
        <div>
          <span>Comparison</span>
          <h2>{comparisonTitle(comparison)}</h2>
          <p>{comparisonContextLabel(comparison.comparison_context)}</p>
        </div>
        <div className={styles.contextTags}>
          <Tag color="blue">Brand + PLC</Tag>
          <Tag>{comparison.comparison_context === "next_month_forecast_vs_current_month_premonth_forecast"
            ? "Forecast vs Original Forecast"
            : `${comparison.target_period_type} vs ${comparison.comparison_period_type}`}</Tag>
          <Tag>No thresholds</Tag>
        </div>
      </section>

      <div className={styles.moverGrid}>
        <MoverList direction="upside" rows={comparison.upside} comparison={comparison} />
        <MoverList direction="downside" rows={comparison.downside} comparison={comparison} />
      </div>

      <section className={styles.moverNote}>
        <strong>How to read this</strong>
        <p>These are adjacent forecast-month planning movements ranked by the Forecast API using absolute revenue change. They are not same-target forecast revisions, actual or nowcast changes, causal explanations, alerts, anomalies, or materiality classifications. Fewer than five means the API returned fewer real movers.</p>
      </section>
    </div>
  );
}
