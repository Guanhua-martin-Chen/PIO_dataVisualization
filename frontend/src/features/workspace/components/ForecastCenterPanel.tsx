"use client";

import { DownloadOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";

import type { ForecastCenterPayload, ForecastCenterRecord } from "../../../app/shared";
import { formatMetric } from "../../../app/shared";

const { Paragraph } = Typography;

export type ForecastMetric = "revenue" | "quantity" | "wholesale_quantity";
export type ForecastLevel = "brand" | "model" | "plc" | "model_plc";

type ForecastCenterPanelProps = {
  data: ForecastCenterPayload | null;
  loading: boolean;
  metric: ForecastMetric;
  level: ForecastLevel;
  modelStrategy: string;
  useWorkingDays: boolean;
  useSeasonality: boolean;
  tariffImpactPct: number;
  onMetricChange: (metric: ForecastMetric) => void;
  onLevelChange: (level: ForecastLevel) => void;
  onModelStrategyChange: (strategy: string) => void;
  onWorkingDaysChange: (value: boolean) => void;
  onSeasonalityChange: (value: boolean) => void;
  onTariffImpactChange: (value: number) => void;
  onRun: () => void;
  onExportCsv: () => void;
  onExportXlsx: () => void;
};

function formatValue(value: number, metric: ForecastMetric) {
  if (metric === "revenue") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value);
  }
  return formatMetric(value);
}

function forecastText(record: ForecastCenterRecord, metric: ForecastMetric) {
  return record.forecast
    .map((item) => `${item.month} ${item.forecastType}: ${formatValue(item.value, metric)}`)
    .join(" | ");
}

