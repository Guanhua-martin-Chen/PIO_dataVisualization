"use client";

import { Empty, Select, Tag } from "antd";
import { useMemo, useState } from "react";

import { compactCurrency, exactCurrency, formatPercent, monthLabel } from "../formatters";
import {
  buildMoverComparisonGroups,
  defaultMoverComparisonId,
  type MoverComparisonKind,
  type MoverComparisonView,
  type MoverRow,
  type TopMoversAnalysisPayload,
} from "../topMoverAnalysis";
import styles from "./OfficialViews.module.css";

function kindLabel(kind: MoverComparisonKind) {
  if (kind === "actual") return "Actual movement";
  if (kind === "bridge") return "Actual → Original Forecast";
  return "Forecast movement";
}

function componentLabel(component?: string) {
  return component === "kia_fleet_cfm_adjustment" ? "Kia Fleet" : "Regular";
}

function MoverList({ direction, rows, comparison }: {
  direction: "upside" | "downside";
  rows: MoverRow[];
  comparison: MoverComparisonView;
}) {
  const title = direction === "upside" ? "Top Upside" : "Top Downside";
  const emptyDescription = comparison.kind === "forecast"
    ? `No ${direction} movers returned by the approved Top Movers API`
    : `No ${direction} movers in this governed comparison`;
  return (
    <section className={styles.moverPanel}>
      <div className={styles.sectionHeading}>
        <div><span>{comparison.kind === "forecast" ? "API ranking" : "Governed comparison"}</span><h2>{title}</h2></div>
        <Tag color={direction === "upside" ? "green" : "red"}>{rows.length} returned</Tag>
      </div>
      {rows.length ? (
        <ol className={styles.moverList}>
          {rows.map((row) => (
            <li key={`${comparison.comparison_id}-${row.direction}-${row.rank}-${row.brand_group}-${row.plc}-${row.forecast_component ?? "all-in"}`}>
              <span className={styles.moverRank}>{row.rank}</span>
              <div className={styles.moverIdentity}>
                <strong>{row.brand_group} / {row.plc}</strong>
                {comparison.kind === "forecast" ? (
                  <span>
                    <Tag color={row.forecast_component === "kia_fleet_cfm_adjustment" ? "gold" : "blue"}>{componentLabel(row.forecast_component)}</Tag>
                    {row.confidence_level ? <Tag>{row.confidence_level}</Tag> : null}
                  </span>
                ) : null}
              </div>
              <div className={direction === "upside" ? styles.moverUp : styles.moverDown}>
                <strong>{direction === "upside" ? "+" : "-"}{compactCurrency(row.absolute_revenue_change)}</strong>
                <span>{row.revenue_change_pct === null ? "Percentage unavailable" : `${direction === "upside" ? "+" : "-"}${formatPercent(Math.abs(row.revenue_change_pct))}`}</span>
              </div>
              <small>{monthLabel(row.comparison_month, true)} {comparison.comparison_label} {exactCurrency(row.comparison_revenue)} → {monthLabel(row.target_month, true)} {comparison.target_label} {exactCurrency(row.target_revenue)}</small>
            </li>
          ))}
        </ol>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyDescription} />}
    </section>
  );
}

export default function TopMoversView({ payload }: { payload: TopMoversAnalysisPayload }) {
  const groups = useMemo(() => buildMoverComparisonGroups(payload), [payload]);
  const comparisons = useMemo(() => groups.flatMap((group) => group.comparisons), [groups]);
  const initialId = defaultMoverComparisonId(payload);
  const [comparisonId, setComparisonId] = useState(initialId);
  const comparison = comparisons.find((item) => item.comparison_id === comparisonId)
    ?? comparisons.find((item) => item.comparison_id === initialId)
    ?? comparisons[0]
    ?? null;

  if (!comparison) {
    return <section className={styles.tableCard}><Empty description="Top Movers are not available in this approved run" /></section>;
  }

  return (
    <div className={styles.stack}>
      {comparisons.length > 1 ? (
        <div className={styles.controls}>
          <Select
            aria-label="Mover comparison"
            value={comparison.comparison_id}
            onChange={setComparisonId}
            options={groups.map((group) => ({
              label: group.label,
              options: group.comparisons.map((item) => ({ value: item.comparison_id, label: item.title })),
            }))}
            style={{ minWidth: 390 }}
          />
        </div>
      ) : null}

      <section className={styles.moverContext}>
        <div>
          <span>Comparison</span>
          <h2>{comparison.title}</h2>
          <p>{comparison.context}</p>
        </div>
        <div className={styles.contextTags}>
          <Tag color="blue">Brand + PLC</Tag>
          <Tag>{kindLabel(comparison.kind)}</Tag>
          <Tag>No thresholds</Tag>
        </div>
      </section>

      <div className={styles.moverGrid}>
        <MoverList direction="upside" rows={comparison.upside} comparison={comparison} />
        <MoverList direction="downside" rows={comparison.downside} comparison={comparison} />
      </div>

      <section className={styles.moverNote}>
        <strong>How to read this</strong>
        <p>{comparison.kind === "actual"
          ? "Completed Actual comparisons use approved Historical Reporting at Brand + PLC grain and rank absolute month-to-month revenue changes. They are descriptive movements, not causal explanations, alerts, anomalies, or materiality classifications."
          : comparison.kind === "bridge"
            ? "This bridge compares the latest completed all-in Actual with the current-month all-in Original Forecast at Brand + PLC grain. Regular and Kia Fleet planning components are combined before comparison because completed Actual does not assert a row-level Fleet/dealer split."
            : "Forecast comparisons are the governed Top Movers API rankings for adjacent planning months. They are not same-target forecast revisions, causal explanations, alerts, anomalies, or materiality classifications. Fewer than five means fewer real movers were returned."}</p>
      </section>
    </div>
  );
}
