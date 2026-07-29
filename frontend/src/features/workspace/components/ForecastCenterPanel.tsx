"use client";

import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
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
  Tooltip,
  Typography,
} from "antd";

import type { ForecastCenterPayload, ForecastCenterRecord } from "../../../app/shared";
import { formatMetric } from "../../../app/shared";

const { Paragraph } = Typography;

export type ForecastMetric = "revenue" | "quantity" | "wholesale_quantity";
export type ForecastLevel = "brand" | "model" | "plc" | "model_plc";

const MODEL_DISPLAY_NAMES: Record<string, string> = {
  auto: "Auto model selection",
  baseline_auto: "Statistical baseline selection",
  reference_portfolio: "Validated reference portfolio",
  ets_additive: "Additive ETS",
  naive_last: "Naive last value",
  working_day_adjusted_seasonal: "Working-day-adjusted seasonal",
  reconciled_allocation: "Reconciled parent allocation",
  new_model_proxy: "New / reintroduced model proxy",
  excluded: "Excluded by lifecycle or volume policy",
  planner_review_residual: "Planner-review residual",
  hw_add_add__heuristic__bias_on__log1p__rolling_24__robust_winsorized:
    "Optimized additive Holt-Winters (robust 24-month log model)",
};

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

function modelDisplayName(modelId: string | null | undefined) {
  if (!modelId) return "N/A";
  return MODEL_DISPLAY_NAMES[modelId] ?? modelId.replaceAll("_", " ");
}

function ModelIdentity({ modelId }: { modelId: string | null | undefined }) {
  if (!modelId) return <>N/A</>;
  return (
    <Tooltip title={`Technical ID: ${modelId}`} placement="topLeft">
      <span
        className="forecast-model-name"
        tabIndex={0}
        aria-label={`${modelDisplayName(modelId)}. Technical ID: ${modelId}`}
      >
        {modelDisplayName(modelId)}
      </span>
    </Tooltip>
  );
}

function metricResultTitle(metric: ForecastMetric) {
  if (metric === "revenue") return "Next forecast revenue (USD)";
  if (metric === "quantity") return "Next forecast installation quantity (accessory units)";
  return "Next forecast wholesale volume (vehicles)";
}