export default function ForecastCenterPanel({
  data,
  loading,
  metric,
  level,
  modelStrategy,
  useWorkingDays,
  useSeasonality,
  tariffImpactPct,
  onMetricChange,
  onLevelChange,
  onModelStrategyChange,
  onWorkingDaysChange,
  onSeasonalityChange,
  onTariffImpactChange,
  onRun,
  onExportCsv,
  onExportXlsx,
}: ForecastCenterPanelProps) {
  const levelOptions = [
    { label: "Brand", value: "brand" },
    { label: "Model", value: "model" },
    ...(metric === "wholesale_quantity"
      ? []
      : [
          { label: "Top 10 PLC", value: "plc" },
          { label: "Model × Top 10 PLC", value: "model_plc" },
        ]),
  ];

  return (
    <Spin spinning={loading}>
      <div className="tab-stack">
        <Card
          className="content-card"
          title="Forecast Center controls"
          extra={(
            <Space wrap>
              <Button icon={<DownloadOutlined />} onClick={onExportCsv}>Current view CSV</Button>
              <Button type="primary" icon={<DownloadOutlined />} onClick={onExportXlsx}>SOP Excel</Button>
            </Space>
          )}
        >
          <div className="toolbar-grid">
            <Select
              value={metric}
              options={[
                { label: "Revenue", value: "revenue" },
                { label: "PIO Quantity", value: "quantity" },
                { label: "Wholesale Quantity", value: "wholesale_quantity" },
              ]}
              onChange={onMetricChange}
            />
            <Select value={level} options={levelOptions} onChange={onLevelChange} />
            <Select
              value={modelStrategy}
              onChange={onModelStrategyChange}
              options={[
                { label: "Auto: baselines + drivers", value: "auto" },
                { label: "Auto: statistical baselines only", value: "baseline_auto" },
                { label: "Driver regression (OLS)", value: "driver_adjusted_regression" },
                { label: "Additive ETS", value: "ets_additive" },
                { label: "Naive last", value: "naive_last" },
                { label: "Mean", value: "mean" },
                { label: "Weighted moving average", value: "weighted_moving_average" },
                { label: "Trailing 12-month mean", value: "trailing_12_mean" },
                { label: "Damped trend", value: "damped_trend" },
                { label: "Seasonal naive", value: "seasonal_naive" },
                { label: "Seasonal mean", value: "seasonal_mean" },
                { label: "Croston SBA", value: "croston_sba" },
              ]}
            />
            <Select
              value={useWorkingDays}
              options={[{ label: "Working Days on", value: true }, { label: "Working Days off", value: false }]}
              onChange={onWorkingDaysChange}
            />
            <Select
              value={useSeasonality}
              options={[{ label: "Seasonality on", value: true }, { label: "Seasonality off", value: false }]}
              onChange={onSeasonalityChange}
            />
            <Space.Compact block>
              <InputNumber
                min={-100}
                max={100}
                value={tariffImpactPct}
                disabled={metric === "wholesale_quantity"}
                onChange={(value) => onTariffImpactChange(Number(value ?? 0))}
                style={{ width: "100%" }}
              />
              <Input value="% tariff demand impact" readOnly style={{ width: 180 }} />
            </Space.Compact>
            <Button type="primary" onClick={onRun}>Generate forecast</Button>
          </div>
          <Paragraph className="workspace-copy" style={{ marginTop: 12, marginBottom: 0 }}>
            Brand is the official forecast anchor. Model and PLC values are transparent allocations that reconcile exactly to the parent.
            H represents Hyundai and Genesis combined; K represents Kia. Accessories use the 21 PLC categories supplied in the workbook.
          </Paragraph>
        </Card>

        {data ? (
          <>
            <Row gutter={[18, 18]}>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Backtest accuracy" value={data.summary.accuracyPct ?? "N/A"} suffix={data.summary.accuracyPct === null ? "" : "%"} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Weighted WAPE" value={data.summary.weightedWape === null ? "N/A" : (data.summary.weightedWape * 100).toFixed(1)} suffix={data.summary.weightedWape === null ? "" : "%"} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Displayed series" value={data.summary.seriesCount} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Hierarchy check" value={data.summary.reconciliation.status} /></Card></Col>
            </Row>

            <Alert
              type={data.summary.nowcastMonths.length ? "warning" : "info"}
              showIcon
              message={`${data.summary.metricLabel}: ${data.summary.forecastMonths.join(", ")}`}
              description={data.summary.periodExplanation}
            />

            <Card className="content-card" title="Model formulas and allocation logic">
              <Table
                size="small"
                pagination={false}
                rowKey="name"
                dataSource={data.summary.formulaCatalog}
                columns={[
                  { title: "Step", dataIndex: "name", key: "name", width: 190 },
                  { title: "Formula", dataIndex: "formula", key: "formula", width: 420 },
                  { title: "When it is used", dataIndex: "logic", key: "logic" },
                ]}
                scroll={{ x: 900 }}
              />
            </Card>

            {metric !== "wholesale_quantity" ? (
              <Card className="content-card" title="Top 10 PLC accessories by historical revenue">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="seriesKey"
                  dataSource={data.topAccessories}
                  columns={[
                    { title: "Rank", dataIndex: "rank", key: "rank", width: 70 },
                    { title: "PLC", dataIndex: "plc", key: "plc" },
                    {
                      title: "Historical revenue share",
                      dataIndex: "historyRevenueSharePct",
                      key: "historyRevenueSharePct",
                      align: "right" as const,
                      render: (value: number) => `${value.toFixed(1)}%`,
                    },
                    {
                      title: "Forecast",
                      key: "forecast",
                      render: (_: unknown, record: ForecastCenterRecord) => forecastText(record, metric),
                    },
                  ]}
                  scroll={{ x: 900 }}
                />
              </Card>
            ) : null}

            <Card
              className="content-card"
              title="Reconciled forecast results"
              extra={<Tag color={data.summary.reconciliation.status === "PASS" ? "green" : "red"}>{data.summary.reconciliation.status}</Tag>}
            >
              <Table
                size="small"
                rowKey="seriesKey"
                pagination={{ pageSize: 20, hideOnSinglePage: true }}
                dataSource={data.records}
                columns={[
                  { title: "Brand", dataIndex: "brandName", key: "brandName", render: (value: string, record: ForecastCenterRecord) => value || record.brand },
                  { title: "Model", dataIndex: "modelName", key: "modelName", render: (value: string) => value || "All models" },
                  { title: "PLC", dataIndex: "plc", key: "plc", render: (value: string) => value || "All PLCs" },
                  { title: "Method", dataIndex: "selectedModel", key: "selectedModel" },
                  {
                    title: "Expected unit revenue",
                    dataIndex: "expectedUnitRevenue",
                    key: "expectedUnitRevenue",
                    align: "right" as const,
                    render: (value: number | null) => value ? formatValue(value, "revenue") : "—",
                  },
                  {
                    title: "Next result",
                    dataIndex: "nextForecast",
                    key: "nextForecast",
                    align: "right" as const,
                    render: (value: number) => formatValue(value, metric),
                  },
                  {
                    title: "Brand-anchor WAPE",
                    dataIndex: "wape",
                    key: "wape",
                    align: "right" as const,
                    render: (value: number | null) => value === null || value === undefined ? "Allocated" : `${(value * 100).toFixed(1)}%`,
                  },
                  {
                    title: "Forecast months",
                    key: "forecast",
                    width: 430,
                    render: (_: unknown, record: ForecastCenterRecord) => forecastText(record, metric),
                  },
                ]}
                scroll={{ x: 1350 }}
              />
            </Card>
          </>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Generate a Forecast Center result." />
        )}
      </div>
    </Spin>
  );
}
