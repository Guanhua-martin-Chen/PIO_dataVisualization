"use client";

import { DownloadOutlined } from "@ant-design/icons";
import { Button, Collapse, Table, Tabs, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { OFFICIAL_PROXY_BASE } from "../api";
import MetricCard from "../components/MetricCard";
import type { GovernedForecastRecord, GovernedPlcRecord, GovernedQuantityRecord, GovernedWholesaleRecord, RegistryRecord } from "../contract";
import { exactCurrency, formatNumber, formatPercent, formatText, monthLabel, timestampLabel } from "../formatters";
import type { OutputPayload } from "../payloads";
import { revenueValue } from "../viewModels";
import styles from "./OfficialViews.module.css";

const revenueColumns: ColumnsType<GovernedForecastRecord> = [
  { title: "Month", dataIndex: "forecast_month", key: "month", render: (value) => monthLabel(value) },
  { title: "Period", dataIndex: "period_type", key: "period" },
  { title: "Revenue", key: "value", align: "right", render: (_, row) => exactCurrency(revenueValue(row)) },
  { title: "Confidence", dataIndex: "confidence_level", key: "confidence" },
];
const quantityColumns: ColumnsType<GovernedQuantityRecord> = [
  { title: "Month", dataIndex: "forecast_month", key: "month", render: (value) => monthLabel(value) },
  { title: "Period", dataIndex: "period_type", key: "period" },
  { title: "Accessory units", dataIndex: "forecast_pio_quantity", key: "units", align: "right", render: (value) => formatNumber(value) },
  { title: "Kia Fleet", dataIndex: "kia_fleet_adjustment_quantity", key: "fleet", align: "right", render: (value) => formatNumber(value) },
];

export default function OutputView({ payload }: { payload: OutputPayload }) {
  const totals = payload.revenue.data.filter((row) => row.record_type === "forecast_total" || row.record_type === "nowcast_total").slice(0, 7);
  const quantityTotals = payload.quantity.data.filter((row) => row.record_type === "forecast_total").slice(0, 6);
  const plcRows = payload.plc.data.filter((row) => row.record_type === "forecast_brand_plc").slice(0, 10);
  const wholesaleRows = payload.wholesale.data.filter((row) => row.record_type === "forecast_brand").slice(0, 9);
  const executiveRows = [
    { key: "current", period: "Current landing", month: payload.executive.data.current_month.month, type: payload.executive.data.current_month.period_type, revenue: revenueValue(payload.executive.data.current_month.nowcast ?? payload.executive.data.current_month.forecast) },
    { key: "next", period: "Next planning month", month: payload.executive.data.next_month.month, type: payload.executive.data.next_month.period_type, revenue: revenueValue(payload.executive.data.next_month.revenue) },
  ];
  const plcColumns: ColumnsType<GovernedPlcRecord> = [
    { title: "Month", dataIndex: "forecast_month", key: "month", render: (value) => monthLabel(value) },
    { title: "Brand", dataIndex: "brand_group", key: "brand" },
    { title: "PLC", dataIndex: "plc", key: "plc" },
    { title: "Units", dataIndex: "forecast_plc_quantity", key: "units", align: "right", render: (value) => formatNumber(value) },
    { title: "Revenue", dataIndex: "forecast_plc_revenue", key: "revenue", align: "right", render: exactCurrency },
  ];
  const wholesaleColumns: ColumnsType<GovernedWholesaleRecord> = [
    { title: "Month", dataIndex: "forecast_month", key: "month", render: (value) => monthLabel(value) },
    { title: "Brand", dataIndex: "brand_group", key: "brand" },
    { title: "Selected", key: "selected", align: "right", render: (_, row) => formatNumber(row.selected_hybrid_wholesale ?? row.forecast_vehicle_wholesale) },
    { title: "Source", dataIndex: "wholesale_source", key: "source" },
  ];
  const metricColumns: ColumnsType<RegistryRecord> = [
    { title: "Scope", dataIndex: "score_scope", key: "scope", render: formatText },
    { title: "Horizon", dataIndex: "forecast_horizon", key: "horizon", render: formatText },
    { title: "Model", dataIndex: "model_name", key: "model", render: formatText },
    { title: "WAPE", dataIndex: "WAPE", key: "wape", render: (value) => formatPercent(value) },
    { title: "Coverage", dataIndex: "prediction_coverage", key: "coverage", render: (value) => formatPercent(value) },
  ];
  const qaRows = Object.entries(payload.qa.data).map(([check, result]) => ({ check, result }));
  const previews = [
    { key: "executive", label: "1. Executive Summary", children: <Table dataSource={executiveRows} columns={[{ title: "View", dataIndex: "period", key: "period" }, { title: "Month", dataIndex: "month", key: "month", render: (value) => monthLabel(value) }, { title: "Period type", dataIndex: "type", key: "type" }, { title: "Revenue", dataIndex: "revenue", key: "revenue", align: "right", render: exactCurrency }]} pagination={false} size="small" /> },
    { key: "revenue", label: "2. Revenue Forecast", children: <><p className={styles.previewNote}>Limited total-level API preview; download contains the complete approved sheet.</p><Table dataSource={totals} columns={revenueColumns} rowKey={(row) => `${row.record_type}-${row.forecast_month}`} pagination={false} size="small" /></> },
    { key: "quantity", label: "3. Quantity Forecast", children: <Table dataSource={quantityTotals} columns={quantityColumns} rowKey={(row) => row.forecast_month} pagination={false} size="small" /> },
    { key: "plc", label: "4. PLC Planning", children: <><p className={styles.previewNote}>First 10 Brand + PLC API rows; no part-level data is exposed.</p><Table dataSource={plcRows} columns={plcColumns} rowKey={(row) => `${row.forecast_month}-${row.brand_group}-${row.plc}-${row.forecast_component}`} pagination={false} scroll={{ x: 700 }} size="small" /></> },
    { key: "wholesale", label: "5. Wholesale Drivers", children: <Table dataSource={wholesaleRows} columns={wholesaleColumns} rowKey={(row) => `${row.forecast_month}-${row.brand_group}`} pagination={false} size="small" /> },
    { key: "performance", label: "6. Model Performance", children: <Table dataSource={payload.performance.data.selected_portfolio_metrics} columns={metricColumns} rowKey={(row) => `${formatText(row.score_scope)}-${formatText(row.forecast_horizon)}`} pagination={false} size="small" /> },
    { key: "qa", label: "7. QA Summary", children: <Table dataSource={qaRows} columns={[{ title: "Check", dataIndex: "check", key: "check", render: (value: string) => value.replaceAll("_", " ") }, { title: "Result", dataIndex: "result", key: "result", render: formatText }]} rowKey="check" pagination={false} size="small" /> },
  ];
  return <div className={styles.stack}>
    <section className={styles.outputHero}><div className={styles.outputIcon}><DownloadOutlined /></div><div><span>Exact approved artifact</span><h2>{payload.latest.sponsor_workbook_filename}</h2><p>The browser previews Forecast API JSON. The download streams the exact approved Sponsor workbook; this website does not parse or recreate it.</p></div><Button type="primary" size="large" icon={<DownloadOutlined />} href={`${OFFICIAL_PROXY_BASE}/downloads/sponsor-workbook`}>Download Sponsor XLSX</Button></section>
    <div className={styles.metricGrid}>
      <MetricCard label="Release QA" value={`${payload.qa.data.release_checks_passed}/${payload.qa.data.release_check_count}`} detail="Approved publication checks" tone="positive" />
      <MetricCard label="Workbook verification" value={payload.qa.data.workbook_sha256_verified ? "Verified" : "Not verified"} detail="SHA-256 verified at publication" />
      <MetricCard label="Published" value={timestampLabel(payload.latest.meta.published_at)} detail={`Run ${payload.latest.meta.run_id}`} />
    </div>
    <section className={styles.previewTabsCard}>
      <div className={styles.sectionHeading}><div><span>Seven approved outputs</span><h2>Workbook content preview</h2></div><Tag>API JSON preview</Tag></div>
      <Tabs className={styles.previewTabs} items={previews} destroyOnHidden />
    </section>
    <Collapse className={styles.previewCollapse} items={[{ key: "technical", label: "Technical verification", children: <section className={styles.hashCard}><span>Approved workbook SHA-256</span><code>{payload.latest.sponsor_workbook_sha256}</code><small>Source commit {payload.latest.meta.source_git_commit}</small></section> }]} />
  </div>;
}
