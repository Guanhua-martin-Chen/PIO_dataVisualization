"use client";

import { Table, Tabs, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { donutOption, revenueTrendOption } from "../charts/chartOptions";
import OfficialChart from "../charts/OfficialChart";
import MetricCard from "../components/MetricCard";
import PeriodBadge from "../components/PeriodBadge";
import { PnvwNote, PnvwValue } from "../components/PnvwValue";
import type { GovernedForecastRecord, RevenueEnvelope } from "../contract";
import { compactCurrency, exactCurrency, formatText, monthLabel, revenueSourceLabel } from "../formatters";
import { primaryRevenueRows, revenueValue, uniqueMonths } from "../viewModels";
import { MonthControl } from "./controls";
import styles from "./OfficialViews.module.css";

export default function RevenueView({ payload, month, onMonthChange }: { payload: RevenueEnvelope; month: string; onMonthChange: (month: string) => void }) {
  const months = uniqueMonths(payload.data);
  const rows = primaryRevenueRows(payload.data, month);
  const total = rows.find((row) => row.record_type.endsWith("_total"));
  const brands = rows.filter((row) => row.record_type.endsWith("_brand"));
  const models = rows.filter((row) => row.record_type.endsWith("_model"));
  const trend = payload.data.filter((row) => row.record_type === "forecast_total").sort((left, right) => left.forecast_month.localeCompare(right.forecast_month)).slice(0, 6).flatMap((row, index) => {
    const nowcast = payload.data.find((candidate) => candidate.forecast_month === row.forecast_month && candidate.record_type === "nowcast_total");
    const selected = nowcast ?? row;
    const value = revenueValue(selected);
    return value === null ? [] : [{ month: selected.forecast_month, value, periodType: selected.period_type, horizon: index < 3 ? "Primary" : "Exploratory" }];
  });
  const brandColumns: ColumnsType<GovernedForecastRecord> = [
    { title: "Brand", dataIndex: "brand_group", key: "brand", render: (value) => <strong>{formatText(value)}</strong> },
    { title: "Period", dataIndex: "period_type", key: "period", render: (value) => <PeriodBadge value={value} /> },
    { title: "Official revenue", key: "revenue", align: "right", render: (_, row) => exactCurrency(revenueValue(row)) },
    { title: "Regular non-Fleet", dataIndex: "forecast_pio_revenue_regular_nonfleet", key: "regular", align: "right", render: exactCurrency },
    { title: "Regular PNVW ($ / vehicle)", dataIndex: "pnvw", key: "pnvw", align: "right", render: (_, row) => <PnvwValue value={row.pnvw} selectedWholesale={row.selected_hybrid_wholesale} forecastComponent={row.forecast_component} /> },
    { title: "Source", dataIndex: "revenue_forecast_source", key: "source", render: (value) => <Tag title={formatText(value)}>{revenueSourceLabel(value)}</Tag> },
    { title: "Confidence", dataIndex: "confidence_level", key: "confidence", render: (value) => <Tag>{formatText(value)}</Tag> },
  ];
  const modelColumns: ColumnsType<GovernedForecastRecord> = [
    { title: "Brand", dataIndex: "brand_group", key: "brand", render: (value) => <strong>{formatText(value)}</strong> },
    { title: "Model", dataIndex: "normalized_model", key: "model", render: formatText },
    { title: "Component", dataIndex: "forecast_component", key: "component", render: (value) => <Tag color={value === "kia_fleet_cfm_adjustment" ? "gold" : "blue"}>{value === "kia_fleet_cfm_adjustment" ? "Kia Fleet" : "Regular"}</Tag> },
    { title: "Period", dataIndex: "period_type", key: "period", render: (value) => <PeriodBadge value={value} /> },
    { title: "Official revenue", key: "revenue", align: "right", render: (_, row) => exactCurrency(revenueValue(row)) },
    { title: "Regular PNVW ($ / vehicle)", dataIndex: "pnvw", key: "pnvw", align: "right", render: (_, row) => <PnvwValue value={row.pnvw} selectedWholesale={row.selected_hybrid_wholesale} forecastComponent={row.forecast_component} /> },
    { title: "Source", dataIndex: "revenue_forecast_source", key: "source", render: (value) => <Tag title={formatText(value)}>{revenueSourceLabel(value)}</Tag> },
    { title: "Confidence", dataIndex: "confidence_level", key: "confidence", render: (value) => <Tag>{formatText(value)}</Tag> },
  ];
  return <div className={styles.stack}>
    <div className={styles.controls}><label className={styles.controlField}><span>Forecast Month</span><MonthControl months={months} value={month} onChange={onMonthChange} /></label></div>
    <div className={styles.metricGrid}>
      <MetricCard label="Official total revenue" value={compactCurrency(revenueValue(total))} detail={`${monthLabel(month)} / ${total?.period_type ?? "not provided"}`} />
      <MetricCard label="Regular non-Fleet" value={compactCurrency(total?.forecast_pio_revenue_regular_nonfleet)} detail="Governed regular component" />
      <MetricCard label="Kia Fleet adjustment" value={compactCurrency(total?.kia_fleet_adjustment_revenue)} detail="Separate component, added once" />
      <MetricCard label="Confidence" value={total?.confidence_level ?? "Not provided"} detail={total?.confidence_detail ?? "API metadata"} />
    </div>
    <div className={styles.chartGrid}>
      <OfficialChart eyebrow="Six months / USD / H1-H3 Primary, H4-H6 Exploratory" title="Official revenue outlook" option={trend.length ? revenueTrendOption(trend) : null} summary="The current point uses the approved nowcast. Future monthly intervals are not published by this approved run, so no band is fabricated." />
      <OfficialChart eyebrow={`${monthLabel(month)} / USD / ${total?.period_type ?? "period not provided"}`} title="Brand contribution" option={brands.length ? donutOption(brands.flatMap((row) => { const value = revenueValue(row); return row.brand_group && value !== null ? [{ name: row.brand_group, value }] : []; })) : null} summary="HMA, GMA, and KUS contributions reconcile to the governed total. Kia Fleet remains inside KUS only once." />
    </div>
    <section className={styles.tableCard}>
      <div className={styles.sectionHeading}><div><span>Approved API records</span><h2>Revenue detail</h2></div><Tag>{brands.length + models.length} rows</Tag></div>
      <Tabs items={[
        { key: "brand", label: `Brand (${brands.length})`, children: <Table columns={brandColumns} dataSource={brands} rowKey={(row) => `${row.forecast_month}-${row.brand_group}-${row.record_type}`} pagination={false} scroll={{ x: 900 }} size="small" /> },
        { key: "model", label: `Model (${models.length})`, children: <Table columns={modelColumns} dataSource={models} rowKey={(row) => `${row.forecast_month}-${row.brand_group}-${row.normalized_model}-${row.forecast_component}`} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 1050 }} size="small" /> },
      ]} />
      <PnvwNote />
    </section>
  </div>;
}
