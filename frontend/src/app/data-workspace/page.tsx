"use client";

import {
  AreaChartOutlined,
  ArrowLeftOutlined,
  FileExcelOutlined,
  HistoryOutlined,
  PartitionOutlined,
  TableOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Card, Spin, Typography, Upload, message } from "antd";
import type { UploadProps } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "../shared";

const { Dragger } = Upload;
const { Title, Paragraph } = Typography;

type WorkbookHistory = {
  id: string;
  filename: string;
  sheetNames: string[];
  defaultSheet: string | null;
  uploadedAt: string;
};

const capabilityCards = [
  {
    icon: <UploadOutlined />,
    title: "Excel-native intake",
    copy: "Bring in workbook exports for exploratory analysis without changing the approved forecast run.",
  },
  {
    icon: <TableOutlined />,
    title: "Server-side data table",
    copy: "Browse large sheets with search, pagination, and business-aware column order.",
  },
  {
    icon: <PartitionOutlined />,
    title: "Field classification",
    copy: "Separate time, vehicle, part, quantity, revenue, and support columns automatically.",
  },
  {
    icon: <AreaChartOutlined />,
    title: "Exploratory views",
    copy: "Inspect source structure and data quality without replacing Official Forecast values.",
  },
];

export default function DataWorkspacePage() {
  const router = useRouter();
  const [messageApi, contextHolder] = message.useMessage();
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("Processing workbook…");
  const [history, setHistory] = useState<WorkbookHistory[]>([]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/workbooks`)
      .then((response) => response.json())
      .then((payload: WorkbookHistory[]) => setHistory(payload))
      .catch(() => setHistory([]));
  }, []);

  async function uploadWorkbook(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    setLoading(true);
    setLoadingMessage("Uploading and profiling workbook…");
    try {
      const response = await fetch(`${API_BASE_URL}/api/workbooks/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.json() as { detail?: string };
        throw new Error(payload.detail ?? "Upload failed.");
      }
      const metadata = await response.json() as { workbookId: string };
      messageApi.success("Upload successful. Opening Data Workspace…");
      router.push(`/workspace/${metadata.workbookId}`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Upload failed.");
      setLoading(false);
    }
    return false;
  }

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls",
    multiple: false,
    showUploadList: false,
    beforeUpload: uploadWorkbook,
  };

  return (
    <main className="page-shell">
      {contextHolder}
      <div style={{ marginBottom: 20 }}>
        <Link
          href="/"
          style={{
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            fontWeight: 600,
          }}
        >
          <ArrowLeftOutlined /> Official Forecast
        </Link>
      </div>

      <section className="hero-shell">
        <div className="hero-copy">
          <div className="eyebrow">Separate exploratory area</div>
          <Title className="hero-title">Data Workspace</Title>
          <Paragraph className="hero-paragraph">
            Upload, inspect, filter, and export source workbooks. Activity here does not retrain, replace, or alter the approved Official Forecast run.
          </Paragraph>
          <div className="hero-badges">
            <span>Exploratory only</span>
            <span>Excel intake</span>
            <span>Data-quality review</span>
            <span>Filtered exports</span>
          </div>
        </div>

        <div className="hero-right">
          {capabilityCards.map((card) => (
            <div key={card.title} className="hero-mini-card">
              <div className="hero-mini-icon">{card.icon}</div>
              <div>
                <div className="hero-mini-title">{card.title}</div>
                <div className="hero-mini-copy">{card.copy}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="hero-upload-row">
        <Dragger {...uploadProps} className="upload-panel upload-hero" disabled={loading}>
          <p className="ant-upload-drag-icon"><UploadOutlined /></p>
          <p className="upload-title">Drop an Excel workbook here</p>
          <p className="upload-copy">Supports .xlsx and .xls. The source file remains unchanged.</p>
        </Dragger>

        {history.length > 0 ? (
          <div className="history-list">
            <div className="history-header">
              <HistoryOutlined />
              <span>Recent exploratory files</span>
            </div>
            {history.map((entry) => (
              <button
                key={entry.id}
                className="history-item"
                onClick={() => router.push(`/workspace/${entry.id}`)}
                disabled={loading}
              >
                <FileExcelOutlined className="history-file-icon" />
                <div className="history-item-info">
                  <span className="history-item-name">{entry.filename}</span>
                  <span className="history-item-meta">
                    {entry.sheetNames.length} sheet{entry.sheetNames.length === 1 ? "" : "s"}
                    {" · "}
                    {new Date(entry.uploadedAt).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </span>
                </div>
                <span className="history-item-arrow">→</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {loading ? (
        <div className="loading-shell">
          <Card className="loading-card">
            <Spin size="large" />
            <p className="loading-msg">{loadingMessage}</p>
          </Card>
        </div>
      ) : null}
    </main>
  );
}
