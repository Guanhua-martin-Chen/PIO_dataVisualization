"use client";

import {
  CheckCircleFilled,
  CloseCircleFilled,
  LockOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Input, Modal, Progress, Tag } from "antd";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import OfficialNavigation from "../official-forecast/OfficialNavigation";
import { ForecastRequestError } from "../official-forecast/api";
import {
  approveForecastUpdate,
  createForecastUpdate,
  getForecastUpdate,
  runForecastUpdate,
} from "./api";
import type { ForecastUpdateJob } from "./contract";
import styles from "./ForecastUpdatePage.module.css";

type Role = "capstone" | "hma_plan" | "gma_plan" | "kia_plan";

const roles: Array<{ role: Role; label: string; help: string }> = [
  {
    role: "capstone",
    label: "CapStone / PIO",
    help: "PIO Sales, PLC Legend, Vehicle Wholesale, historical Wholesale, and Working Days sheets.",
  },
  {
    role: "hma_plan",
    label: "HMA Plan",
    help: "Total Non-Fleet model-level Wholesale Distribution plan.",
  },
  {
    role: "gma_plan",
    label: "GMA Plan",
    help: "TOTAL (Non-Fleet) model-level Wholesale plan.",
  },
  {
    role: "kia_plan",
    label: "Kia Plan",
    help: "Dealer Wholesale TTL model plan; Fleet remains separately governed.",
  },
];

const statusCopy: Record<string, { label: string; color: string }> = {
  validated: { label: "Validated", color: "blue" },
  validation_failed: { label: "Validation failed", color: "red" },
  queued: { label: "Queued", color: "processing" },
  running: { label: "Pipeline running", color: "processing" },
  qa_failed: { label: "QA failed", color: "red" },
  awaiting_approval: { label: "Ready for approval", color: "gold" },
  publishing: { label: "Publishing", color: "processing" },
  published: { label: "Published", color: "green" },
  failed: { label: "Pipeline failed", color: "red" },
};

const operatorCodeStorageKey = "pio-forecast-update-operator-code";

function errorMessage(reason: unknown) {
  if (reason instanceof ForecastRequestError) return reason.message;
  if (reason instanceof Error) return reason.message;
  return "The protected forecast update request failed.";
}

