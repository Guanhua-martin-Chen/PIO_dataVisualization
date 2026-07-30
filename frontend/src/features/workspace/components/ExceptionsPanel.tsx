"use client";

import { Button, Card, Col, Empty, Row, Spin, Statistic, Table, Tag, Typography } from "antd";

import type { ForecastCenterPayload } from "../../../app/shared";

const { Paragraph, Text } = Typography;

type ForecastException = ForecastCenterPayload["forecastExceptions"][number];

type ExceptionsPanelProps = {
  data: ForecastCenterPayload | null;
  loading: boolean;
  onRefresh: () => void;
};

function severityColor(severity: ForecastException["severity"]) {
  if (severity === "high") return "red";
  if (severity === "medium") return "gold";
  return "blue";
}

export default function ExceptionsPanel({ data, loading, onRefresh }: ExceptionsPanelProps) {
  const exceptions = data?.forecastExceptions ?? [];
  const highCount = exceptions.filter((item) => item.severity === "high").length;
  const monthlyCount = exceptions.filter((item) => !item.seriesLevel).length;

  return (
    <Spin spinning={loading}>
      <div className="tab-stack">
        <Card className="content-card">
          <div className="major-tab-header">
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Forecast Exceptions</div>
              <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                Governed review queue from the same Forecast Center payload shown on the Forecast
                tab. Evidence is cutoff-safe and includes a reason code and suggested planner action.
              </Paragraph>
            </div>
            <Button type="primary" onClick={onRefresh}>Refresh governed forecast</Button>
          </div>
          {data ? (
            <div className="health-grid" style={{ marginTop: 16 }}>
              <div>
                <span className="health-label">Source hash</span>
                <Text copyable={{ text: data.summary.modelGovernance.sourceHash }}>
                  {data.summary.modelGovernance.sourceHash}
                </Text>
              </div>
              <div>
                <span className="health-label">Training cutoff</span>
                <strong>{data.summary.modelGovernance.trainingCutoff}</strong>
              </div>
            </div>
          ) : null}
        </Card>

        {data ? (
          <>
            <Row gutter={[18, 18]}>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Review items" value={exceptions.length} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="High severity" value={highCount} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Forecast-month findings" value={monthlyCount} /></Card></Col>
              <Col xs={12} lg={6}><Card className="metric-card"><Statistic title="Reconciliation" value={data.summary.reconciliation.status} /></Card></Col>
            </Row>
            <Card className="content-card" title="Governed review queue">
              <Table
                size="small"
                rowKey="exceptionId"
                dataSource={exceptions}
                pagination={{ pageSize: 15, hideOnSinglePage: true }}
                scroll={{ x: 1450 }}
                columns={[
                  {
                    title: "Severity",
                    dataIndex: "severity",
                    key: "severity",
                    width: 110,
                    render: (value: ForecastException["severity"]) => (
                      <Tag color={severityColor(value)}>{value.toUpperCase()}</Tag>
                    ),
                  },
                  {
                    title: "Reason code",
                    dataIndex: "reasonCode",
                    key: "reasonCode",
                    width: 230,
                    render: (value: string) => <Text code>{value}</Text>,
                  },
                  { title: "Scope", dataIndex: "scope", key: "scope", width: 120 },
                  { title: "Series", dataIndex: "seriesKey", key: "seriesKey", width: 290, ellipsis: true },
                  {
                    title: "Forecast month",
                    dataIndex: "forecastMonth",
                    key: "forecastMonth",
                    width: 140,
                    render: (value: string | null, record: ForecastException) =>
                      record.seriesLevel ? "Series-level" : value ?? "—",
                  },
                  {
                    title: "Evidence",
                    dataIndex: "evidence",
                    key: "evidence",
                    width: 340,
                    render: (value: Record<string, unknown>) => (
                      <Text>{JSON.stringify(value)}</Text>
                    ),
                  },
                  {
                    title: "Suggested action",
                    dataIndex: "suggestedAction",
                    key: "suggestedAction",
                    width: 340,
                  },
                ]}
              />
            </Card>
          </>
        ) : (
          <Card className="content-card">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="Open Exceptions to load the shared governed Forecast Center result."
            />
          </Card>
        )}
      </div>
    </Spin>
  );
}
