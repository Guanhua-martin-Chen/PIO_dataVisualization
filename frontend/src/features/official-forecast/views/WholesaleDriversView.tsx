"use client";

import { SafetyCertificateOutlined } from "@ant-design/icons";
import { Collapse, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";

import MetricCard from "../components/MetricCard";
import type { WholesaleEnvelope } from "../contract";
import { formatNumber, monthLabel } from "../formatters";
import {
  buildWholesaleInputSummary,
  uniqueMonths,
  type WholesaleInputRow,
} from "../viewModels";
import { MonthControl } from "./controls";
import styles from "./OfficialViews.module.css";

function availableNumber(value: number | null, compact = false) {
  return value === null ? "Not available" : formatNumber(value, compact);
}

function sourceColor(source: WholesaleInputRow["source"]) {
  if (source === "Sponsor Plan only") return "blue";
  if (source === "Sponsor Plan + Internal fallback") return "gold";
  if (source === "Internal fallback only") return "orange";
  return "default";
}

export default function WholesaleDriversView({
  payload,
  month,
  onMonthChange,
}: {
  payload: WholesaleEnvelope;
  month: string;
  onMonthChange: (month: string) => void;
}) {
  const months = uniqueMonths(payload.data);
  const summary = buildWholesaleInputSummary(payload.data, month);
  const columns: ColumnsType<WholesaleInputRow> = [
    { title: "Brand", dataIndex: "brand", key: "brand", render: (value) => <strong>{value}</strong> },
    { title: "Sponsor-reported Plan", dataIndex: "sponsorPlan", key: "sponsor", align: "right", render: (value) => availableNumber(value) },
    { title: "Full Internal Forecast — Reference Only", dataIndex: "internalReference", key: "internal", align: "right", render: (value) => availableNumber(value) },
    { title: "Governed Selected Regular Wholesale", dataIndex: "selected", key: "selected", align: "right", render: (value) => availableNumber(value) },
    { title: "Selected Source", dataIndex: "source", key: "source", render: (value) => <Tag color={sourceColor(value)}>{value}</Tag> },
    { title: "Models Using Fallback", dataIndex: "fallbackModelCount", key: "fallback", align: "right", render: (value) => availableNumber(value) },
  ];

  return <div className={styles.stack}>
    <div className={styles.controls}>
      <label className={styles.controlField}>
        <span>Forecast Month</span>
        <MonthControl months={months} value={month} onChange={onMonthChange} />
      </label>
    </div>

    <section className={styles.stack} aria-labelledby="selected-wholesale-heading">
      <div className={styles.sectionHeading}>
        <div><span>Governed pipeline result</span><h2 id="selected-wholesale-heading">Selected Regular Wholesale — {monthLabel(month)}</h2></div>
      </div>

      <div className={styles.metricGrid}>
        <MetricCard label="Total Selected Regular Wholesale" value={availableNumber(summary.totalSelected, true)} detail={`${monthLabel(month)} · HMA + GMA + KUS regular vehicles`} />
        <MetricCard label="Brands using fallback" value={availableNumber(summary.brandsUsingFallback)} detail="API-published source and fallback counts" />
        <MetricCard label="Models using fallback" value={availableNumber(summary.modelsUsingFallback)} detail="Across HMA, GMA, and KUS" />
      </div>

      <div className={styles.wholesaleBrandGrid}>
        {summary.rows.map((row) => <article className={styles.wholesaleBrandCard} key={row.brand}>
          <div className={styles.wholesaleBrandHeader}><strong>{row.brand}</strong><Tag color={sourceColor(row.source)}>{row.source}</Tag></div>
          <span>Selected Regular Wholesale</span>
          <b>{availableNumber(row.selected, true)}{row.selected === null ? "" : " vehicles"}</b>
          <div><span>Models using fallback</span><strong>{availableNumber(row.fallbackModelCount)}</strong></div>
        </article>)}
      </div>
    </section>

    <section className={styles.methodCard}>
      <div className={styles.sectionHeading}>
        <div><span>Governed selection logic</span><h2>How Selected Regular Wholesale Is Built</h2></div>
        <Tag color="blue">Model by model</Tag>
      </div>
      <div className={styles.logicFlow}>
        <strong>For each Brand + Model + Month</strong>
        <i aria-hidden="true">→</i>
        <span>Sponsor Plan available?</span>
        <i aria-hidden="true">→</i>
        <div className={styles.logicBranches}>
          <div><b>Yes</b><span>Use Sponsor Plan</span></div>
          <div><b>No</b><span>Use Internal Forecast fallback</span></div>
        </div>
        <i aria-hidden="true">→</i>
        <strong>Sum selected model-level values to Brand<br />= Governed Selected Regular Wholesale</strong>
      </div>
      <ul className={styles.logicNotes}>
        <li>Selection happens model by model, not once for the entire brand.</li>
        <li>An explicit Sponsor Plan zero remains zero.</li>
        <li>Internal fallback is used only when Sponsor Plan is missing.</li>
        <li>Kia Fleet is excluded from regular Wholesale.</li>
      </ul>
    </section>

    <section className={styles.callout}>
      <SafetyCertificateOutlined />
      <div><h3>Fleet is governed separately</h3><p>Kia Fleet is not included in Selected Regular Wholesale. Fleet vehicle volume and the Kia Fleet CFM adjustment are governed separately.</p></div>
    </section>

    <Collapse className={styles.sourceCollapse} items={[{
      key: "source-comparison",
      label: "Source comparison and methodology",
      children: <div>
        <p className={styles.sourceNote}>This shows what the internal model forecasts for the full brand. It is not added in full to the Sponsor Plan and is not the selected total.</p>
        <Table columns={columns} dataSource={summary.rows} rowKey="brand" pagination={false} scroll={{ x: 1200 }} size="small" />
      </div>,
    }]} />
  </div>;
}