export default function ForecastUpdatePage() {
  const [token, setToken] = useState("");
  const [files, setFiles] = useState<Partial<Record<Role, File>>>({});
  const [job, setJob] = useState<ForecastUpdateJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const allFilesSelected = roles.every(({ role }) => files[role]);
  const active = Boolean(job && ["queued", "running", "publishing"].includes(job.status));

  useEffect(() => {
    setToken(window.sessionStorage.getItem(operatorCodeStorageKey) ?? "");
  }, []);

  useEffect(() => {
    if (!active || !job || !token) return;
    const timer = window.setInterval(() => {
      getForecastUpdate(token, job.job_id)
        .then(({ job: next }) => setJob(next))
        .catch((reason: unknown) => setError(errorMessage(reason)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, job, token]);

  const status = useMemo(
    () => job ? statusCopy[job.status] ?? { label: job.status, color: "default" } : null,
    [job],
  );

  async function validateUploads() {
    if (!allFilesSelected || !token.trim()) return;
    setBusy(true);
    setError("");
    try {
      const selected = Object.fromEntries(
        roles.map(({ role }) => [role, files[role] as File]),
      ) as Record<Role, File>;
      setJob((await createForecastUpdate(token.trim(), selected)).job);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function startPipeline() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      setJob((await runForecastUpdate(token.trim(), job.job_id)).job);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function confirmApproval() {
    if (!job) return;
    Modal.confirm({
      title: "Approve and publish this forecast?",
      content: "This will atomically make the QA-passing Draft the latest approved run. The Dashboard and Sponsor workbook will update together.",
      okText: "Approve and publish",
      cancelText: "Continue reviewing",
      onOk: async () => {
        setBusy(true);
        setError("");
        try {
          setJob((await approveForecastUpdate(token.trim(), job.job_id)).job);
        } catch (reason) {
          setError(errorMessage(reason));
        } finally {
          setBusy(false);
        }
      },
    });
  }

  return (
    <main className={styles.page}>
      <OfficialNavigation />
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Protected forecast operations</span>
          <h1>Update Forecast</h1>
          <p>Upload four governed source roles, run the existing forecasting pipeline, review QA, and approve one immutable release.</p>
        </div>
        <div className={styles.workflowNote}>
          Upload → Validate → Run Pipeline → QA → Review / Approve → Dashboard + Sponsor XLSX
        </div>
      </section>

      {error ? <Alert type="error" showIcon closable onClose={() => setError("")} message={error} style={{ marginBottom: 14 }} /> : null}

      <section className={styles.grid}>
        <Card className={styles.card} title="1. Upload and validate">
          <div className={styles.tokenRow}>
            <Input.Password
              prefix={<LockOutlined />}
              value={token}
              onChange={(event) => {
                const nextToken = event.target.value;
                setToken(nextToken);
                if (nextToken) {
                  window.sessionStorage.setItem(operatorCodeStorageKey, nextToken);
                } else {
                  window.sessionStorage.removeItem(operatorCodeStorageKey);
                }
              }}
              placeholder="Operator access code"
              autoComplete="off"
            />
            <Tag color="default">Remembered in this browser tab</Tag>
          </div>
          <div className={styles.fileGrid}>
            {roles.map(({ role, label, help }) => (
              <label className={styles.fileBox} key={role}>
                <span className={styles.fileRole}>{label}</span>
                <p>{help}</p>
                <input
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    setFiles((current) => ({ ...current, [role]: file }));
                  }}
                />
              </label>
            ))}
          </div>
          <div className={styles.actions}>
            <Button
              type="primary"
              icon={<UploadOutlined />}
              disabled={!allFilesSelected || !token.trim() || active}
              loading={busy && !job}
              onClick={validateUploads}
            >
              Upload and validate
            </Button>
            <Button
              icon={<PlayCircleOutlined />}
              disabled={job?.status !== "validated" || active}
              loading={busy && job?.status === "validated"}
              onClick={startPipeline}
            >
              Run governed pipeline
            </Button>
          </div>
          <p className={styles.safety}>
            Filenames may vary; governed sheet, field, and source-role structure must pass. Uploads remain private runtime files and are never committed. A failed upload, pipeline, or QA run leaves the previous approved Dashboard unchanged.
          </p>
        </Card>

        <Card className={styles.card} title="2. QA, review, and approve">
          {!job ? (
            <div className={styles.empty}>
              <div><SafetyCertificateOutlined style={{ fontSize: 32, marginBottom: 10 }} /><br />Validated job status will appear here.</div>
            </div>
          ) : (
            <>
              <div className={styles.statusHeader}>
                <div><span className={styles.eyebrow}>Job {job.job_id.slice(0, 8)}</span><br /><strong>{job.progress.message}</strong></div>
                {status ? <Tag color={status.color}>{status.label}</Tag> : null}
              </div>
              <Progress percent={job.progress.percent} status={job.status.includes("failed") ? "exception" : job.status === "published" ? "success" : "active"} />

              <div className={styles.validationList}>
                {job.files.map((file) => (
                  <div className={styles.validationItem} key={file.role}>
                    {file.valid ? <CheckCircleFilled style={{ color: "#16834b" }} /> : <CloseCircleFilled style={{ color: "#bd3c43" }} />}
                    <div><strong>{roles.find((item) => item.role === file.role)?.label}</strong><br /><span>{file.filename}<br />{file.summary}</span></div>
                    <Tag color={file.valid ? "green" : "red"}>{file.valid ? "Valid" : "Blocked"}</Tag>
                  </div>
                ))}
              </div>

              {job.draft ? (
                <div className={styles.draft}>
                  <div><small>Actual data through</small><strong>{job.draft.actual_data_through}</strong></div>
                  <div><small>Forecast window</small><strong>{job.draft.forecast_start} – {job.draft.forecast_end}</strong></div>
                  <div><small>Registry</small><strong>{job.draft.registry_version}</strong></div>
                  <div><small>Sponsor workbook</small><strong>{job.draft.sponsor_workbook_filename}</strong></div>
                </div>
              ) : null}

              {job.qa ? (
                <div className={styles.qaList}>
                  <span className={styles.sectionTitle}>Release QA · {job.qa.checks_passed}/{job.qa.checks_total} passed</span>
                  {job.qa.checks.map((check) => (
                    <div className={styles.qaItem} key={check.check}>
                      {check.passes ? <CheckCircleFilled style={{ color: "#16834b" }} /> : <CloseCircleFilled style={{ color: "#bd3c43" }} />}
                      <strong>{check.check.replaceAll("_", " ")}</strong>
                      <Tag color={check.passes ? "green" : "red"}>{check.passes ? "Pass" : "Fail"}</Tag>
                    </div>
                  ))}
                </div>
              ) : null}

              {job.error ? <Alert type="error" showIcon message={job.error} style={{ marginTop: 14 }} /> : null}
              <div className={styles.actions}>
                <Button
                  type="primary"
                  icon={<SafetyCertificateOutlined />}
                  disabled={job.status !== "awaiting_approval"}
                  loading={busy || job.status === "publishing"}
                  onClick={confirmApproval}
                >
                  Approve and publish
                </Button>
                {job.status === "published" ? <Link href="/"><Button>Open updated Dashboard</Button></Link> : null}
              </div>
            </>
          )}
        </Card>
      </section>
    </main>
  );
}
