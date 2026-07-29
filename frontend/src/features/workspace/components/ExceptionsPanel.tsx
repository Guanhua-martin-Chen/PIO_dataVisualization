"use client";

import { Alert, Button, Card, Col, Empty, Row, Spin, Statistic, Table, Tag, Typography } from "antd";

import type { AnomalyCenterPayload } from "../../../app/shared";

const { Paragraph } = Typography;

type ExceptionsPanelProps = {
  data: AnomalyCenterPayload | null;
  loading: boolean;
  onRefresh: () => void;
};

export default function ExceptionsPanel({ data, loading, onRefresh }: ExceptionsPanelProps) {
  return (
    <Spin spinning={loading}>
      <div className="tab-stack">
        <Card className="content-card">
          <div className="major-tab-header">
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Exceptions</div>
              <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                Experimental anomaly and signal review over governed PIO_Sales_Data, enriched with every compatible
                Wholesale worksheet. This is historical diagnostic evidence, not a production exception-reason schema.
              </Paragraph>
            </div>
            <Button type="primary" onClick={onRefresh}>Refresh Exceptions</Button>
          </div>
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="Experimental until PR C"
            description="Reason-code parity and governed planner actions are not yet available. Results do not use the selected Data Workspace sheet as their target."
          />
        </Card>

        {data ? (
          <>
            <Row gutter={[18, 18]}>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Scanned parts" value={data.summary.scannedParts} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Surfaced exceptions" value={data.summary.surfacedAlerts} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Structural breaks" value={data.summary.structuralBreaks} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="High-risk diagnostics" value={data.summary.highRiskForecasts} /></Card></Col>
            </Row>
            <Card className="content-card" title="Exception diagnostics">
              <Table
                size="small"
                rowKey="part"
                dataSource={data.records}
                pagination={{ pageSize: 12, hideOnSinglePage: true }}
                scroll={{ x: 1100 }}
                columns={[
                  { title: "Part", dataIndex: "part", key: "part", width: 190 },
                  { title: "Description", dataIndex: "partDescription", key: "partDescription", width: 260, render: (value: string | null) => value || "—" },
                  { title: "Latest month", dataIndex: "latestMonth", key: "latestMonth", width: 120 },
                  { title: "Latest actual", dataIndex: "latestActual", key: "latestActual", align: "right" as const },
                  { title: "Diagnostic next point", dataIndex: "nextForecast", key: "nextForecast", align: "right" as const },
                  { title: "Regime", dataIndex: "regime", key: "regime", render: (value: string) => <Tag>{value}</Tag> },
                  {
                    title: "Diagnostic risk",
                    dataIndex: "forecastRisk",
                    key: "forecastRisk",
                    render: (value: string) => <Tag color={value === "High" ? "red" : value === "Medium" ? "gold" : "blue"}>{value}</Tag>,
                  },
                  { title: "Evidence", dataIndex: "evidence", key: "evidence", width: 360, render: (value: string[]) => value?.join(" ") || "—" },
                ]}
              />
            </Card>
          </>
        ) : (
          <Card className="content-card">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Open Exceptions to run the governed-source diagnostic." />
          </Card>
        )}
      </div>
    </Spin>
  );
}
