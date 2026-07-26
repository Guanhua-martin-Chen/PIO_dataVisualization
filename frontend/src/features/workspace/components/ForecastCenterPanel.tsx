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
  minMonthlyVolume: number;
  onMetricChange: (metric: ForecastMetric) => void;
  onLevelChange: (level: ForecastLevel) => void;
  onModelStrategyChange: (strategy: string) => void;
  onWorkingDaysChange: (value: boolean) => void;
  onSeasonalityChange: (value: boolean) => void;
  onTariffImpactChange: (value: number) => void;
  onMinMonthlyVolumeChange: (value: number) => void;
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
  minMonthlyVolume,
  onMetricChange,
  onLevelChange,
  onModelStrategyChange,
  onWorkingDaysChange,
  onSeasonalityChange,
  onTariffImpactChange,
  onMinMonthlyVolumeChange,
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
  const hmaAnchor = data?.brandRecords.find((record) => record.brand === "HMA");

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
            <Space.Compact block>
              <InputNumber
                min={0}
                value={minMonthlyVolume}
                onChange={(value) => onMinMonthlyVolumeChange(Number(value ?? 0))}
                style={{ width: "100%" }}
              />
              <Input value="min avg qty/month" readOnly style={{ width: 170 }} />
            </Space.Compact>
            <Button type="primary" onClick={onRun}>Generate forecast</Button>
          </div>
          <Paragraph className="workspace-copy" style={{ marginTop: 12, marginBottom: 0 }}>
            HMA, GMA, and KUS are the official forecast anchors. Model and PLC values reconcile exactly to the parent.
            HMA, GMA, and KUS use dealer/non-fleet wholesale denominators under the current business rule; fleet is excluded.
            IONIQ variants remain separate model entities.
          </Paragraph>
        </Card>

        {data ? (
          <>
            <Row gutter={[18, 18]}>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Backtest accuracy (all anchors)" value={data.summary.accuracyPct ?? "N/A"} suffix={data.summary.accuracyPct === null ? "" : "%"} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Weighted WAPE" value={data.summary.weightedWape === null ? "N/A" : (data.summary.weightedWape * 100).toFixed(1)} suffix={data.summary.weightedWape === null ? "" : "%"} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Displayed series" value={data.summary.seriesCount} /></Card></Col>
              <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Hierarchy check" value={data.summary.reconciliation.status} /></Card></Col>
            </Row>

            <Card className="content-card" title="Accuracy scope and interpretation">
              <div className="summary-stack">
                <div className="summary-row"><span className="summary-dot" /><span><strong>Target:</strong> {data.summary.accuracyScope.target}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span><strong>Evaluated grain:</strong> {data.summary.accuracyScope.evaluatedGrain}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span>{data.summary.accuracyScope.overallFormula}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span>{data.summary.accuracyScope.childPolicy}</span></div>
              </div>
              <Table
                style={{ marginTop: 16 }}
                size="small"
                pagination={false}
                rowKey="brand"
                dataSource={data.brandRecords}
                columns={[
                  { title: "Official anchor", dataIndex: "brand", key: "brand" },
                  { title: "Selected model", dataIndex: "selectedModel", key: "selectedModel" },
                  { title: "History months", dataIndex: "historyMonths", key: "historyMonths", align: "right" as const },
                  { title: "Independent test points", dataIndex: "backtestPoints", key: "backtestPoints", align: "right" as const },
                  {
                    title: "Anchor WAPE",
                    dataIndex: "wape",
                    key: "wape",
                    align: "right" as const,
                    render: (value: number | null) => value === null || value === undefined ? "N/A" : `${(value * 100).toFixed(2)}%`,
                  },
                  {
                    title: "Anchor accuracy",
                    dataIndex: "accuracyPct",
                    key: "accuracyPct",
                    align: "right" as const,
                    render: (value: number | null) => value === null || value === undefined ? "N/A" : `${value.toFixed(2)}%`,
                  },
                ]}
              />
              {hmaAnchor && hmaAnchor.wape !== null && hmaAnchor.wape !== undefined && hmaAnchor.wape >= 0.10 ? (
                <Alert
                  style={{ marginTop: 16 }}
                  type="warning"
                  showIcon
                  message={`HMA anchor diagnostic: ${hmaAnchor.selectedModel} did not follow recent HMA level/mix changes closely enough`}
                  description="This is a brand-anchor time-series error, not a Model/PLC reconciliation failure. A shorter history window may adapt faster, but it also weakens annual seasonality evidence and reduces independent test points."
                />
              ) : null}
            </Card>

            <Alert
              type={data.summary.nowcastMonths.length ? "warning" : "info"}
              showIcon
              message={`${data.summary.metricLabel}: ${data.summary.forecastMonths.join(", ")}`}
              description={data.summary.periodExplanation}
            />

            <Card className="content-card" title="Business-policy validation">
              <Table
                size="small"
                pagination={false}
                rowKey="check"
                dataSource={data.summary.businessValidation}
                columns={[
                  { title: "Check", dataIndex: "check", key: "check", width: 220 },
                  {
                    title: "Status",
                    dataIndex: "status",
                    key: "status",
                    width: 100,
                    render: (value: "PASS" | "WARN" | "FAIL") => (
                      <Tag color={value === "PASS" ? "green" : value === "WARN" ? "gold" : "red"}>{value}</Tag>
                    ),
                  },
                  { title: "Evidence", dataIndex: "detail", key: "detail" },
                ]}
              />
              <Paragraph className="workspace-copy" style={{ marginTop: 12, marginBottom: 0 }}>
                Fleet is not added to PIO quantity or revenue. Low-volume and stopped series receive no normal allocation;
                new/reintroduced models use a recent run-rate proxy. Any unavoidable remainder is labeled Planner review residual.
              </Paragraph>
            </Card>

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
                  { title: "Route", dataIndex: "allocationRoute", key: "allocationRoute", render: (value: string) => value || "Official anchor" },
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
