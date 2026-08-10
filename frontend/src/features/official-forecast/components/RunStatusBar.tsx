import { CheckCircleFilled, ReloadOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";

import type { GovernedRunMetadata } from "../contract";
import { dateLabel, formatPercent } from "../formatters";
import styles from "./OfficialUi.module.css";

function shortRunId(runId: string) {
  const releaseSuffix = runId.toLowerCase().lastIndexOf("-r");
  const withoutRelease = releaseSuffix > 0 ? runId.slice(0, releaseSuffix) : runId;
  return withoutRelease.split("-").at(-1) ?? withoutRelease;
}

function approvedStatus(confidence: string) {
  return `${confidence.charAt(0).toUpperCase()}${confidence.slice(1)} approved`;
}

export default function RunStatusBar({
  meta,
  loading,
  onRefresh,
  confidence,
  h1Wape,
}: {
  meta: GovernedRunMetadata;
  loading: boolean;
  onRefresh: () => void;
  confidence?: string;
  h1Wape?: number | null;
}) {
  return (
    <section className={`${styles.metaStrip} ${h1Wape !== undefined ? styles.metaStripWithWape : ""}`} aria-label="Approved run status">
      <div className={styles.runStatus}>
        <div className={styles.runIdentity}>
          <CheckCircleFilled />
          <span><strong>Approved forecast</strong><Tooltip title={meta.run_id}><small>Run {shortRunId(meta.run_id)}</small></Tooltip></span>
        </div>
        <Tooltip title="Checks whether the Forecast API has a newer approved run. It does not run models or approve results.">
          <Button
            className={styles.refreshButton}
            size="small"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={onRefresh}
          >
            Check for newer approved run
          </Button>
        </Tooltip>
      </div>
      <div><span>Actual data through</span><strong>{dateLabel(meta.actual_data_through)}</strong></div>
      <div><span>Registry</span><strong>{meta.registry_version}</strong></div>
      <div><span>{confidence ? "Forecast status" : "Schema"}</span><strong>{confidence ? approvedStatus(confidence) : meta.schema_version}</strong></div>
      {h1Wape !== undefined ? <div><span>H1 WAPE</span><strong>{formatPercent(h1Wape)}</strong></div> : null}
    </section>
  );
}
