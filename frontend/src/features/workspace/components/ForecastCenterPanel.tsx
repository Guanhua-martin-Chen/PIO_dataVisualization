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
  onExportXlsx?: () => void;
  currentExportReady?: boolean;
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
  onExportCsv,
  currentExportReady = true,
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
          extra={(
            <Space wrap>
              <Tooltip title={currentExportReady ? "" : "Prepare a governed run in Output Center first."}>
                <span>
                  <Button
                    icon={<DownloadOutlined />}
                    disabled={!currentExportReady}
                    onClick={onExportCsv}
                  >
                    Current view CSV
                  </Button>
                </span>
              </Tooltip>
            </Space>
          )}
        >
          <div className="toolbar-grid">
            <Select
              aria-label="Forecast metric"
              value={metric}
              options={[
                { label: "Revenue", value: "revenue" },
                { label: "PIO Quantity", value: "quantity" },
                { label: "Wholesale Quantity", value: "wholesale_quantity" },
              ]}
              onChange={onMetricChange}
            />
            <Select aria-label="Forecast hierarchy level" value={level} options={levelOptions} onChange={onLevelChange} />
            <Select
              aria-label="Forecast model strategy"
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
              aria-label="Working Days factor"
              value={useWorkingDays}
              disabled={modelStrategy === "reference_portfolio"}
              options={[{ label: "Working Days on", value: true }, { label: "Working Days off", value: false }]}
              onChange={onWorkingDaysChange}
            />
            <Select
              aria-label="Seasonality factor"
              value={useSeasonality}
              disabled={modelStrategy === "reference_portfolio"}
              options={[{ label: "Seasonality on", value: true }, { label: "Seasonality off", value: false }]}
              onChange={onSeasonalityChange}
            />
            <Space.Compact block>
              <InputNumber
                aria-label="Tariff demand impact percent"
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
                aria-label="Minimum average monthly quantity"
                min={0}
                value={minMonthlyVolume}
                onChange={(value) => onMinMonthlyVolumeChange(Number(value ?? 0))}
                style={{ width: "100%" }}
              />
              <Input value="min avg qty/month" readOnly style={{ width: 170 }} />
            </Space.Compact>
            <Button aria-label="Generate governed forecast" type="primary" onClick={onRun}>Generate forecast</Button>
          </div>
          <Paragraph className="workspace-copy" style={{ marginTop: 12, marginBottom: 0 }}>
            HMA, GMA, and KUS are the official forecast anchors. Model and PLC values reconcile exactly to the parent.
            Current runtime uses dealer/non-fleet wholesale. The approved KUS contract separates Wholesale and
            Carpet Floor Mat Fleet baskets from June 2026; implementation and backtest are pending.
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

            <section aria-label="Rolling-origin contract">
              <Card className="content-card" title="Rolling-origin contract">
                <Paragraph className="workspace-copy">
                  H1 is one month ahead, H2 is two months ahead, and H3 is three months ahead.
                  With 42 completed months and 24 months of minimum training, the governed contract
                  has 18 H1, 17 H2, and 16 H3 Official Total common-origin rows (51 combined).
                  The recent application H1 diagnostic contains Brand prediction rows and is not a
                  same-scope ranking against the governed contract.
                </Paragraph>
                <div role="region" aria-label="Evaluation scope table">
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="evaluationScopeId"
                    dataSource={data.summary.evaluationScopes}
                    columns={[
                      { title: "Scope ID", dataIndex: "evaluationScopeId", key: "evaluationScopeId", width: 310 },
                      { title: "Label", dataIndex: "label", key: "label", width: 220 },
                      { title: "Horizons", dataIndex: "horizons", key: "horizons", render: (value: number[]) => value.join(", ") },
                      { title: "Common origin rows", dataIndex: "commonOriginRows", key: "commonOriginRows", align: "right" as const, render: (value: number | null) => value ?? "Not validated" },
                      { title: "Brand prediction rows", dataIndex: "brandPredictionRows", key: "brandPredictionRows", align: "right" as const, render: (value: number | null) => value ?? "Not validated" },
                      { title: "Aggregation / coverage", key: "contract", render: (_: unknown, row) => `${row.aggregation}; ${row.coverage}` },
                      { title: "Status", dataIndex: "validationStatus", key: "validationStatus" },
                    ]}
                    scroll={{ x: 1250 }}
                  />
                </div>
              </Card>
            </section>

            <section aria-label="Fair model comparison">
              <Card className="content-card" title="Fair model comparison">
                <Alert
                  type={data.summary.fairModelComparison.validationStatus.startsWith("validated") ? "success" : "warning"}
                  showIcon
                  message={data.summary.fairModelComparison.validationStatus}
                  description={data.summary.fairModelComparison.disclosure || "Registered values are withheld because this request is not the complete governed scope."}
                />
                <div role="region" aria-label="Fair model comparison table" style={{ marginTop: 16 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="modelId"
                    dataSource={data.summary.fairModelComparison.rows}
                    locale={{ emptyText: "No registered metrics are eligible for this request scope." }}
                    columns={[
                      { title: "Method", dataIndex: "label", key: "label", width: 260 },
                      { title: "Comparison", dataIndex: "comparisonType", key: "comparisonType", width: 220 },
                      { title: "HMA", dataIndex: "hmaMethod", key: "hmaMethod", width: 280, render: (value: string) => <ModelIdentity modelId={value} /> },
                      { title: "GMA", dataIndex: "gmaMethod", key: "gmaMethod", render: (value: string) => <ModelIdentity modelId={value} /> },
                      { title: "KUS", dataIndex: "kusMethod", key: "kusMethod", render: (value: string) => <ModelIdentity modelId={value} /> },
                      { title: "Official Total WAPE", dataIndex: "officialTotalWape", key: "officialTotalWape", align: "right" as const, render: (value: number) => `${(value * 100).toFixed(2)}%` },
                      { title: "Common folds", dataIndex: "foldCount", key: "foldCount", align: "right" as const },
                    ]}
                    scroll={{ x: 1350 }}
                  />
                </div>
              </Card>
            </section>

            <section aria-label="Allocation accuracy">
              <Card className="content-card" title="Allocation accuracy">
                <Paragraph className="workspace-copy">
                  Brand forecast error propagates to children; child share error is additional.
                  These held-out diagnostics supply the actual parent total only to isolate allocation
                  share error. They are allocationOnly, not end-to-end accuracy. Reconciliation PASS
                  means the children sum to the parent; it does not measure allocation accuracy.
                </Paragraph>
                <div role="region" aria-label="Allocation accuracy table">
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="level"
                    dataSource={data.summary.allocationAccuracy}
                    columns={[
                      { title: "Level", dataIndex: "level", key: "level" },
                      { title: "Scope", dataIndex: "scope", key: "scope" },
                      { title: "Grain", dataIndex: "grain", key: "grain", width: 310 },
                      { title: "WAPE", dataIndex: "wape", key: "wape", align: "right" as const, render: (value: number | null) => value === null ? "N/A" : `${(value * 100).toFixed(2)}%` },
                      { title: "Accuracy", dataIndex: "accuracy", key: "accuracy", align: "right" as const, render: (value: number | null) => value === null ? "N/A" : `${(value * 100).toFixed(2)}%` },
                      { title: "Coverage", dataIndex: "coverage", key: "coverage", align: "right" as const, render: (value: number) => `${(value * 100).toFixed(1)}%` },
                      { title: "Rows", dataIndex: "rowCount", key: "rowCount", align: "right" as const },
                      { title: "Folds", dataIndex: "foldCount", key: "foldCount", align: "right" as const },
                      { title: "Status", dataIndex: "validationStatus", key: "validationStatus" },
                    ]}
                    scroll={{ x: 1250 }}
                  />
                </div>
              </Card>
            </section>

            <section aria-label="Forecast Exceptions">
              <Card className="content-card" title="Forecast Exceptions">
                <Paragraph className="workspace-copy">
                  This governed list is evaluated across Model, PLC, and PIS_PNO before
                  eligibility filtering, and does not shrink when the displayed hierarchy level
                  changes. Reason codes appear only where their evidence is applicable. Series-level
                  findings show no single forecast month; forecast-specific findings name the actual
                  affected month. Evidence uses only the completed-month cutoff.
                </Paragraph>
                <div role="region" aria-label="Forecast Exceptions table">
                  <Table
                    size="small"
                    rowKey="exceptionId"
                    pagination={{ pageSize: 12, hideOnSinglePage: true }}
                    dataSource={data.forecastExceptions}
                    columns={[
                      { title: "Severity", dataIndex: "severity", key: "severity", render: (value: string) => <Tag color={value === "high" ? "red" : value === "medium" ? "gold" : "blue"}>{value.toUpperCase()}</Tag> },
                      { title: "Reason code", dataIndex: "reasonCode", key: "reasonCode", width: 230 },
                      { title: "Scope", dataIndex: "scope", key: "scope" },
                      { title: "Series", dataIndex: "seriesKey", key: "seriesKey", width: 260 },
                      { title: "Forecast month", dataIndex: "forecastMonth", key: "forecastMonth", render: (value: string | null, row) => row.seriesLevel ? "Series-level" : value },
                      { title: "Evidence", dataIndex: "evidence", key: "evidence", width: 360, render: (value: Record<string, unknown>) => JSON.stringify(value) },
                      { title: "Suggested action", dataIndex: "suggestedAction", key: "suggestedAction", width: 360 },
                    ]}
                    scroll={{ x: 1450 }}
                  />
                </div>
              </Card>
            </section>

            <section aria-label="Prediction intervals">
              <Card className="content-card" title="Prediction intervals">
                <Paragraph className="workspace-copy">
                  Bounds use horizon-specific held-out rolling-origin residuals and are constrained
                  to 0 ≤ lower ≤ point ≤ upper. Nominal and empirical coverage are reported separately.
                  {` ${data.summary.predictionIntervals.childCoveragePolicy}`}
                </Paragraph>
                <div role="region" aria-label="Official Total prediction interval table">
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(row) => `${row.forecastMonth}-${row.horizon}`}
                    dataSource={data.summary.predictionIntervals.officialTotal}
                    columns={[
                      { title: "Forecast month", dataIndex: "forecastMonth", key: "forecastMonth" },
                      { title: "Horizon", dataIndex: "horizon", key: "horizon", render: (value: number) => `H${value}` },
                      { title: "Lower", dataIndex: "lower", key: "lower", align: "right" as const, render: (value: number) => formatValue(value, metric) },
                      { title: "Point", dataIndex: "point", key: "point", align: "right" as const, render: (value: number) => formatValue(value, metric) },
                      { title: "Upper", dataIndex: "upper", key: "upper", align: "right" as const, render: (value: number) => formatValue(value, metric) },
                      { title: "Nominal", dataIndex: "nominalCoverage", key: "nominalCoverage", render: (value: number) => `${(value * 100).toFixed(0)}%` },
                      { title: "Empirical", dataIndex: "empiricalCoverage", key: "empiricalCoverage", render: (value: number | null) => value === null ? "N/A" : `${(value * 100).toFixed(1)}%` },
                      { title: "Coverage samples", dataIndex: "coverageSampleCount", key: "coverageSampleCount", align: "right" as const },
                      { title: "Calibration residuals", dataIndex: "calibrationResidualCount", key: "calibrationResidualCount", align: "right" as const },
                      { title: "Status", dataIndex: "validationStatus", key: "validationStatus" },
                    ]}
                    scroll={{ x: 1450 }}
                  />
                </div>
              </Card>
            </section>

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
                Current runtime does not yet add Fleet. The approved KUS Fleet-first, no-double-counting rule is pending implementation.
                Low-volume and stopped series receive no normal allocation;
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
