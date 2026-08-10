"use client";

import { Table, Tabs, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { chartColors, stackedBarOption } from "../charts/chartOptions";
import OfficialChart from "../charts/OfficialChart";
import MetricCard from "../components/MetricCard";
import PeriodBadge from "../components/PeriodBadge";
import type { GovernedQuantityRecord, QuantityEnvelope } from "../contract";
import { finite, formatNumber, formatText, monthLabel } from "../formatters";
import { uniqueMonths } from "../viewModels";
import { MonthControl } from "./controls";
import styles from "./OfficialViews.module.css";

export default function QuantityView({ payload, month, onMonthChange }: { payload: QuantityEnvelope; month: string; onMonthChange: (month: string) => void }) {
  const months = uniqueMonths(payload.data);
  const rows = payload.data.filter((row) => row.forecast_month === month);
  const total = rows.find((row) => row.record_type === "forecast_total");
  const brands = rows.filter((row) => row.record_type === "forecast_brand");
  const models = rows.filter((row) => row.record_type === "forecast_model");
  const brandColumns: ColumnsType<GovernedQuantityRecord> = [
    { title: "Brand", dataIndex: "brand_group", key: "brand", render: (value) => <strong>{formatText(value)}</strong> },
    { title: "Period", dataIndex: "period_type", key: "period", render: (value) => <PeriodBadge value={value} /> },
    { title: "Official units", dataIndex: "forecast_pio_quantity", key: "units", align: "right", render: (value) => formatNumber(value) },
    { title: "Regular non-Fleet", dataIndex: "forecast_pio_quantity_regular_nonfleet", key: "regular", align: "right", render: (value) => formatNumber(value) },
    { title: "Kia Fleet", dataIndex: "kia_fleet_adjustment_quantity", key: "fleet", align: "right", render: (value) => formatNumber(value) },
    { title: "Units / vehicle", dataIndex: "accessory_units_per_wholesale_vehicle", key: "upv", align: "right", render: (value) => typeof value === "number" ? value.toFixed(2) : "Not provided" },
    { title: "Confidence", dataIndex: "confidence_level", key: "confidence", render: (value) => <Tag>{formatText(value)}</Tag> },
  ];
  const modelColumns: ColumnsType<GovernedQuantityRecord> = [
    { title: "Brand", dataIndex: "brand_group", key: "brand", render: (value) => <strong>{formatText(value)}</strong> },
    { title: "Model", dataIndex: "normalized_model", key: "model", render: formatText },
    { title: "Component", dataIndex: "forecast_component", key: "component", render: (value) => <Tag color={value === "kia_fleet_cfm_adjustment" ? "gold" : "blue"}>{value === "kia_fleet_cfm_adjustment" ? "Kia Fleet" : "Regular"}</Tag> },
    { title: "Period", dataIndex: "period_type", key: "period", render: (value) => <PeriodBadge value={value} /> },
    { title: "Official units", dataIndex: "forecast_pio_quantity", key: "units", align: "right", render: (value) => formatNumber(value) },
    { title: "Units / vehicle", dataIndex: "accessory_units_per_wholesale_vehicle", key: "upv", align: "right", render: (value) => typeof value === "number" ? value.toFixed(2) : "Not provided" },
    { title: "Method", dataIndex: "quantity_model", key: "method", render: formatText },
    { title: "Confidence", dataIndex: "confidence_level", key: "confidence", render: (value) => <Tag>{formatText(value)}</Tag> },
  ];
  return <div className={styles.stack}>
    <div className={styles.controls}><label className={styles.controlField}><span>Forecast Month</span><MonthControl months={months} value={month} onChange={onMonthChange} /></label></div>
    <div className={styles.metricGrid}>
      <MetricCard label="Official accessory units" value={formatNumber(total?.forecast_pio_quantity, true)} detail={`${monthLabel(month)} / ${total?.period_type ?? "not provided"}`} />
      <MetricCard label="Regular non-Fleet units" value={formatNumber(total?.forecast_pio_quantity_regular_nonfleet, true)} detail="Regular component" />
      <MetricCard label="Kia Fleet units" value={formatNumber(total?.kia_fleet_adjustment_quantity, true)} detail="Separate component, added once" />
    </div>
    <OfficialChart eyebrow={`${monthLabel(month)} / accessory units / ${total?.period_type ?? "period not provided"}`} title="Regular and Kia Fleet decomposition" option={brands.length ? stackedBarOption(brands.map((row) => row.brand_group ?? "Unknown"), [{ name: "Regular non-Fleet", values: brands.map((row) => finite(row.forecast_pio_quantity_regular_nonfleet)), color: chartColors.navy }, { name: "Kia Fleet", values: brands.map((row) => finite(row.kia_fleet_adjustment_quantity)), color: chartColors.amber }], "accessory units") : null} summary="Quantity and units per vehicle are counts or ratios, never percentages. Kia Fleet is shown as its own KUS component." />
    <section className={styles.tableCard}>
      <div className={styles.sectionHeading}><div><span>Approved API records</span><h2>Quantity detail</h2></div><Tag>{brands.length + models.length} rows</Tag></div>
      <Tabs items={[
        { key: "brand", label: `Brand (${brands.length})`, children: <Table columns={brandColumns} dataSource={brands} rowKey={(row) => `${row.forecast_month}-${row.brand_group}`} pagination={false} scroll={{ x: 900 }} size="small" /> },
        { key: "model", label: `Model (${models.length})`, children: <Table columns={modelColumns} dataSource={models} rowKey={(row) => `${row.forecast_month}-${row.brand_group}-${row.normalized_model}-${row.forecast_component}`} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 1050 }} size="small" /> },
      ]} />
    </section>
  </div>;
}