function formatValue(value: number, metric: ForecastMetric) {
  if (metric === "revenue") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value);
  }
  const unit = metric === "quantity" ? "accessory units" : "vehicles";
  return `${formatMetric(value)} ${unit}`;
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
      <div className="tab-stack forecast-center-panel">
        <Card
          className="content-card"
          title="Forecast Center controls"
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
                ...(metric === "revenue"
                  ? [{ label: "Validated reference portfolio", value: "reference_portfolio" }]
                  : []),
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
              disabled={modelStrategy === "reference_portfolio"}
              options={[{ label: "Working Days on", value: true }, { label: "Working Days off", value: false }]}
              onChange={onWorkingDaysChange}
            />
            <Select
              value={useSeasonality}
              disabled={modelStrategy === "reference_portfolio"}
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

            <Collapse
              className="forecast-method-collapse"
              defaultActiveKey={[]}
              items={[
                {
                  key: "method-validation",
                  label: "Method & Validation",
                  children: (
                    <div className="tab-stack">
            <Card className="content-card" title="Accuracy scope and interpretation" variant="borderless">
              <div className="summary-stack">
                <div className="summary-row"><span className="summary-dot" /><span><strong>Target:</strong> {data.summary.accuracyScope.target}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span><strong>Evaluated grain:</strong> {data.summary.accuracyScope.evaluatedGrain}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span>{data.summary.accuracyScope.overallFormula}</span></div>
                <div className="summary-row"><span className="summary-dot" /><span>{data.summary.accuracyScope.childPolicy}</span></div>
              </div>
              <div className="health-grid" style={{ marginTop: 16 }}>
                <div><span className="health-label">Requested Strategy</span><strong><ModelIdentity modelId={data.summary.modelGovernance.requestedStrategy} /></strong></div>
                <div>
                  <span className="health-label">Source hash</span>
                  <Tooltip title={data.summary.modelGovernance.sourceHash} placement="topLeft">
                    <strong className="forecast-technical-value" tabIndex={0}>{data.summary.modelGovernance.sourceHash}</strong>
                  </Tooltip>
                </div>
                <div><span className="health-label">Training cutoff</span><strong>{data.summary.modelGovernance.trainingCutoff}</strong></div>
                <div><span className="health-label">Backtest horizons</span><strong>{data.summary.modelGovernance.backtestHorizons.join(", ")}</strong></div>
                <div><span className="health-label">Fold count</span><strong>{data.summary.modelGovernance.foldCount ?? "Not validated for this source"}</strong></div>
                <div><span className="health-label">WAPE scope</span><strong>{data.summary.modelGovernance.wapeScope}</strong></div>
                <div><span className="health-label">Accuracy proxy</span><strong>{data.summary.modelGovernance.accuracyProxy === null ? "Not validated for this source" : `${(data.summary.modelGovernance.accuracyProxy * 100).toFixed(2)}%`}</strong></div>
                <div><span className="health-label">Reference status</span><strong>{data.summary.modelGovernance.referenceMethodStatus}</strong></div>
              </div>
              <Table
                className="forecast-governance-table"
                style={{ marginTop: 16 }}
                size="small"
                pagination={false}
                rowKey="brand"
                dataSource={data.brandRecords}
                columns={[
                  { title: "Official anchor", dataIndex: "brand", key: "brand", width: 120 },
                  {
                    title: "Requested strategy",
                    dataIndex: "requestedModelStrategy",
                    key: "requestedModelStrategy",
                    width: 190,
                    render: (value: string) => <ModelIdentity modelId={value} />,
                  },
                  {
                    title: "Brand-specific method",
                    dataIndex: "brandSpecificMethod",
                    key: "brandSpecificMethod",
                    width: 240,
                    render: (value: string) => <ModelIdentity modelId={value} />,
                  },
                  {
                    title: "Selected model",
                    dataIndex: "selectedModel",
                    key: "selectedModel",
                    width: 240,
                    render: (value: string) => <ModelIdentity modelId={value} />,
                  },
                  {
                    title: "Backtest model",
                    dataIndex: "backtestModel",
                    key: "backtestModel",
                    width: 240,
                    render: (value: string) => <ModelIdentity modelId={value} />,
                  },
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
                scroll={{ x: 1450 }}
              />
              {hmaAnchor && hmaAnchor.wape !== null && hmaAnchor.wape !== undefined && hmaAnchor.wape >= 0.10 ? (
                <Alert
                  style={{ marginTop: 16 }}
                  type="warning"
                  showIcon
                  message={`HMA anchor diagnostic: ${modelDisplayName(hmaAnchor.selectedModel)} did not follow recent HMA level/mix changes closely enough`}
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

            <Card className="content-card" title="Business-policy validation" variant="borderless">
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

            <Card className="content-card" title="Model formulas and allocation logic" variant="borderless">
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
                    </div>
                  ),
                },
              ]}
            />

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
              title="Forecast Results"
              extra={<Tag color={data.summary.reconciliation.status === "PASS" ? "green" : "red"}>{data.summary.reconciliation.status}</Tag>}
            >
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="Governed point forecast months"
                description="This table contains reconciled point forecasts only. Validated lower and upper intervals are intentionally deferred to PR C."
              />
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
                  {
                    title: "Method",
                    dataIndex: "selectedModel",
                    key: "selectedModel",
                    width: 220,
                    render: (value: string) => <ModelIdentity modelId={value} />,
                  },
                  {
                    title: "Expected unit price (USD per installed accessory unit)",
                    dataIndex: "expectedUnitRevenue",
                    key: "expectedUnitRevenue",
                    hidden: metric !== "revenue",
                    width: 220,
                    align: "right" as const,
                    render: (value: number | null | undefined) =>
                      value === null || value === undefined ? "—" : formatValue(value, "revenue"),
                  },
                  {
                    title: metricResultTitle(metric),
                    dataIndex: "nextForecast",
                    key: "nextForecast",
                    width: 220,
                    align: "right" as const,
                    render: (value: number) => formatValue(value, metric),
                  },
                  {
                    title: "Planning explanation",
                    key: "forecastExplanation",
                    width: 320,
                    render: (_: unknown, record: ForecastCenterRecord) => {
                      const hasExplicitReason =
                        record.forecastEligible === false ||
                        record.allocationRoute?.startsWith("excluded_") ||
                        record.allocationRoute === "planner_review_residual" ||
                        record.allocationRoute === "new_model_proxy";
                      if (!hasExplicitReason) return "—";
                      if (!record.selectionNote && !record.allocationRoute && !record.lifecycleStatus) return "—";
                      return (
                        <div className="forecast-explanation">
                          {record.lifecycleStatus ? <Tag>{record.lifecycleStatus}</Tag> : null}
                          <span>{record.selectionNote || record.allocationRoute}</span>
                        </div>
                      );
                    },
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
                scroll={{ x: 1800 }}
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
