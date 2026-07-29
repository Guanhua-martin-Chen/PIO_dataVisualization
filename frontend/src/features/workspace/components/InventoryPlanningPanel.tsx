"use client";

import { Alert, Button, Card, Empty, Spin, Table, Tag, Typography } from "antd";

import type { ForecastCenterPayload, ForecastCenterRecord } from "../../../app/shared";

const { Paragraph } = Typography;

function forecastPoints(record: ForecastCenterRecord) {
  return record.forecast
    .map((point) => `${point.month}: ${Math.round(point.value).toLocaleString()} accessory units`)
    .join(" | ");
}

type InventoryPlanningPanelProps = {
  data: ForecastCenterPayload | null;
  loading: boolean;
  onRefresh: () => void;
};

export default function InventoryPlanningPanel({ data, loading, onRefresh }: InventoryPlanningPanelProps) {
  return (
    <Spin spinning={loading}>
      <div className="tab-stack">
        <Card className="content-card">
          <div className="major-tab-header">
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Inventory Planning</div>
              <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                Experimental planning preview from a separate governed PIO Quantity forecast at Model × PLC grain.
                Opening this page never replaces the main Forecast result.
              </Paragraph>
            </div>
            <Button type="primary" onClick={onRefresh}>Refresh Planning Preview</Button>
          </div>
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="Experimental demand preview — not a reorder recommendation"
            description="Current stock, on-order quantities, lead times, and exact-part reorder recommendations await governed PIS_PNO inventory inputs. No legacy WAPE or risk fallback is presented as governed."
          />
        </Card>

        {data ? (
          <Card
            className="content-card"
            title="Reconciled accessory-unit demand preview"
            extra={<Tag color={data.summary.reconciliation.status === "PASS" ? "green" : "red"}>{data.summary.reconciliation.status}</Tag>}
          >
            <Table
              size="small"
              rowKey="seriesKey"
              dataSource={data.records}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              scroll={{ x: 1200 }}
              columns={[
                { title: "Brand", dataIndex: "brandName", key: "brandName", width: 190, render: (value: string, record: ForecastCenterRecord) => value || record.brand },
                { title: "Model", dataIndex: "modelName", key: "modelName", width: 180 },
                { title: "PLC", dataIndex: "plc", key: "plc", width: 150 },
                { title: "Allocation route", dataIndex: "allocationRoute", key: "allocationRoute", width: 180 },
                {
                  title: "Next demand (accessory units)",
                  dataIndex: "nextForecast",
                  key: "nextForecast",
                  align: "right" as const,
                  width: 210,
                  render: (value: number) => `${Math.round(value).toLocaleString()} accessory units`,
                },
                {
                  title: "Point forecast months",
                  key: "forecast",
                  width: 430,
                  render: (_: unknown, record: ForecastCenterRecord) => forecastPoints(record),
                },
              ]}
            />
          </Card>
        ) : (
          <Card className="content-card">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Open Inventory Planning to load its governed quantity preview." />
          </Card>
        )}
      </div>
    </Spin>
  );
}
