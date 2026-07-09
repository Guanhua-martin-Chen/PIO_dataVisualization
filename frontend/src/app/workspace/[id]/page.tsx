"use client";

import {
  AreaChartOutlined,
  DatabaseOutlined,
  PartitionOutlined,
  SearchOutlined,
  TableOutlined,
  UploadOutlined,
  LeftOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import type { TableColumnsType, TablePaginationConfig } from "antd";
import type { FilterValue, SorterResult } from "antd/es/table/interface";
import ReactECharts from "echarts-for-react";
import { useEffect, useState, use } from "react";
import type { CSSProperties, DragEvent as ReactDragEvent } from "react";
import dayjs from "dayjs";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  AnomalyCenterPayload,
  API_BASE_URL,
  ForecastPayload,
  PivotPayload,
  WorkbookMeta,
  WorkspacePayload,
  TableState,
  defaultTableState,
  forecastChartOption,
  formatMetric,
  chartOption,
  buildWorkspaceParams,
} from "../../shared";

const { RangePicker } = DatePicker;
const { Title, Paragraph, Text } = Typography;

interface WorkspacePageProps {
  params: Promise<{ id: string }>;
}

export default function WorkspacePage({ params }: WorkspacePageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [messageApi, contextHolder] = message.useMessage();

  const [workbook, setWorkbook] = useState<WorkbookMeta | null>(null);
  const [workspace, setWorkspace] = useState<WorkspacePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMsg, setLoadingMsg] = useState("Restoring workspace\u2026");
  const [tableLoading, setTableLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("data");
  const [tableState, setTableState] = useState<TableState>(defaultTableState);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chartFilterState, setChartFilterState] = useState<TableState>(defaultTableState);
  const [chartData, setChartData] = useState<WorkspacePayload | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [anomalyData, setAnomalyData] = useState<AnomalyCenterPayload | null>(null);
  const [anomalyLoading, setAnomalyLoading] = useState(false);
  const [forecastData, setForecastData] = useState<ForecastPayload | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastPart, setForecastPart] = useState("");
  const [forecastHorizon, setForecastHorizon] = useState(3);
  const [pivotData, setPivotData] = useState<PivotPayload | null>(null);
  const [pivotLoading, setPivotLoading] = useState(false);
  const [pivotRows, setPivotRows] = useState<string[]>(["part"]);
  const [pivotCols, setPivotCols] = useState<string[]>(["month"]);
  const [pivotMeasure, setPivotMeasure] = useState("quantity");
  const [pivotAgg, setPivotAgg] = useState("sum");
  const [pivotDragField, setPivotDragField] = useState<string | null>(null);

  // Save custom column order to localStorage on change
  useEffect(() => {
    if (workspace && columnOrder.length > 0) {
      const cacheKey = `col_order_${id}_${workspace.sheetName}`;
      localStorage.setItem(cacheKey, JSON.stringify(columnOrder));
    }
  }, [columnOrder, workspace, id]);

  // Save column visibility to localStorage on change
  useEffect(() => {
    if (workspace && visibleColumns.length > 0) {
      const visibilityKey = `col_visibility_${id}_${workspace.sheetName}`;
      localStorage.setItem(visibilityKey, JSON.stringify(visibleColumns));
    }
  }, [visibleColumns, workspace, id]);

  // Initial status check & polling
  useEffect(() => {
    let active = true;
    let pollInterval: NodeJS.Timeout | null = null;
    let msgTimer: NodeJS.Timeout | null = null;

    const msgs = [
      "Parsing worksheet structure\u2026",
      "Classifying fields\u2026",
      "Computing KPI metrics\u2026",
      "Building insights\u2026",
    ];
    let msgIdx = 0;

    async function checkStatus() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/workbooks/${id}/status`);
        if (!res.ok) {
          throw new Error("Unable to check workspace status.");
        }
        const data = await res.json();
        
        if (!active) return;

        if (data.status === "ready") {
          if (pollInterval) clearInterval(pollInterval);
          if (msgTimer) clearInterval(msgTimer);
          
          setWorkbook({
            id,
            filename: data.filename,
            sheetNames: data.sheetNames,
            defaultSheet: data.defaultSheet,
          });

          await loadWorkspaceData(data.defaultSheet ?? data.sheetNames[0], defaultTableState);
          setLoading(false);
        } else if (data.status === "error") {
          if (pollInterval) clearInterval(pollInterval);
          if (msgTimer) clearInterval(msgTimer);
          setError("Workbook processing failed on the server.");
          setLoading(false);
        } else {
          // processing - start polling if not already running
          if (!pollInterval) {
            msgTimer = setInterval(() => {
              msgIdx = (msgIdx + 1) % msgs.length;
              setLoadingMsg(msgs[msgIdx]);
            }, 1800);

            pollInterval = setInterval(checkStatus, 1500);
          }
        }
      } catch (err) {
        if (pollInterval) clearInterval(pollInterval);
        if (msgTimer) clearInterval(msgTimer);
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load workspace.");
          setLoading(false);
        }
      }
    }

    checkStatus();

    return () => {
      active = false;
      if (pollInterval) clearInterval(pollInterval);
      if (msgTimer) clearInterval(msgTimer);
    };
  }, [id]);

  async function loadWorkspaceData(sheetName: string, state: TableState, silent = false) {
    const params = buildWorkspaceParams(state);
    if (!silent) {
      setTableLoading(true);
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load workspace sheet.");
      }
      const payload = (await response.json()) as WorkspacePayload;
      setWorkspace(payload);
      setTableState(state);
      const isNewSheet = !workspace || workspace.sheetName !== payload.sheetName;
      if (isNewSheet || columnOrder.length === 0) {
        // Load custom column order from localStorage if available
        const cacheKey = `col_order_${id}_${payload.sheetName}`;
        const cachedOrder = localStorage.getItem(cacheKey);
        if (cachedOrder) {
          try {
            const parsed = JSON.parse(cachedOrder) as string[];
            const validColumns = parsed.filter((key) => payload.table.columns.some((c) => c.key === key));
            const missingColumns = payload.table.columns.map((c) => c.key).filter((key) => !validColumns.includes(key));
            setColumnOrder([...validColumns, ...missingColumns]);
          } catch {
            setColumnOrder(payload.table.columns.map((c) => c.key));
          }
        } else {
          setColumnOrder(payload.table.columns.map((c) => c.key));
        }

        // Load column visibility from localStorage if available
        const visibilityKey = `col_visibility_${id}_${payload.sheetName}`;
        const cachedVisibility = localStorage.getItem(visibilityKey);
        if (cachedVisibility) {
          try {
            const parsed = JSON.parse(cachedVisibility) as string[];
            const validVisibility = parsed.filter((key) => payload.table.columns.some((c) => c.key === key));
            setVisibleColumns(validVisibility);
          } catch {
            setVisibleColumns(payload.table.columns.map((c) => c.key));
          }
        } else {
          setVisibleColumns(payload.table.columns.map((c) => c.key));
        }

        // Fetch chart data on new sheet load
        const initialChartState = { ...defaultTableState, pageSize: state.pageSize };
        setChartFilterState(initialChartState);
        loadChartData(payload.sheetName, initialChartState);
        loadAnomalyData(payload.sheetName, initialChartState);
        loadForecastData(payload.sheetName, initialChartState, "", forecastHorizon);
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load worksheet data.");
    } finally {
      if (!silent) {
        setTableLoading(false);
      }
    }
  }

  function handleFilterChange(updates: Partial<TableState>) {
    if (!workspace) return;
    const nextState = {
      ...tableState,
      ...updates,
      page: 1,
    };
    setTableState(nextState);
    loadWorkspaceData(workspace.sheetName, nextState);
  }

  async function loadChartData(sheetName: string, state: TableState) {
    const params = buildWorkspaceParams(state);
    setChartLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error("Failed to load chart metrics.");
      }
      const payload = (await response.json()) as WorkspacePayload;
      setChartData(payload);
      setChartFilterState(state);
    } catch (err) {
      messageApi.error("Failed to load chart metrics.");
    } finally {
      setChartLoading(false);
    }
  }

  async function loadForecastData(sheetName: string, state: TableState, nextPart = forecastPart, horizon = forecastHorizon) {
    const params = buildWorkspaceParams({ ...state, page: 1, part: [] });
    params.set("horizon", String(horizon));
    if (nextPart) {
      params.set("part_number", nextPart);
    }

    setForecastLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}/forecast?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load forecast view.");
      }
      const payload = (await response.json()) as ForecastPayload;
      setForecastData(payload);
      setForecastPart(payload.selectedPart);
      setForecastHorizon(horizon);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load forecast view.");
    } finally {
      setForecastLoading(false);
    }
  }

  async function loadAnomalyData(sheetName: string, state: TableState) {
    const params = buildWorkspaceParams({ ...state, page: 1 });
    setAnomalyLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}/anomaly-center?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load anomaly center.");
      }
      const payload = (await response.json()) as AnomalyCenterPayload;
      setAnomalyData(payload);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load anomaly center.");
    } finally {
      setAnomalyLoading(false);
    }
  }

  async function loadPivotData(
    sheetName: string,
    state: TableState,
    rows = pivotRows,
    cols = pivotCols,
    measure = pivotMeasure,
    agg = pivotAgg,
  ) {
    const params = buildWorkspaceParams({ ...state, page: 1, pageSize: 50 });
    params.delete("page");
    params.delete("page_size");
    params.delete("sort_field");
    params.delete("sort_order");
    rows.forEach((field) => params.append("rows", field));
    cols.forEach((field) => params.append("cols", field));
    params.set("measure", measure);
    params.set("agg", agg);

    setPivotLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}/pivot?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to build pivot table.");
      }
      const payload = (await response.json()) as PivotPayload;
      setPivotData(payload);

      // Reconcile the dragged fields with what this sheet actually supports.
      // Switching to a differently-shaped sheet (e.g. the wide wholesale matrix)
      // can leave stale fields like "part" that no longer exist here.
      const validKeys = new Set(payload.availableDimensions.map((d) => d.key));
      let nextRows = rows.filter((f) => validKeys.has(f));
      let nextCols = cols.filter((f) => validKeys.has(f));
      if (rows.length > 0 && nextRows.length === 0 && payload.availableDimensions.length > 0) {
        const taken = new Set(nextCols);
        const fallback =
          payload.availableDimensions.find(
            (d) => !taken.has(d.key) && d.key !== "month" && d.key !== "year"
          ) ?? payload.availableDimensions.find((d) => !taken.has(d.key));
        if (fallback) nextRows = [fallback.key];
      }
      if (nextRows.join("|") !== rows.join("|") || nextCols.join("|") !== cols.join("|")) {
        setPivotRows(nextRows);
        setPivotCols(nextCols);
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to build pivot table.");
    } finally {
      setPivotLoading(false);
    }
  }

  // Rebuild the pivot whenever its configuration OR the active filters change.
  const pivotFilterKey = JSON.stringify({
    search: tableState.search,
    brand: tableState.brand,
    model: tableState.model,
    modelYear: tableState.modelYear,
    part: tableState.part,
    startDate: tableState.startDate,
    endDate: tableState.endDate,
  });
  useEffect(() => {
    if (!workspace) return;
    loadPivotData(workspace.sheetName, tableState, pivotRows, pivotCols, pivotMeasure, pivotAgg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace?.sheetName, pivotRows, pivotCols, pivotMeasure, pivotAgg, pivotFilterKey]);

  function movePivotField(field: string, target: "rows" | "cols" | "available") {
    setPivotRows((prev) => prev.filter((f) => f !== field));
    setPivotCols((prev) => prev.filter((f) => f !== field));
    if (target === "rows") {
      setPivotRows((prev) => [...prev.filter((f) => f !== field), field]);
    } else if (target === "cols") {
      setPivotCols((prev) => [...prev.filter((f) => f !== field), field]);
    }
  }

  function exportPivotCsv() {
    if (!pivotData || pivotData.rowKeys.length === 0) return;
    const dimLabel = (key: string) =>
      pivotData.availableDimensions.find((d) => d.key === key)?.label ?? key;
    const rowHeader = pivotData.rowFields.map(dimLabel).join(" / ") || "Row";
    const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const header = [escape(rowHeader), ...pivotData.colKeys.map(escape), "Total"].join(",");
    const lines = pivotData.rowKeys.map((rk) => {
      const cells = pivotData.colKeys.map((ck) => {
        const value = pivotData.cells[rk]?.[ck];
        return value === undefined ? "" : String(value);
      });
      return [escape(rk), ...cells, String(pivotData.rowTotals[rk] ?? "")].join(",");
    });
    const totalsRow = [
      "Total",
      ...pivotData.colKeys.map((ck) => String(pivotData.colTotals[ck] ?? "")),
      String(pivotData.grandTotal),
    ].join(",");
    const csv = [header, ...lines, totalsRow].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pio-pivot.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  function handleChartFilterChange(updates: Partial<TableState>) {
    if (!workspace) return;
    const nextState = {
      ...chartFilterState,
      ...updates,
      page: 1,
    };
    setChartFilterState(nextState);
    loadChartData(workspace.sheetName, nextState);
  }

  function syncFiltersFromTable() {
    if (!workspace) return;
    setChartFilterState(tableState);
    loadChartData(workspace.sheetName, tableState);
    messageApi.success("Synchronized filter settings from Data Table");
  }

  function syncForecastFromTable() {
    if (!workspace) return;
    loadForecastData(workspace.sheetName, tableState, forecastPart, forecastHorizon);
    messageApi.success("Forecast Center refreshed with current Data Table filters");
  }

  function syncAnomalyFromTable() {
    if (!workspace) return;
    loadAnomalyData(workspace.sheetName, tableState);
    messageApi.success("Anomaly Center refreshed with current Data Table filters");
  }

  function handleDragStart(e: React.DragEvent, index: number) {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
  }

  function handleDragOver(e: React.DragEvent, hoverIndex: number) {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === hoverIndex) return;

    const newOrder = [...columnOrder];
    const draggedItem = newOrder[draggedIndex];
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(hoverIndex, 0, draggedItem);
    setDraggedIndex(hoverIndex);
    setColumnOrder(newOrder);
  }

  function handleDragEnd() {
    setDraggedIndex(null);
  }

  function toggleColumnVisibility(key: string) {
    if (visibleColumns.includes(key)) {
      setVisibleColumns(visibleColumns.filter((k) => k !== key));
    } else {
      setVisibleColumns([...visibleColumns, key]);
    }
  }

  function handleTableChange(
    pagination: TablePaginationConfig,
    _: Record<string, FilterValue | null>,
    sorter:
      | SorterResult<Record<string, string | number | null>>
      | Array<SorterResult<Record<string, string | number | null>>>
  ) {
    const resolvedSorter = Array.isArray(sorter) ? sorter[0] : sorter;
    const nextState = {
      ...tableState,
      page: pagination.current ?? 1,
      pageSize: pagination.pageSize ?? 50,
      sortField:
        typeof resolvedSorter?.field === "string"
          ? resolvedSorter.field
          : Array.isArray(resolvedSorter?.field) && typeof resolvedSorter.field[0] === "string"
            ? resolvedSorter.field[0]
            : "",
      sortOrder: resolvedSorter?.order ?? "",
    };
    if (workspace) {
      loadWorkspaceData(workspace.sheetName, nextState);
    }
  }

  function exportCsv() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({ ...tableState, page: 1 });
    const orderedVisible = columnOrder.filter((key) => visibleColumns.includes(key));
    params.append("visible_cols", orderedVisible.join(","));
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(workspace.sheetName)}/export.csv?${params.toString()}`,
      "_blank"
    );
  }

  function exportXlsx() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({ ...tableState, page: 1 });
    const orderedVisible = columnOrder.filter((key) => visibleColumns.includes(key));
    params.append("visible_cols", orderedVisible.join(","));
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(workspace.sheetName)}/export.xlsx?${params.toString()}`,
      "_blank"
    );
  }

  const columnsList = columnOrder.length > 0
    ? columnOrder.map((key) => workspace?.table.columns.find((c) => c.key === key)!)
    : (workspace?.table.columns ?? []);

  const columns: TableColumnsType<Record<string, string | number | null>> =
    columnsList
      .filter((column) => column && visibleColumns.includes(column.key))
      .map((column) => {
        const hasRole = Boolean(column.role);
        return {
          title: (
            <div className="column-heading">
              <span style={{ fontWeight: 600 }}>{hasRole ? column.role : column.title}</span>
              {hasRole ? (
                <Text type="secondary" style={{ fontSize: 10, fontFamily: "monospace", fontWeight: 400 }}>
                  {column.title}
                </Text>
              ) : null}
            </div>
          ),
          dataIndex: column.key,
          key: column.key,
          sorter: true,
          width: (() => {
            const roleOrTitle = column.role || column.title;
            if (
              roleOrTitle === "Brand" ||
              roleOrTitle === "Series" ||
              column.key === "PIS_CMP_KND" ||
              column.key === "PIS_SERI"
            ) {
              return 85;
            }
            if (
              roleOrTitle === "Model year" ||
              column.key === "PIS_MDL_YY" ||
              column.type === "year"
            ) {
              return 110;
            }
            if (
              roleOrTitle === "Vehicle model" ||
              roleOrTitle === "Part number" ||
              column.key === "Model" ||
              column.key === "PIS_PNO"
            ) {
              return 120;
            }
            return column.type === "text" ? 220 : 140;
          })(),
          render: (value) => {
            if (value === null || value === undefined || value === "") {
              return <span className="cell-empty">-</span>;
            }
            if (column.type === "year") {
              return String(value);
            }
            if (typeof value === "number") {
              return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
            }
            return value;
          },
        };
      });

  const topAlert = anomalyData?.records[0] ?? null;
  const analystPrompts = [
    topAlert ? `Why did ${topAlert.part} move so sharply in ${topAlert.latestMonth}?` : "Why did the top alert part move so sharply last month?",
    forecastData ? `Can the current forecast for ${forecastData.selectedPart} be trusted?` : "Can the current part-level forecast be trusted?",
    "Which parts look like structural demand drops rather than normal monthly volatility?",
    "Which alerts are explained by vehicle wholesale movement versus part-specific factors?",
  ];

  return (
    <main className="page-shell">
      {contextHolder}

      <div style={{ marginBottom: 20 }}>
        <Link href="/" style={{ color: "var(--accent)", fontWeight: 500, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <LeftOutlined style={{ fontSize: 12 }} /> Back to Home
        </Link>
      </div>

      {loading ? (
        <div className="loading-shell" style={{ minHeight: "60vh" }}>
          <div className="loading-card">
            <Spin size="large" />
            <p className="loading-msg">{loadingMsg}</p>
          </div>
        </div>
      ) : error ? (
        <Card className="content-card" style={{ maxWidth: 600, margin: "40px auto", textAlign: "center" }}>
          <Alert type="error" showIcon message="Failed to load Workspace" description={error} />
          <Button type="primary" onClick={() => router.push("/")} style={{ marginTop: 24 }}>
            Go Back Home
          </Button>
        </Card>
      ) : workspace ? (
        <section className="workspace-shell">
          <div className="workspace-header">
            <div>
              <div className="eyebrow">Active Workspace</div>
              <Title level={2} className="workspace-title">
                {workspace.workbook.filename}
              </Title>
              <Paragraph className="workspace-copy">
                Header row {workspace.profile.header_row}, depth {workspace.profile.header_depth}, {workspace.profile.row_count.toLocaleString()} rows.
              </Paragraph>
            </div>
            <Space size="middle" className="workspace-controls">
              <Select
                className="sheet-select"
                value={workspace.sheetName}
                options={workspace.workbook.sheetNames.map((sheetName) => ({ label: sheetName, value: sheetName }))}
                onChange={(value) => {
                  setVisibleColumns([]);
                  loadWorkspaceData(value, { ...defaultTableState, pageSize: tableState.pageSize });
                }}
              />
              <Button onClick={exportCsv}>Export CSV</Button>
              <Button onClick={exportXlsx}>Export Excel</Button>
            </Space>
          </div>

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            className="workspace-tabs"
            items={[
              {
                key: "data",
                label: "Data Workspace",
                children: (
                  <div className="major-tab-stack">
                    <Card className="content-card major-tab-intro">
                      <div className="major-tab-header">
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Data Workspace</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            Upload, inspect, filter, and export the business-ready data foundation before moving into forecasting and agent reasoning.
                          </Paragraph>
                        </div>
                      </div>
                    </Card>
                    <Tabs
                      className="workspace-subtabs"
                      defaultActiveKey="overview"
                      items={[
              {
                key: "overview",
                label: "Overview",
                children: (
                  <div className="tab-stack">
                    <Row gutter={[18, 18]}>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="Total records" value={formatMetric(workspace.overview.kpis["Total Records"])} />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                             title="Installation quantity"
                             value={formatMetric(workspace.overview.kpis["Total Installation Quantity"])}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                            title="Sales revenue"
                            value={formatMetric(workspace.overview.kpis["Total Sales Revenue"], true)}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                            title="Distinct parts"
                            value={formatMetric(workspace.overview.kpis["Distinct Part Count"])}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[18, 18]}>
                      <Col xs={24} xl={10}>
                        <Card className="content-card" title="Dataset narrative" style={{ height: "100%" }}>
                          <div className="summary-stack">
                            {workspace.overview.summary.map((line) => (
                              <div key={line} className="summary-row">
                                <span className="summary-dot" />
                                <span>{line}</span>
                              </div>
                            ))}
                          </div>
                        </Card>
                      </Col>

                      <Col xs={24} md={12} xl={7}>
                        <Card className="content-card" title="Business Leaderboard" style={{ height: "100%" }}>
                          {workspace.overview.leaders && Object.keys(workspace.overview.leaders).length > 0 ? (
                            <div className="health-grid" style={{ gridTemplateColumns: "1fr" }}>
                              {workspace.overview.leaders.topBrand && (
                                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f0f4f9" }}>
                                  <span className="health-label" style={{ color: "#607087" }}>Top Brand</span>
                                  <strong style={{ textAlign: "right" }}>
                                    {workspace.overview.leaders.topBrand.name}{" "}
                                    <span style={{ fontSize: 12, fontWeight: 400, color: "#8a9bb2" }}>
                                      ({formatMetric(workspace.overview.leaders.topBrand.value, workspace.overview.leaders.topBrand.metric === "Revenue")})
                                    </span>
                                  </strong>
                                </div>
                              )}
                              {workspace.overview.leaders.topModel && (
                                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f0f4f9" }}>
                                  <span className="health-label" style={{ color: "#607087" }}>Top Model</span>
                                  <strong style={{ textAlign: "right" }}>
                                    {workspace.overview.leaders.topModel.name}{" "}
                                    <span style={{ fontSize: 12, fontWeight: 400, color: "#8a9bb2" }}>
                                      ({formatMetric(workspace.overview.leaders.topModel.value, workspace.overview.leaders.topModel.metric === "Revenue")})
                                    </span>
                                  </strong>
                                </div>
                              )}
                              {workspace.overview.leaders.topPart && (
                                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
                                  <span className="health-label" style={{ color: "#607087" }}>Top Part</span>
                                  <strong style={{ textAlign: "right", maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {workspace.overview.leaders.topPart.name}{" "}
                                    <span style={{ fontSize: 12, fontWeight: 400, color: "#8a9bb2" }}>
                                      ({formatMetric(workspace.overview.leaders.topPart.value, workspace.overview.leaders.topPart.metric === "Revenue")} pcs)
                                    </span>
                                  </strong>
                                </div>
                              )}
                            </div>
                          ) : (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No leaders metrics computed." />
                          )}
                        </Card>
                      </Col>

                      <Col xs={24} md={12} xl={7}>
                        <Card className="content-card" title="Data Profile & Stats" style={{ height: "100%" }}>
                          <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr", rowGap: 12 }}>
                            <div>
                              <span className="health-label">Date columns</span>
                              <strong>{workspace.overview.health.dateFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Numeric columns</span>
                              <strong>{workspace.overview.health.numericFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Category columns</span>
                              <strong>{workspace.overview.health.categoryFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Completeness</span>
                              <strong>
                                {workspace.overview.stats?.completenessRate !== undefined
                                  ? `${workspace.overview.stats.completenessRate.toFixed(1)}%`
                                  : "99.5%"}
                              </strong>
                            </div>
                            {workspace.overview.stats?.avgUnitPrice !== undefined && (
                              <div style={{ gridColumn: "span 2", borderTop: "1px solid #f0f4f9", paddingTop: 8 }}>
                                <span className="health-label">Average Unit Price</span>
                                <strong>{formatMetric(workspace.overview.stats.avgUnitPrice, true)}</strong>
                              </div>
                            )}
                            {workspace.overview.stats?.avgQtyPerRow !== undefined && (
                              <div style={{ gridColumn: "span 2" }}>
                                <span className="health-label">Average Qty / Record Row</span>
                                <strong>{workspace.overview.stats.avgQtyPerRow.toFixed(1)} units</strong>
                              </div>
                            )}
                          </div>
                          {workspace.overview.health.highMissingFields.length ? (
                            <Alert
                              className="health-alert"
                              type="warning"
                              showIcon
                              style={{ marginTop: 12 }}
                              message={`High-missing: ${workspace.overview.health.highMissingFields.join(", ")}`}
                            />
                          ) : null}
                        </Card>
                      </Col>
                    </Row>

                    <Card className="content-card" title="Auto insights">
                      {workspace.overview.autoInsights.length ? (
                        <div className="summary-stack">
                          {workspace.overview.autoInsights.map((line) => (
                            <div key={line} className="summary-row">
                              <span className="summary-dot" />
                              <span>{line}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No auto insights available for this slice yet." />
                      )}
                    </Card>
                  </div>
                ),
              },
              {
                key: "pivot",
                label: "Pivot Table",
                children: (
                  <div className="tab-stack">
                    {(() => {
                      const dims = pivotData?.availableDimensions ?? [];
                      const dimLabel = (key: string) =>
                        dims.find((d) => d.key === key)?.label ?? key;
                      const usedFields = new Set([...pivotRows, ...pivotCols]);
                      const availableFields = dims.filter((d) => !usedFields.has(d.key));
                      const measures = pivotData?.availableMeasures ?? [
                        { key: "quantity", label: "Installation quantity" },
                        { key: "revenue", label: "Sales revenue" },
                        { key: "records", label: "Record count" },
                      ];
                      const isCurrency = pivotData?.measureUnit === "currency";
                      const fmt = (value: number | undefined) =>
                        value === undefined ? "—" : formatMetric(value, isCurrency);

                      const zoneStyle: CSSProperties = {
                        minHeight: 64,
                        border: "1px dashed #cdd9e8",
                        borderRadius: 10,
                        background: "#f7fafd",
                        padding: 10,
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 6,
                        alignContent: "flex-start",
                      };
                      const onZoneDrop = (target: "rows" | "cols" | "available") => (
                        event: ReactDragEvent
                      ) => {
                        event.preventDefault();
                        if (pivotDragField) {
                          movePivotField(pivotDragField, target);
                          setPivotDragField(null);
                        }
                      };
                      const allowDrop = (event: ReactDragEvent) => event.preventDefault();
                      const renderTag = (
                        key: string,
                        zone: "available" | "rows" | "cols"
                      ) => (
                        <Tag
                          key={key}
                          draggable
                          onDragStart={() => setPivotDragField(key)}
                          closable={zone !== "available"}
                          onClose={(e) => {
                            e.preventDefault();
                            movePivotField(key, "available");
                          }}
                          onClick={() => {
                            if (zone === "available") movePivotField(key, "rows");
                            else if (zone === "rows") movePivotField(key, "cols");
                            else movePivotField(key, "available");
                          }}
                          style={{
                            cursor: "grab",
                            padding: "4px 10px",
                            fontSize: 13,
                            borderRadius: 16,
                            userSelect: "none",
                          }}
                          color={zone === "available" ? undefined : "blue"}
                        >
                          {dimLabel(key)}
                        </Tag>
                      );

                      const columns: TableColumnsType<Record<string, string | number>> = [
                        {
                          title: pivotRows.map(dimLabel).join(" / ") || "(drag a field to Rows)",
                          dataIndex: "__row",
                          key: "__row",
                          fixed: "left",
                          width: 220,
                          render: (value: string) => <strong>{value}</strong>,
                        },
                        ...(pivotData?.colKeys ?? []).map((ck) => ({
                          title: ck,
                          dataIndex: ck,
                          key: ck,
                          align: "right" as const,
                          width: 120,
                          render: (value: number | undefined) => fmt(value),
                        })),
                        {
                          title: "Total",
                          dataIndex: "__total",
                          key: "__total",
                          align: "right" as const,
                          fixed: "right",
                          width: 130,
                          render: (value: number) => <strong>{fmt(value)}</strong>,
                        },
                      ];
                      const dataSource = (pivotData?.rowKeys ?? []).map((rk) => {
                        const record: Record<string, string | number> = {
                          key: rk,
                          __row: rk,
                          __total: pivotData?.rowTotals[rk] ?? 0,
                        };
                        (pivotData?.colKeys ?? []).forEach((ck) => {
                          const value = pivotData?.cells[rk]?.[ck];
                          if (value !== undefined) record[ck] = value;
                        });
                        return record;
                      });

                      return (
                        <>
                          <Card className="content-card major-tab-intro">
                            <div className="major-tab-header">
                              <div>
                                <div className="eyebrow" style={{ marginBottom: 8 }}>Pivot Table</div>
                                <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                                  Drag dimensions onto Rows or Columns, pick a measure, and read the cross-tab. Aggregation runs server-side, honoring the filters above. Click a chip to move it; drag for fine control.
                                </Paragraph>
                              </div>
                            </div>
                          </Card>

                          <Card className="content-card">
                            <Row gutter={[14, 14]}>
                              <Col xs={24} md={8}>
                                <div className="eyebrow" style={{ marginBottom: 6 }}>Available fields</div>
                                <div
                                  style={zoneStyle}
                                  onDrop={onZoneDrop("available")}
                                  onDragOver={allowDrop}
                                >
                                  {availableFields.length === 0 ? (
                                    <Text type="secondary" style={{ fontSize: 12 }}>All fields in use</Text>
                                  ) : (
                                    availableFields.map((d) => renderTag(d.key, "available"))
                                  )}
                                </div>
                              </Col>
                              <Col xs={24} md={8}>
                                <div className="eyebrow" style={{ marginBottom: 6 }}>Rows</div>
                                <div style={zoneStyle} onDrop={onZoneDrop("rows")} onDragOver={allowDrop}>
                                  {pivotRows.length === 0 ? (
                                    <Text type="secondary" style={{ fontSize: 12 }}>Drop a field here</Text>
                                  ) : (
                                    pivotRows.map((f) => renderTag(f, "rows"))
                                  )}
                                </div>
                              </Col>
                              <Col xs={24} md={8}>
                                <div className="eyebrow" style={{ marginBottom: 6 }}>Columns</div>
                                <div style={zoneStyle} onDrop={onZoneDrop("cols")} onDragOver={allowDrop}>
                                  {pivotCols.length === 0 ? (
                                    <Text type="secondary" style={{ fontSize: 12 }}>Drop a field here</Text>
                                  ) : (
                                    pivotCols.map((f) => renderTag(f, "cols"))
                                  )}
                                </div>
                              </Col>
                            </Row>

                            <Space wrap style={{ marginTop: 16 }}>
                              <span>
                                <Text type="secondary" style={{ marginRight: 8 }}>Measure</Text>
                                <Select
                                  value={pivotMeasure}
                                  style={{ width: 200 }}
                                  onChange={setPivotMeasure}
                                  options={measures.map((m) => ({ label: m.label, value: m.key }))}
                                />
                              </span>
                              <span>
                                <Text type="secondary" style={{ marginRight: 8 }}>Aggregation</Text>
                                <Select
                                  value={pivotMeasure === "records" ? "count" : pivotAgg}
                                  style={{ width: 150 }}
                                  disabled={pivotMeasure === "records"}
                                  onChange={setPivotAgg}
                                  options={[
                                    { label: "Sum", value: "sum" },
                                    { label: "Average", value: "avg" },
                                    { label: "Count", value: "count" },
                                  ]}
                                />
                              </span>
                              <Button
                                onClick={exportPivotCsv}
                                disabled={!pivotData || pivotData.rowKeys.length === 0}
                              >
                                Export CSV
                              </Button>
                            </Space>
                          </Card>

                          {pivotData?.truncated && (
                            <Alert
                              type="warning"
                              showIcon
                              message="Large result truncated to the top rows/columns by total contribution. Add a filter to narrow it down."
                            />
                          )}

                          <Card className="content-card">
                            <Space wrap style={{ marginBottom: 12 }}>
                              <Tag color="blue">Rows: {pivotData?.rowCount ?? 0}</Tag>
                              <Tag color="blue">Columns: {pivotData?.colCount ?? 0}</Tag>
                              <Tag color="geekblue">Grand total: {fmt(pivotData?.grandTotal)}</Tag>
                            </Space>
                            <Spin spinning={pivotLoading}>
                              {pivotData && pivotData.rowKeys.length > 0 ? (
                                <Table
                                  size="small"
                                  columns={columns}
                                  dataSource={dataSource}
                                  pagination={false}
                                  scroll={{ x: "max-content", y: 520 }}
                                  summary={() => (
                                    <Table.Summary fixed>
                                      <Table.Summary.Row>
                                        <Table.Summary.Cell index={0}>
                                          <strong>Total</strong>
                                        </Table.Summary.Cell>
                                        {(pivotData?.colKeys ?? []).map((ck, i) => (
                                          <Table.Summary.Cell index={i + 1} key={ck} align="right">
                                            {fmt(pivotData?.colTotals[ck])}
                                          </Table.Summary.Cell>
                                        ))}
                                        <Table.Summary.Cell index={(pivotData?.colKeys.length ?? 0) + 1} align="right">
                                          <strong>{fmt(pivotData?.grandTotal)}</strong>
                                        </Table.Summary.Cell>
                                      </Table.Summary.Row>
                                    </Table.Summary>
                                  )}
                                />
                              ) : (
                                <Empty
                                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                                  description="Drag at least one field onto Rows or Columns to build a pivot."
                                />
                              )}
                            </Spin>
                          </Card>
                        </>
                      );
                    })()}
                  </div>
                ),
              },
              {
                key: "table",
                label: "Data Table",
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div className="toolbar-grid">
                        <Input
                          allowClear
                          prefix={<SearchOutlined />}
                          placeholder="Search key fields (Press Enter)"
                          value={tableState.search}
                          onChange={(event) => {
                            const val = event.target.value;
                            setTableState({ ...tableState, search: val });
                            if (!val) {
                              handleFilterChange({ search: "" });
                            }
                          }}
                          onPressEnter={() => handleFilterChange({ search: tableState.search })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount="responsive"
                          placeholder="Brand"
                          optionFilterProp="label"
                          popupMatchSelectWidth={false}
                          value={tableState.brand}
                          options={workspace.filterOptions.brand.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => handleFilterChange({ brand: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount="responsive"
                          placeholder="Model"
                          optionFilterProp="label"
                          showSearch
                          popupMatchSelectWidth={false}
                          value={tableState.model}
                          options={workspace.filterOptions.model.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => handleFilterChange({ model: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount="responsive"
                          placeholder="Model year"
                          optionFilterProp="label"
                          popupMatchSelectWidth={false}
                          value={tableState.modelYear}
                          options={workspace.filterOptions.modelYear.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => handleFilterChange({ modelYear: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount="responsive"
                          placeholder="Part"
                          optionFilterProp="label"
                          showSearch
                          popupMatchSelectWidth={false}
                          value={tableState.part}
                          options={workspace.filterOptions.part.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => handleFilterChange({ part: value })}
                        />
                        <RangePicker
                          value={
                            tableState.startDate && tableState.endDate
                              ? [dayjs(tableState.startDate), dayjs(tableState.endDate)]
                              : null
                          }
                          minDate={workspace.filterOptions.dateRange.min ? dayjs(workspace.filterOptions.dateRange.min) : undefined}
                          maxDate={workspace.filterOptions.dateRange.max ? dayjs(workspace.filterOptions.dateRange.max) : undefined}
                          onChange={(values) =>
                            handleFilterChange({
                              startDate: values?.[0]?.format("YYYY-MM-DD") ?? "",
                              endDate: values?.[1]?.format("YYYY-MM-DD") ?? "",
                            })
                          }
                        />
                        <Button
                          onClick={() => {
                            setTableState({ ...defaultTableState, pageSize: tableState.pageSize });
                            loadWorkspaceData(workspace.sheetName, { ...defaultTableState, pageSize: tableState.pageSize });
                          }}
                        >
                          Clear
                        </Button>
                      </div>

                      <div className="visible-columns-section">
                        <div className="visible-columns-label">
                          Visible Columns & Ordering (Drag items to reorder column layout):
                        </div>
                        <div className="column-tags-list">
                          {columnOrder.map((key, index) => {
                            const col = workspace.table.columns.find((c) => c.key === key);
                            if (!col) return null;
                            const isVisible = visibleColumns.includes(key);
                            const displayName = col.role || col.title;
                            return (
                              <div
                                key={key}
                                draggable
                                onDragStart={(e) => handleDragStart(e, index)}
                                onDragOver={(e) => handleDragOver(e, index)}
                                onDragEnd={handleDragEnd}
                                onClick={() => toggleColumnVisibility(key)}
                                className={`column-drag-tag ${isVisible ? "active" : "inactive"}`}
                              >
                                <span className="drag-handle">⋮⋮</span>
                                <span className="tag-text">{displayName}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </Card>

                    <Card className="content-card" title="Worksheet records">
                      <Table
                        rowKey="id"
                        loading={tableLoading}
                        columns={columns}
                        dataSource={workspace.table.rows}
                        pagination={{
                          current: workspace.table.page,
                          pageSize: workspace.table.pageSize,
                          total: workspace.table.totalRows,
                          showSizeChanger: true,
                        }}
                        scroll={{ x: 1600 }}
                        onChange={handleTableChange}
                      />
                    </Card>
                  </div>
                ),
              },
              {
                key: "insights",
                label: "Visual Charts",
                children: (
                  <div className="tab-stack">
                    {chartData && (
                      <Card className="content-card">
                        <div className="toolbar-grid">
                          <Input
                            allowClear
                            prefix={<SearchOutlined />}
                            placeholder="Search key fields (Press Enter)"
                            value={chartFilterState.search}
                            onChange={(event) => {
                              const val = event.target.value;
                              setChartFilterState({ ...chartFilterState, search: val });
                              if (!val) {
                                handleChartFilterChange({ search: "" });
                              }
                            }}
                            onPressEnter={() => handleChartFilterChange({ search: chartFilterState.search })}
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Brand"
                            optionFilterProp="label"
                            popupMatchSelectWidth={false}
                            value={chartFilterState.brand}
                            options={chartData.filterOptions.brand.map((option) => ({
                              label: `${option.label} (${option.count.toLocaleString()})`,
                              value: option.value,
                            }))}
                            onChange={(value) => handleChartFilterChange({ brand: value })}
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Model"
                            optionFilterProp="label"
                            showSearch
                            popupMatchSelectWidth={false}
                            value={chartFilterState.model}
                            options={chartData.filterOptions.model.map((option) => ({
                              label: `${option.label} (${option.count.toLocaleString()})`,
                              value: option.value,
                            }))}
                            onChange={(value) => handleChartFilterChange({ model: value })}
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Model year"
                            optionFilterProp="label"
                            popupMatchSelectWidth={false}
                            value={chartFilterState.modelYear}
                            options={chartData.filterOptions.modelYear.map((option) => ({
                              label: `${option.label} (${option.count.toLocaleString()})`,
                              value: option.value,
                            }))}
                            onChange={(value) => handleChartFilterChange({ modelYear: value })}
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Part"
                            optionFilterProp="label"
                            showSearch
                            popupMatchSelectWidth={false}
                            value={chartFilterState.part}
                            options={chartData.filterOptions.part.map((option) => ({
                              label: `${option.label} (${option.count.toLocaleString()})`,
                              value: option.value,
                            }))}
                            onChange={(value) => handleChartFilterChange({ part: value })}
                          />
                          <RangePicker
                            value={
                              chartFilterState.startDate && chartFilterState.endDate
                                ? [dayjs(chartFilterState.startDate), dayjs(chartFilterState.endDate)]
                                : null
                            }
                            minDate={chartData.filterOptions.dateRange.min ? dayjs(chartData.filterOptions.dateRange.min) : undefined}
                            maxDate={chartData.filterOptions.dateRange.max ? dayjs(chartData.filterOptions.dateRange.max) : undefined}
                            onChange={(values) =>
                              handleChartFilterChange({
                                startDate: values?.[0]?.format("YYYY-MM-DD") ?? "",
                                endDate: values?.[1]?.format("YYYY-MM-DD") ?? "",
                              })
                            }
                          />
                          <Button
                            onClick={() => {
                              const cleared = { ...defaultTableState, pageSize: chartFilterState.pageSize };
                              setChartFilterState(cleared);
                              loadChartData(workspace.sheetName, cleared);
                            }}
                          >
                            Clear
                          </Button>
                          <Button type="primary" onClick={syncFiltersFromTable}>
                            Sync from Data Table
                          </Button>
                        </div>
                      </Card>
                    )}

                    {chartLoading ? (
                      <div className="loading-shell" style={{ minHeight: "40vh" }}>
                        <div className="loading-card">
                          <Spin size="large" />
                          <p className="loading-msg">Refreshing charts…</p>
                        </div>
                      </div>
                    ) : chartData ? (
                      <div className="chart-grid">
                        {chartData.insights.monthlyInstallation ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                "Monthly installation quantity",
                                chartData.insights.monthlyInstallation.labels,
                                chartData.insights.monthlyInstallation.values,
                                "line"
                              )}
                              style={{ height: 320 }}
                            />
                          </Card>
                        ) : null}
                        {chartData.insights.monthlyRevenue ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                "Monthly revenue",
                                chartData.insights.monthlyRevenue.labels,
                                chartData.insights.monthlyRevenue.values,
                                "area"
                              )}
                              style={{ height: 320 }}
                            />
                          </Card>
                        ) : null}
                        {chartData.insights.topModels ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                "Top vehicle models by revenue",
                                chartData.insights.topModels.labels,
                                chartData.insights.topModels.values,
                                "bar"
                              )}
                              style={{ height: 320 }}
                            />
                          </Card>
                        ) : null}
                        {chartData.insights.topParts ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                chartData.insights.topParts.title,
                                chartData.insights.topParts.labels,
                                chartData.insights.topParts.values,
                                "bar"
                              )}
                              style={{ height: 320 }}
                            />
                          </Card>
                        ) : null}
                        {!Object.keys(chartData.insights).length ? (
                          <Card className="content-card">
                            <Empty
                              image={Empty.PRESENTED_IMAGE_SIMPLE}
                              description="The selected worksheet does not expose enough business-ready fields for the default insight set."
                            />
                          </Card>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ),
              },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: "forecasting",
                label: "Forecast Center",
                children: (
                  <div className="major-tab-stack">
                    <Card className="content-card major-tab-intro">
                      <div className="major-tab-header">
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Forecast Center</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            Review anomaly signals, understand structural demand changes, and inspect part-level forecast confidence in one place.
                          </Paragraph>
                        </div>
                      </div>
                    </Card>
                    <Tabs
                      className="workspace-subtabs"
                      defaultActiveKey="anomaly"
                      items={[
              {
                key: "anomaly",
                label: "Anomaly Center",
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>V2 Anomaly Detection</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            Anomaly Center scans the current filtered slice for structural drops, sudden ramps, unstable parts, and low-trust forecast zones.
                          </Paragraph>
                        </div>
                        <Space wrap>
                          <Button type="primary" onClick={syncAnomalyFromTable}>
                            Refresh from Data Table
                          </Button>
                        </Space>
                      </div>
                    </Card>

                    {anomalyLoading ? (
                      <div className="loading-shell" style={{ minHeight: "40vh" }}>
                        <div className="loading-card">
                          <Spin size="large" />
                          <p className="loading-msg">Scanning for structural demand changes…</p>
                        </div>
                      </div>
                    ) : anomalyData ? (
                      <>
                        <Row gutter={[18, 18]}>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Scanned parts" value={anomalyData.summary.scannedParts} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Surfaced alerts" value={anomalyData.summary.surfacedAlerts} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Structural breaks" value={anomalyData.summary.structuralBreaks} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="High forecast risk" value={anomalyData.summary.highRiskForecasts} />
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24} xl={10}>
                            <Card className="content-card" title="Why these alerts surfaced" style={{ height: "100%" }}>
                              <div className="summary-stack">
                                <div className="summary-row">
                                  <span className="summary-dot" />
                                  <span>The scanner ranks parts by recent change magnitude, anomaly months, regime shift shape, and backtest reliability.</span>
                                </div>
                                <div className="summary-row">
                                  <span className="summary-dot" />
                                  <span>Structural drops and ramps are treated as highest risk because historical moving averages usually miss these state changes.</span>
                                </div>
                                <div className="summary-row">
                                  <span className="summary-dot" />
                                  <span>Low-confidence forecasts are not hidden. They are surfaced so planners know where human review matters most.</span>
                                </div>
                              </div>
                            </Card>
                          </Col>
                          <Col xs={24} xl={14}>
                            <Card className="chart-card" title="Alert regime mix">
                              {anomalyData.regimeBreakdown.length ? (
                                <ReactECharts
                                  option={chartOption(
                                    "Alert regime mix",
                                    anomalyData.regimeBreakdown.map((item) => item.label),
                                    anomalyData.regimeBreakdown.map((item) => item.count),
                                    "bar"
                                  )}
                                  style={{ height: 320 }}
                                />
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No regime mix available for the current slice." />
                              )}
                            </Card>
                          </Col>
                        </Row>

                        {anomalyData.records.length ? (
                          <div className="classification-stack">
                            {anomalyData.records.map((record) => (
                              <Card
                                key={record.part}
                                className="content-card"
                                title={`${record.part}${record.partDescription ? ` · ${record.partDescription}` : ""}`}
                                extra={
                                  <Space wrap size={8}>
                                    <Tag color={record.forecastRisk === "High" ? "red" : record.forecastRisk === "Medium" ? "gold" : "blue"}>
                                      {record.forecastRisk} forecast risk
                                    </Tag>
                                    <Tag color={record.confidence === "High" ? "blue" : record.confidence === "Medium" ? "gold" : "default"}>
                                      {record.confidence} confidence
                                    </Tag>
                                    <Tag color={record.regimeSeverity === "High" ? "red" : record.regimeSeverity === "Medium" ? "gold" : "default"}>
                                      {record.regime}
                                    </Tag>
                                  </Space>
                                }
                              >
                                <Row gutter={[18, 18]}>
                                  <Col xs={24} xl={8}>
                                    <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                                      <div>
                                        <span className="health-label">Latest month</span>
                                        <strong>{record.latestMonth}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">History months</span>
                                        <strong>{record.historyMonths}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Latest actual</span>
                                        <strong>{formatMetric(record.latestActual)} pcs</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Recent 3M avg</span>
                                        <strong>{formatMetric(record.recent3MonthAverage)} pcs</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">MoM change</span>
                                        <strong>{record.deltaPct !== null ? `${record.deltaPct >= 0 ? "+" : ""}${record.deltaPct.toFixed(1)}%` : "N/A"}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Backtest WAPE</span>
                                        <strong>{record.wape !== null ? `${(record.wape * 100).toFixed(1)}%` : "N/A"}</strong>
                                      </div>
                                      <div style={{ gridColumn: "span 2" }}>
                                        <span className="health-label">Next baseline forecast</span>
                                        <strong>
                                          {formatMetric(record.nextForecast)} pcs
                                          {record.forecastDeltaPct !== null ? ` (${record.forecastDeltaPct >= 0 ? "+" : ""}${record.forecastDeltaPct.toFixed(1)}%)` : ""}
                                        </strong>
                                      </div>
                                    </div>
                                  </Col>
                                  <Col xs={24} xl={8}>
                                    <Card bordered={false} style={{ background: "rgba(248, 250, 255, 0.82)", height: "100%" }}>
                                      <div style={{ fontWeight: 700, marginBottom: 10 }}>Evidence trail</div>
                                      <div className="summary-stack">
                                        {record.evidence.map((line) => (
                                          <div key={line} className="summary-row">
                                            <span className="summary-dot" />
                                            <span>{line}</span>
                                          </div>
                                        ))}
                                      </div>
                                    </Card>
                                  </Col>
                                  <Col xs={24} xl={8}>
                                    <div style={{ display: "grid", gap: 16 }}>
                                      <Card bordered={false} style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Wholesale-linked model</div>
                                        {record.wholesaleSignal ? (
                                          <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                                            <div>
                                              <span className="health-label">Link strength</span>
                                              <strong>{record.wholesaleSignal.relationshipStrength}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Model WAPE</span>
                                              <strong>{record.wholesaleSignal.modelWape !== null ? `${(record.wholesaleSignal.modelWape * 100).toFixed(1)}%` : "N/A"}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Wholesale delta</span>
                                              <strong>{record.wholesaleSignal.wholesaleDeltaPct !== null ? `${record.wholesaleSignal.wholesaleDeltaPct >= 0 ? "+" : ""}${record.wholesaleSignal.wholesaleDeltaPct.toFixed(1)}%` : "N/A"}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Expected by model</span>
                                              <strong>{formatMetric(record.wholesaleSignal.expectedFromModel)} pcs</strong>
                                            </div>
                                            <div style={{ gridColumn: "span 2" }}>
                                              <span className="health-label">Unexplained residual</span>
                                              <strong>
                                                {record.wholesaleSignal.unexplainedResidualPct !== null
                                                  ? `${record.wholesaleSignal.unexplainedResidualPct >= 0 ? "+" : ""}${record.wholesaleSignal.unexplainedResidualPct.toFixed(1)}%`
                                                  : "N/A"}
                                              </strong>
                                            </div>
                                          </div>
                                        ) : (
                                          <Text type="secondary">No wholesale-linked model could be fit for this part with the current workbook structure.</Text>
                                        )}
                                      </Card>
                                      <Card bordered={false} style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Brand drivers</div>
                                        {record.brandDrivers.length ? (
                                          <div className="summary-stack">
                                            {record.brandDrivers.map((item) => (
                                              <div key={`${record.part}-brand-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                                                <span>{item.name}</span>
                                                <strong style={{ color: item.delta < 0 ? "#b42318" : "#155eef" }}>
                                                  {item.delta >= 0 ? "+" : ""}{formatMetric(item.delta)}
                                                </strong>
                                              </div>
                                            ))}
                                          </div>
                                        ) : (
                                          <Text type="secondary">No brand-level shift surfaced in this slice.</Text>
                                        )}
                                      </Card>
                                      <Card bordered={false} style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Model drivers</div>
                                        {record.modelDrivers.length ? (
                                          <div className="summary-stack">
                                            {record.modelDrivers.map((item) => (
                                              <div key={`${record.part}-model-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                                                <span>{item.name}</span>
                                                <strong style={{ color: item.delta < 0 ? "#b42318" : "#155eef" }}>
                                                  {item.delta >= 0 ? "+" : ""}{formatMetric(item.delta)}
                                                </strong>
                                              </div>
                                            ))}
                                          </div>
                                        ) : (
                                          <Text type="secondary">No model-level shift surfaced in this slice.</Text>
                                        )}
                                      </Card>
                                    </div>
                                  </Col>
                                </Row>
                              </Card>
                            ))}
                          </div>
                        ) : (
                          <Card className="content-card">
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No anomaly alerts surfaced for the current slice." />
                          </Card>
                        )}
                      </>
                    ) : (
                      <Card className="content-card">
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Anomaly center data is not available for this worksheet yet." />
                      </Card>
                    )}
                  </div>
                ),
              },
              {
                key: "forecast",
                label: "Forecast Center",
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Part-Month Baseline Forecast</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            Forecast Center uses the current Data Table filters for brand, model, model year, search, and date range.
                          </Paragraph>
                        </div>
                        <Space wrap>
                          <Select
                            showSearch
                            style={{ minWidth: 320 }}
                            placeholder="Select a part number"
                            optionFilterProp="label"
                            value={forecastPart || undefined}
                            options={forecastData?.partOptions.map((option) => ({
                              label: `${option.value}${option.description ? ` · ${option.description}` : ""}`,
                              value: option.value,
                            })) ?? []}
                            onChange={(value) => {
                              setForecastPart(value);
                              loadForecastData(workspace.sheetName, tableState, value, forecastHorizon);
                            }}
                          />
                          <Select
                            style={{ width: 160 }}
                            value={forecastHorizon}
                            options={[
                              { label: "1 month", value: 1 },
                              { label: "3 months", value: 3 },
                              { label: "6 months", value: 6 },
                              { label: "12 months", value: 12 },
                            ]}
                            onChange={(value) => {
                              setForecastHorizon(value);
                              loadForecastData(workspace.sheetName, tableState, forecastPart, value);
                            }}
                          />
                          <Button type="primary" onClick={syncForecastFromTable}>
                            Refresh from Data Table
                          </Button>
                        </Space>
                      </div>
                    </Card>

                    {forecastLoading ? (
                      <div className="loading-shell" style={{ minHeight: "40vh" }}>
                        <div className="loading-card">
                          <Spin size="large" />
                          <p className="loading-msg">Building part-level forecast…</p>
                        </div>
                      </div>
                    ) : forecastData ? (
                      <>
                        <Row gutter={[18, 18]}>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Next month forecast" value={formatMetric(forecastData.summary.nextForecast)} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Latest actual month" value={formatMetric(forecastData.summary.latestActual)} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Recent 3-month average" value={formatMetric(forecastData.summary.recent3MonthAverage)} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Backtest WAPE" value={forecastData.summary.wape !== null ? `${(forecastData.summary.wape * 100).toFixed(1)}%` : "N/A"} />
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24} xl={16}>
                            <Card
                              className="chart-card"
                              title={`${forecastData.selectedPart}${forecastData.partDescription ? ` · ${forecastData.partDescription}` : ""}`}
                              extra={<Tag color={forecastData.summary.confidence === "High" ? "blue" : forecastData.summary.confidence === "Medium" ? "gold" : "default"}>{forecastData.summary.confidence} confidence</Tag>}
                            >
                              <ReactECharts option={forecastChartOption(forecastData)} style={{ height: 360 }} />
                            </Card>
                          </Col>
                          <Col xs={24} xl={8}>
                            <Card className="content-card" title="Model readout" style={{ height: "100%" }}>
                              <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr", rowGap: 12 }}>
                                <div>
                                  <span className="health-label">Model</span>
                                  <strong>{forecastData.summary.modelName.replaceAll("_", " ")}</strong>
                                </div>
                                <div>
                                  <span className="health-label">History months</span>
                                  <strong>{forecastData.summary.historyMonths}</strong>
                                </div>
                                <div>
                                  <span className="health-label">MAE</span>
                                  <strong>{forecastData.summary.mae !== null ? formatMetric(forecastData.summary.mae) : "N/A"}</strong>
                                </div>
                                <div>
                                  <span className="health-label">Bias</span>
                                  <strong>{forecastData.summary.bias !== null ? `${(forecastData.summary.bias * 100).toFixed(1)}%` : "N/A"}</strong>
                                </div>
                                <div>
                                  <span className="health-label">Data path</span>
                                  <strong>{forecastData.summary.preprocessing === "cleaned" ? "Anomaly-softened" : "Raw history"}</strong>
                                </div>
                                <div>
                                  <span className="health-label">WAPE</span>
                                  <strong>{forecastData.summary.wape !== null ? `${(forecastData.summary.wape * 100).toFixed(1)}%` : "N/A"}</strong>
                                </div>
                                <div style={{ gridColumn: "span 2", borderTop: "1px solid #f0f4f9", paddingTop: 10 }}>
                                  <span className="health-label">Next month change</span>
                                  <strong>
                                    {forecastData.summary.deltaPct !== null
                                      ? `${forecastData.summary.deltaPct >= 0 ? "+" : ""}${forecastData.summary.deltaPct.toFixed(1)}%`
                                      : "N/A"}
                                  </strong>
                                </div>
                                {forecastData.summary.selectionBasis ? (
                                  <div style={{ gridColumn: "span 2", borderTop: "1px solid #f0f4f9", paddingTop: 10 }}>
                                    <span className="health-label">Selection logic</span>
                                    <strong style={{ fontSize: 13, lineHeight: 1.5 }}>{forecastData.summary.selectionBasis}</strong>
                                  </div>
                                ) : null}
                                {forecastData.summary.adjustedMonths > 0 ? (
                                  <div style={{ gridColumn: "span 2" }}>
                                    <span className="health-label">Adjusted anomaly months</span>
                                    <strong>{forecastData.summary.adjustedMonths}</strong>
                                  </div>
                                ) : null}
                                {forecastData.summary.candidateScores.length ? (
                                  <div style={{ gridColumn: "span 2" }}>
                                    <span className="health-label">Candidate WAPE ranking</span>
                                    <div className="summary-stack" style={{ marginTop: 8 }}>
                                      {forecastData.summary.candidateScores.slice(0, 4).map((item) => (
                                        <div key={`${item.model}-${item.preprocessing ?? "raw"}`} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "6px 0", borderBottom: "1px solid #f0f4f9" }}>
                                          <span>{(item.label ?? item.model).replaceAll("_", " ")}</span>
                                          <strong>{item.wape !== null ? `${(item.wape * 100).toFixed(1)}%` : "N/A"}</strong>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24} xl={12}>
                            <Card className="content-card" title="Forecast interpretation" style={{ height: "100%" }}>
                              <div className="summary-stack">
                                {forecastData.insights.map((line) => (
                                  <div key={line} className="summary-row">
                                    <span className="summary-dot" />
                                    <span>{line}</span>
                                  </div>
                                ))}
                              </div>
                            </Card>
                          </Col>
                          <Col xs={24} xl={12}>
                            <Card className="content-card" title="Latest change explanation" style={{ height: "100%" }}>
                              {forecastData.changeAnalysis ? (
                                <div className="summary-stack">
                                  {forecastData.changeAnalysis.notes.map((line) => (
                                    <div key={line} className="summary-row">
                                      <span className="summary-dot" />
                                      <span>{line}</span>
                                    </div>
                                  ))}
                                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f0f4f9" }}>
                                    <div style={{ color: "#607087", fontSize: 12, marginBottom: 6 }}>
                                      {forecastData.changeAnalysis.previousMonth} {"->"} {forecastData.changeAnalysis.latestMonth}
                                    </div>
                                    <strong>
                                      {formatMetric(forecastData.changeAnalysis.previousActual)} pcs {"->"} {formatMetric(forecastData.changeAnalysis.latestActual)} pcs
                                    </strong>
                                  </div>
                                </div>
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Not enough complete months to explain the latest change." />
                              )}
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24} xl={12}>
                            <Card className="content-card" title="Anomaly radar" style={{ height: "100%" }}>
                              {forecastData.anomalies.length ? (
                                <div className="summary-stack">
                                  {forecastData.anomalies.map((item) => (
                                    <div key={item.month} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 0", borderBottom: "1px solid #f0f4f9" }}>
                                      <div>
                                        <Text strong>{item.month}</Text>
                                        <div style={{ color: "#607087", fontSize: 12 }}>
                                          Actual {formatMetric(item.actual)} pcs
                                          {item.baseline !== null ? ` vs baseline ${formatMetric(item.baseline)} pcs` : ""}
                                        </div>
                                      </div>
                                      <div style={{ textAlign: "right" }}>
                                        <div style={{ fontWeight: 700, color: item.deltaPct !== null && item.deltaPct < 0 ? "#b42318" : "#155eef" }}>
                                          {item.deltaPct !== null ? `${item.deltaPct >= 0 ? "+" : ""}${item.deltaPct.toFixed(1)}%` : "N/A"}
                                        </div>
                                        <Tag color={item.severity === "High" ? "red" : "gold"} style={{ marginInlineEnd: 0 }}>
                                          {item.severity}
                                        </Tag>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No statistically notable anomaly months were detected yet." />
                              )}
                            </Card>
                          </Col>
                          <Col xs={24} xl={12}>
                            <Card className="content-card" title="Primary drivers" style={{ height: "100%" }}>
                              {forecastData.changeAnalysis ? (
                                <div style={{ display: "grid", gap: 16 }}>
                                  <div>
                                    <div style={{ fontWeight: 700, marginBottom: 8 }}>Brand contribution</div>
                                    {forecastData.changeAnalysis.brandDrivers.length ? (
                                      <div className="summary-stack">
                                        {forecastData.changeAnalysis.brandDrivers.map((item) => (
                                          <div key={`brand-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "6px 0", borderBottom: "1px solid #f0f4f9" }}>
                                            <span>{item.name}</span>
                                            <strong style={{ color: item.delta < 0 ? "#b42318" : "#155eef" }}>
                                              {item.delta >= 0 ? "+" : ""}{formatMetric(item.delta)} pcs
                                            </strong>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <Text type="secondary">No brand-level driver signal in the current slice.</Text>
                                    )}
                                  </div>
                                  <div>
                                    <div style={{ fontWeight: 700, marginBottom: 8 }}>Model contribution</div>
                                    {forecastData.changeAnalysis.modelDrivers.length ? (
                                      <div className="summary-stack">
                                        {forecastData.changeAnalysis.modelDrivers.map((item) => (
                                          <div key={`model-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "6px 0", borderBottom: "1px solid #f0f4f9" }}>
                                            <span>{item.name}</span>
                                            <strong style={{ color: item.delta < 0 ? "#b42318" : "#155eef" }}>
                                              {item.delta >= 0 ? "+" : ""}{formatMetric(item.delta)} pcs
                                            </strong>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <Text type="secondary">No model-level driver signal in the current slice.</Text>
                                    )}
                                  </div>
                                </div>
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Driver breakdown becomes available once at least two complete months exist." />
                              )}
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24}>
                            <Card className="content-card" title="Recommended watchlist" style={{ height: "100%" }}>
                              {forecastData.watchlist.length ? (
                                <div className="summary-stack">
                                  {forecastData.watchlist.map((item) => (
                                    <div key={item.part} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 0", borderBottom: "1px solid #f0f4f9" }}>
                                      <div>
                                        <Text strong>{item.part}</Text>
                                        <div style={{ color: "#607087", fontSize: 12 }}>
                                          Latest {formatMetric(item.latestActual)} pcs {"->"} Forecast {formatMetric(item.nextForecast)} pcs
                                        </div>
                                      </div>
                                      <div style={{ textAlign: "right" }}>
                                        <div style={{ fontWeight: 700, color: item.deltaPct !== null && item.deltaPct < 0 ? "#b42318" : "#155eef" }}>
                                          {item.deltaPct !== null ? `${item.deltaPct >= 0 ? "+" : ""}${item.deltaPct.toFixed(1)}%` : "N/A"}
                                        </div>
                                        <Tag color={item.confidence === "High" ? "blue" : item.confidence === "Medium" ? "gold" : "default"} style={{ marginInlineEnd: 0 }}>
                                          {item.confidence}
                                        </Tag>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No watchlist signals available for the current slice." />
                              )}
                            </Card>
                          </Col>
                        </Row>
                      </>
                    ) : (
                      <Card className="content-card">
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Forecast data is not available for this worksheet yet." />
                      </Card>
                    )}
                  </div>
                ),
              },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: "agent",
                label: "AI Analyst",
                children: (
                  <div className="major-tab-stack">
                    <Card className="content-card major-tab-intro">
                      <div className="major-tab-header">
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>AI Analyst</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            This workspace is where the future agent will investigate demand shifts, challenge weak forecasts, and answer planning questions from trusted data tools.
                          </Paragraph>
                        </div>
                        <Tag color="blue">Agent-ready foundation</Tag>
                      </div>
                    </Card>

                    <Row gutter={[18, 18]}>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="Rows in scope" value={workspace.profile.row_count} />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="Alerts ready" value={anomalyData?.summary.surfacedAlerts ?? 0} />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="High-risk forecasts" value={anomalyData?.summary.highRiskForecasts ?? 0} />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="Selected forecast confidence" value={forecastData?.summary.confidence ?? "N/A"} />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[18, 18]}>
                      <Col xs={24} xl={10}>
                        <Card className="content-card" title="Suggested Analyst Questions" style={{ height: "100%" }}>
                          <div className="summary-stack">
                            {analystPrompts.map((prompt) => (
                              <div key={prompt} className="summary-row">
                                <span className="summary-dot" />
                                <span>{prompt}</span>
                              </div>
                            ))}
                          </div>
                        </Card>
                      </Col>
                      <Col xs={24} xl={7}>
                        <Card className="content-card" title="Current Best Lead" style={{ height: "100%" }}>
                          {topAlert ? (
                            <div className="summary-stack">
                              <div className="summary-row">
                                <span className="summary-dot" />
                                <span>
                                  <strong>{topAlert.part}</strong>
                                  {topAlert.partDescription ? ` · ${topAlert.partDescription}` : ""}
                                </span>
                              </div>
                              <div className="summary-row">
                                <span className="summary-dot" />
                                <span>{topAlert.regime} with {topAlert.forecastRisk.toLowerCase()} forecast risk.</span>
                              </div>
                              {topAlert.evidence.slice(0, 3).map((line) => (
                                <div key={line} className="summary-row">
                                  <span className="summary-dot" />
                                  <span>{line}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No anomaly lead is available yet." />
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} xl={7}>
                        <Card className="content-card" title="Trusted Tool Chain" style={{ height: "100%" }}>
                          <div className="summary-stack">
                            <div className="summary-row">
                              <span className="summary-dot" />
                              <span>Structured sheet parsing and field classification</span>
                            </div>
                            <div className="summary-row">
                              <span className="summary-dot" />
                              <span>Anomaly scoring with regime detection and backtest evidence</span>
                            </div>
                            <div className="summary-row">
                              <span className="summary-dot" />
                              <span>Part-level forecast with confidence, WAPE, bias, and watchlist outputs</span>
                            </div>
                            <div className="summary-row">
                              <span className="summary-dot" />
                              <span>Wholesale-linked model signals where a learnable relationship exists</span>
                            </div>
                          </div>
                        </Card>
                      </Col>
                    </Row>

                    <Card className="content-card" title="Agent Roadmap">
                      <div className="summary-stack">
                        <div className="summary-row">
                          <span className="summary-dot" />
                          <span>Next step: let the agent call anomaly, forecast, and wholesale-linked tools instead of inventing explanations.</span>
                        </div>
                        <div className="summary-row">
                          <span className="summary-dot" />
                          <span>Then add guided outputs such as: root-cause hypotheses, confidence-ranked explanations, and recommended planner actions.</span>
                        </div>
                        <div className="summary-row">
                          <span className="summary-dot" />
                          <span>After that, connect the same tool chain to forecast overrides, penetration analysis, and inventory recommendations.</span>
                        </div>
                      </div>
                    </Card>
                  </div>
                ),
              },
            ]}
          />
        </section>
      ) : null}
    </main>
  );
}
