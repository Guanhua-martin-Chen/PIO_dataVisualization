"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Alert, Input, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";

import MetricCard from "../components/MetricCard";
import type { GovernedPlcRecord, PlcEnvelope } from "../contract";
import {
  compactCurrency,
  finite,
  forecastComponentLabel,
  formatNumber,
  formatText,
  monthLabel,
  plcMethodLabel,
} from "../formatters";
import { uniqueMonths } from "../viewModels";
import { BrandControl, LevelControl, MonthControl } from "./controls";
import styles from "./OfficialViews.module.css";

type PlanningLevel = "brand-plc" | "model-plc";

function availableNumber(value: unknown, digits?: number) {
  const numeric = finite(value);
  if (numeric === null) return "Not available";
  return digits === undefined ? formatNumber(numeric) : numeric.toFixed(digits);
}

function availableCurrency(value: unknown) {
  const numeric = finite(value);
  if (numeric === null) return "Not available";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(numeric);
}

export default function PlcPlanningView({
  payload,
  month,
  brand,
  level,
  showMonthControl = true,
  onSelectionChange,
}: {
  payload: PlcEnvelope;
  month: string;
  brand: string;
  level: PlanningLevel;
  showMonthControl?: boolean;
  onSelectionChange: (updates: { month?: string; brand?: string; level?: PlanningLevel }) => void;
}) {
  const months = uniqueMonths(payload.data);
  const brandOrder = ["HMA", "GMA", "KUS"];
  const brands = [...new Set(payload.data.flatMap((row) => row.brand_group ? [row.brand_group] : []))].sort((left, right) => {
    const leftIndex = brandOrder.indexOf(left);
    const rightIndex = brandOrder.indexOf(right);
    return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex) || left.localeCompare(right);
  });
  const [search, setSearch] = useState("");
  const brandRows = payload.data.filter((row) => row.forecast_month === month && row.brand_group === brand && row.record_type === "forecast_brand_plc");
  const modelRows = payload.data.filter((row) => row.forecast_month === month && row.brand_group === brand && row.record_type === "forecast_model_plc");
  const regularRows = brandRows.filter((row) => row.forecast_component !== "kia_fleet_cfm_adjustment");
  const fleetRows = brandRows.filter((row) => row.forecast_component === "kia_fleet_cfm_adjustment");
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const sourceRows = level === "brand-plc" ? brandRows : modelRows;
  const tableRows = normalizedSearch ? sourceRows.filter((row) => {
    const plc = row.plc?.toLocaleLowerCase() ?? "";
    if (level === "brand-plc") return plc.includes(normalizedSearch);
    const model = row.normalized_model?.toLocaleLowerCase() ?? "";
    return plc.includes(normalizedSearch) || model.includes(normalizedSearch);
  }) : sourceRows;
  const revenueValues = brandRows.map((row) => finite(row.forecast_plc_revenue));
  const plcRevenue = revenueValues.length > 0 && revenueValues.every((value) => value !== null)
    ? revenueValues.reduce<number>((sum, value) => sum + (value as number), 0)
    : null;

  const columns: ColumnsType<GovernedPlcRecord> = [
    { title: "PLC", dataIndex: "plc", key: "plc", render: (value) => <strong>{formatText(value)}</strong> },
    { title: "Component", dataIndex: "forecast_component", key: "component", render: (value) => <Tag title={formatText(value)} color={value === "kia_fleet_cfm_adjustment" ? "gold" : "blue"}>{forecastComponentLabel(value)}</Tag> },
    { title: "Quantity", dataIndex: "forecast_plc_quantity", key: "quantity", align: "right", render: (value) => availableNumber(value) },
    { title: "Revenue", dataIndex: "forecast_plc_revenue", key: "revenue", align: "right", render: availableCurrency },
    { title: "Unit revenue", dataIndex: "expected_plc_unit_revenue", key: "unitRevenue", align: "right", render: availableCurrency },
    { title: "PLC units / vehicle", dataIndex: "plc_units_per_wholesale_vehicle", key: "upv", align: "right", render: (value) => availableNumber(value, 3) },
    { title: "Method", dataIndex: "brand_plc_quantity_method", key: "method", render: (value) => <span title={formatText(value)}>{plcMethodLabel(value)}</span> },
  ];
  const modelColumns: ColumnsType<GovernedPlcRecord> = [
    { title: "Model", dataIndex: "normalized_model", key: "model", render: (value) => <strong>{formatText(value)}</strong> },
    ...columns,
    { title: "Allocation", dataIndex: "model_plc_allocation_method", key: "allocation", render: (value) => <span title={formatText(value)}>{plcMethodLabel(value)}</span> },
  ];

  return <div className={styles.stack}>
    <div className={styles.controls}>
      {showMonthControl ? <label className={styles.controlField}><span>Forecast Month</span><MonthControl months={months} value={month} onChange={(value) => { setSearch(""); onSelectionChange({ month: value }); }} /></label> : null}
      <label className={styles.controlField}><span>Brand</span><BrandControl brands={brands} value={brand} onChange={(value) => { setSearch(""); onSelectionChange({ brand: value }); }} /></label>
      <label className={styles.controlField}><span>Planning Level</span><LevelControl value={level} onChange={(value) => { setSearch(""); onSelectionChange({ level: value }); }} /></label>
    </div>
    <Alert type="info" showIcon message="PLC is the lowest Official planning category. Exact PIS_PNO and Part Description are intentionally excluded." />
    <div className={styles.metricGrid}>
      <MetricCard label="PLC revenue" value={plcRevenue === null ? "Not available" : compactCurrency(plcRevenue)} detail={`${brand} / ${monthLabel(month)}`} />
      <MetricCard label="Regular PLC rows" value={formatNumber(regularRows.length)} detail="Regular non-Fleet component" />
      <MetricCard label="Kia Fleet PLC rows" value={formatNumber(fleetRows.length)} detail="Separate component, added once" />
    </div>
    <section className={styles.tableCard}>
      <div className={styles.sectionHeading}>
        <div><span>{monthLabel(month)} · Official planning grain</span><h2>{brand} {level === "brand-plc" ? "Brand + PLC" : "Brand + Model + PLC"} Planning</h2></div>
        <div className={styles.tableTools}><Input allowClear prefix={<SearchOutlined />} placeholder="Search PLC or Model" value={search} onChange={(event) => setSearch(event.target.value)} /><Tag color="green">Reconciled</Tag></div>
      </div>
      {level === "brand-plc"
        ? <Table columns={columns} dataSource={tableRows} rowKey={(row) => `${row.forecast_component}-${row.plc}`} pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 1200 }} size="small" />
        : <Table columns={modelColumns} dataSource={tableRows} rowKey={(row) => `${row.forecast_component}-${row.normalized_model}-${row.plc}`} pagination={{ pageSize: 15, showSizeChanger: false }} scroll={{ x: 1450 }} size="small" />}
    </section>
  </div>;
}
