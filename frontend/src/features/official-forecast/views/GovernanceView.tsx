"use client";

import { CheckCircleFilled, SafetyCertificateOutlined } from "@ant-design/icons";
import { Descriptions, Table, Tabs, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { RegistryRecord } from "../contract";
import { formatNumber, formatPercent, formatText, timestampLabel } from "../formatters";
import type { GovernancePayload } from "../payloads";
import styles from "./OfficialViews.module.css";

function value(record: RegistryRecord, key: string) { return record[key]; }

export default function GovernanceView({ payload }: { payload: GovernancePayload }) {
  const { performance, qa, latest } = payload;
  const brandColumns: ColumnsType<RegistryRecord> = [
    { title: "Brand", key: "brand", render: (_, row) => <strong>{formatText(row.brand_group ?? row.brand)}</strong> },
    { title: "Selected method", key: "method", render: (_, row) => formatText(row.selected_model ?? row.recommended_method) },
    { title: "H1 WAPE", key: "h1", align: "right", render: (_, row) => formatPercent(value(row, "h1_WAPE") ?? row.WAPE) },
    { title: "H2 WAPE", key: "h2", align: "right", render: (_, row) => formatPercent(value(row, "h2_WAPE")) },
    { title: "H3 WAPE", key: "h3", align: "right", render: (_, row) => formatPercent(value(row, "h3_WAPE")) },
    { title: "Coverage", key: "coverage", align: "right", render: (_, row) => formatPercent(row.prediction_coverage ?? value(row, "coverage")) },
    { title: "Deployable", dataIndex: "deployable_flag", key: "deployable", render: (flag) => <Tag color={flag ? "green" : "red"}>{flag ? "Yes" : "No"}</Tag> },
    { title: "Selection reason", dataIndex: "selection_reason", key: "reason", render: formatText },
  ];
  const metricColumns: ColumnsType<RegistryRecord> = [
    { title: "Scope", dataIndex: "score_scope", key: "scope", render: formatText },
    { title: "Horizon", dataIndex: "forecast_horizon", key: "horizon", render: formatText },
    { title: "Model", dataIndex: "model_name", key: "model", render: formatText },
    { title: "WAPE", dataIndex: "WAPE", key: "wape", align: "right", render: (value) => formatPercent(value) },
    { title: "Bias", dataIndex: "Bias", key: "bias", align: "right", render: (value) => formatPercent(value) },
    { title: "Folds", dataIndex: "fold_count", key: "folds", align: "right", render: (value) => formatNumber(value) },
    { title: "Coverage", dataIndex: "prediction_coverage", key: "coverage", align: "right", render: (value) => formatPercent(value) },
  ];
  const checks = [
    ["Release checks", `${qa.data.release_checks_passed}/${qa.data.release_check_count} passed`, qa.data.release_checks_passed === qa.data.release_check_count],
    ["Workbook hash", qa.data.workbook_sha256_verified ? "Verified" : "Not verified", qa.data.workbook_sha256_verified],
    ["Source hash", qa.data.source_hash_reconciled ? "Reconciled" : "Mismatch", qa.data.source_hash_reconciled],
    ["Brand registry", qa.data.brand_registry_deployable ? "Deployable" : "Blocked", qa.data.brand_registry_deployable],
    ["PLC blanks", formatNumber(qa.data.plc_blank_count), qa.data.plc_blank_count === 0],
    ["PLC legend conflicts", formatNumber(qa.data.plc_legend_description_conflict_count), qa.data.plc_legend_description_conflict_count === 0],
    ["Kia Fleet component", qa.data.kia_fleet_component_present ? "Present" : "Missing", qa.data.kia_fleet_component_present],
    ["Exact part level", qa.data.api_contains_exact_part_level ? "Unexpectedly present" : "Excluded", !qa.data.api_contains_exact_part_level],
  ] as const;
  const tabs = [
    { key: "performance", label: "Model Performance", children: <div className={styles.stack}><section className={styles.tableCard}><div className={styles.sectionHeading}><div><span>Frozen registry</span><h2>Brand revenue selections</h2></div><Tag color="green">Approved</Tag></div><Table columns={brandColumns} dataSource={performance.data.brand_revenue_registry} rowKey={(row) => formatText(row.brand_group ?? row.brand)} pagination={false} scroll={{ x: 1150 }} size="small" /></section><section className={styles.tableCard}><div className={styles.sectionHeading}><div><span>Leakage-safe evidence</span><h2>Selected portfolio performance</h2></div><Tag>Common folds</Tag></div><Table columns={metricColumns} dataSource={performance.data.selected_portfolio_metrics} rowKey={(row) => `${formatText(row.score_scope)}-${formatText(row.forecast_horizon)}`} pagination={false} scroll={{ x: 850 }} size="small" /></section></div> },
    { key: "qa", label: "QA", children: <div className={styles.qaGrid}>{checks.map(([label, result, passing]) => <article key={label}><span>{passing ? <CheckCircleFilled className={styles.pass} /> : <SafetyCertificateOutlined className={styles.review} />}{label}</span><strong>{result}</strong></article>)}</div> },
    { key: "metadata", label: "Run Metadata", children: <section className={styles.tableCard}><Descriptions bordered size="small" column={{ xs: 1, sm: 1, md: 2, lg: 3 }} items={[
      { key: "run", label: "Run ID", children: latest.meta.run_id },
      { key: "schema", label: "Schema", children: latest.meta.schema_version },
      { key: "registry", label: "Registry", children: latest.meta.registry_version },
      { key: "generated", label: "Generated", children: timestampLabel(latest.meta.generated_at) },
      { key: "published", label: "Published", children: timestampLabel(latest.meta.published_at) },
      { key: "commit", label: "Source commit", children: latest.meta.source_git_commit },
      { key: "start", label: "Forecast start", children: latest.meta.forecast_start },
      { key: "end", label: "Forecast end", children: latest.meta.forecast_end },
      { key: "status", label: "Approval", children: <Tag color="green">{latest.meta.approval_status}</Tag> },
    ]} /></section> },
  ];
  return <Tabs defaultActiveKey="qa" items={tabs} />;
}
