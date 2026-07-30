"use client";

import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Row, Space, Table, Tag, Tooltip, Typography } from "antd";

import type { ForecastOutputRunPreview } from "../../../app/shared";

const { Paragraph, Text } = Typography;

type OutputCenterPanelProps = {
  data: ForecastOutputRunPreview | null;
  loading: boolean;
  onPrepare: () => void;
  onDownloadExcel: () => void;
  onDownloadPdf: () => void;
};

function formatNumber(value: number, currency = false) {
  return new Intl.NumberFormat("en-US", {
    style: currency ? "currency" : "decimal",
    currency: currency ? "USD" : undefined,
    maximumFractionDigits: 0,
  }).format(value);
}

export default function OutputCenterPanel({
  data,
  loading,
  onPrepare,
  onDownloadExcel,
  onDownloadPdf,
}: OutputCenterPanelProps) {
  const ready = Boolean(data) && !loading;
  const pdfReady = ready && data?.artifacts.executiveSummaryPdf === "ready";

  return (
    <div className="tab-stack" aria-labelledby="output-center-title">
      <Card
        className="content-card"
        title={<span id="output-center-title">Output Center</span>}
        extra={(
          <Space wrap>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={onPrepare}
            >
              {data ? "Refresh governed run" : "Prepare governed run"}
            </Button>
            <Button
              icon={<DownloadOutlined />}
              disabled={!ready}
              onClick={onDownloadExcel}
            >
              Detailed Forecast / SOP Excel
            </Button>
            <Tooltip
              title={pdfReady ? "" : "PDF requires the governed reportlab server dependency."}
            >
              <span>
                <Button
                  icon={<DownloadOutlined />}
                  disabled={!pdfReady}
                  onClick={onDownloadPdf}
                >
                  Executive Summary PDF
                </Button>
              </span>
            </Tooltip>
          </Space>
        )}
      >
        <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
          Prepare one immutable forecast run for the current filters and settings. Web preview,
          PDF, detailed Excel, and current-view CSV all read that same run and never silently
          rebuild it after expiry or a backend restart.
        </Paragraph>
        <div aria-live="polite" role="status" style={{ marginTop: 12 }}>
          {loading ? "Preparing governed output run." : data
            ? `Run ready: ${data.metadata.runId}`
            : "No governed output run is ready. Downloads are disabled."}
        </div>
      </Card>

      {!data ? (
        <Alert
          type="info"
          showIcon
          message="Prepare a governed output run to enable preview and downloads."
        />
      ) : (
        <>
          <Card className="content-card" title="Run metadata">
            <Row gutter={[18, 18]}>
              <Col xs={24} lg={12}>
                <div className="health-grid">
                  <div>
                    <span className="health-label">Run ID</span>
                    <Text copyable={{ text: data.metadata.runId }}>{data.metadata.runId}</Text>
                  </div>
                  <div>
                    <span className="health-label">Source hash</span>
                    <Text copyable={{ text: data.metadata.sourceHash }}>{data.metadata.sourceHash}</Text>
                  </div>
                  <div><span className="health-label">Cutoff</span><strong>{data.metadata.cutoff}</strong></div>
                  <div><span className="health-label">Created</span><strong>{data.metadata.createdAt}</strong></div>
                </div>
              </Col>
              <Col xs={24} lg={12}>
                <div className="health-grid">
                  <div><span className="health-label">Requested strategy</span><strong>{data.metadata.requestedStrategy}</strong></div>
                  <div><span className="health-label">Revenue effective</span><strong>{data.metadata.effectiveStrategies.revenue}</strong></div>
                  <div><span className="health-label">Quantity effective</span><strong>{data.metadata.effectiveStrategies.quantity}</strong></div>
                  <div><span className="health-label">Wholesale effective</span><strong>{data.metadata.effectiveStrategies.wholesale_quantity}</strong></div>
                </div>
              </Col>
            </Row>
            <Space wrap style={{ marginTop: 16 }}>
              {data.metadata.nowcastPeriods.map((period) => <Tag color="gold" key={`nowcast-${period}`}>{period} Nowcast</Tag>)}
              {data.metadata.forecastPeriods.map((period) => <Tag color="blue" key={`forecast-${period}`}>{period} Forecast</Tag>)}
              {data.reused ? <Tag color="green">Reused complete run</Tag> : <Tag color="purple">New immutable run</Tag>}
            </Space>
          </Card>

          <Card className="content-card" title="Executive Summary preview">
            <Table
              rowKey="month"
              pagination={false}
              dataSource={data.executiveSummary.headlineTotals}
              scroll={{ x: 760 }}
              columns={[
                { title: "Period", dataIndex: "month", key: "month" },
                {
                  title: "Type",
                  dataIndex: "periodType",
                  key: "periodType",
                  render: (value: string) => <Tag color={value === "Nowcast" ? "gold" : "blue"}>{value}</Tag>,
                },
                {
                  title: "Revenue (USD)",
                  dataIndex: "revenue",
                  key: "revenue",
                  align: "right",
                  render: (value: number) => formatNumber(value, true),
                },
                {
                  title: "PIO Quantity (installed accessory units)",
                  dataIndex: "quantity",
                  key: "quantity",
                  align: "right",
                  render: (value: number) => formatNumber(value),
                },
                {
                  title: "Wholesale Quantity (vehicles)",
                  dataIndex: "wholesale_quantity",
                  key: "wholesale_quantity",
                  align: "right",
                  render: (value: number) => formatNumber(value),
                },
              ]}
            />
          </Card>

          <Card className="content-card" title="Reconciliation and Top 10 PLC">
            <Space wrap style={{ marginBottom: 16 }}>
              {Object.entries(data.executiveSummary.reconciliation).map(([metric, check]) => (
                <Tag color={check.status === "PASS" ? "green" : "red"} key={metric}>
                  {metric.replaceAll("_", " ")}: {check.status}
                </Tag>
              ))}
            </Space>
            <Table
              rowKey={(record) => `${record.rank}-${record.plc}`}
              pagination={false}
              size="small"
              dataSource={data.executiveSummary.topPlcs.slice(0, 10)}
              columns={[
                { title: "Rank", dataIndex: "rank", key: "rank", width: 90 },
                { title: "PLC", dataIndex: "plc", key: "plc" },
                {
                  title: "Historical revenue share",
                  dataIndex: "historyRevenueSharePct",
                  key: "historyRevenueSharePct",
                  align: "right",
                  render: (value: number | undefined) => `${Number(value ?? 0).toFixed(1)}%`,
                },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
}
