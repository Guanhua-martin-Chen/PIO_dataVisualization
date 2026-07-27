"use client";

import {
  AreaChartOutlined,
  CalculatorOutlined,
  DatabaseOutlined,
  DownloadOutlined,
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
  InputNumber,
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

import WorkspaceHeader from "./components/WorkspaceHeader";
import ForecastCenterPanel from "./components/ForecastCenterPanel";
import { WorkspaceError, WorkspaceLoading } from "./components/WorkspaceState";
import {
  AnalystPayload,
  AnalystMemoryItem,
  AnomalyCenterPayload,
  API_BASE_URL,
  ForecastCenterPayload,
  ForecastPayload,
  HierarchicalForecastPayload,
  MonthlyFactsPayload,
  PivotPayload,
  WorkbookMeta,
  WorkspacePayload,
  TableState,
  defaultTableState,
  forecastChartOption,
  formatMetric,
  chartOption,
  buildWorkspaceParams,
} from "../../app/shared";

const { RangePicker } = DatePicker;
const { Title, Paragraph, Text } = Typography;

type InventorySource = {
  part: string;
  partDescription: string | null;
  monthlyForecast: number;
  wape: number | null;
  forecastRisk: string;
  reliabilityTier: string;
};

type InventoryPlanRow = InventorySource & {
  key: string;
  horizonDemand: number;
  leadTimeDemand: number;
  safetyStock: number;
  reorderPoint: number;
  targetStock: number;
  currentInventory: number | null;
  onOrder: number | null;
  suggestedOrder: number | null;
  coverageMonths: number | null;
  riskLabel: string;
  riskCode: "stockout" | "overstock" | "balanced" | "input_needed";
};

interface WorkspacePageProps {
  params: Promise<{ id: string }>;
}

function serviceLevelMultiplier(serviceLevel: number) {
  if (serviceLevel >= 99) return 2.33;
  if (serviceLevel >= 98) return 2.05;
  if (serviceLevel >= 95) return 1.65;
  if (serviceLevel >= 90) return 1.28;
  return 1;
}

function riskErrorFallback(forecastRisk: string) {
  if (forecastRisk === "High") return 0.45;
  if (forecastRisk === "Medium") return 0.28;
  return 0.16;
}

function roundToPack(value: number, packSize: number) {
  const normalizedPack = Math.max(1, Math.floor(packSize || 1));
  return Math.ceil(Math.max(0, value) / normalizedPack) * normalizedPack;
}

function escapeCsvCell(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
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
  const [dataSubTab, setDataSubTab] = useState("overview");
  const [tableState, setTableState] = useState<TableState>(defaultTableState);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chartFilterState, setChartFilterState] = useState<TableState>(defaultTableState);
  const [chartData, setChartData] = useState<WorkspacePayload | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [edaLoading, setEdaLoading] = useState(false);
  const [monthlyFacts, setMonthlyFacts] = useState<MonthlyFactsPayload | null>(null);
  const [monthlyFactsLoading, setMonthlyFactsLoading] = useState(false);
  const [forecastFilterState, setForecastFilterState] = useState<TableState>(defaultTableState);
  const [forecastFilterOptions, setForecastFilterOptions] = useState<WorkspacePayload["filterOptions"] | null>(null);
  const [anomalyData, setAnomalyData] = useState<AnomalyCenterPayload | null>(null);
  const [anomalyLoading, setAnomalyLoading] = useState(false);
  const [anomalyFocusPart, setAnomalyFocusPart] = useState("");
  const [forecastData, setForecastData] = useState<ForecastPayload | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastView, setForecastView] = useState("hierarchy");
  const [hierarchicalForecast] = useState<HierarchicalForecastPayload | null>(null);
  const [forecastCenterData, setForecastCenterData] = useState<ForecastCenterPayload | null>(null);
  const [hierarchicalForecastLoading, setHierarchicalForecastLoading] = useState(false);
  const [forecastMetric, setForecastMetric] = useState<"revenue" | "quantity" | "wholesale_quantity">("revenue");
  const [hierarchyLevel, setHierarchyLevel] = useState<"brand" | "model" | "plc" | "model_plc">("brand");
  const [hierarchyModelStrategy, setHierarchyModelStrategy] = useState("auto");
  const [useWorkingDays, setUseWorkingDays] = useState(true);
  const [useSeasonality, setUseSeasonality] = useState(true);
  const [tariffImpactPct, setTariffImpactPct] = useState(0);
  const [minimumMonthlyVolume, setMinimumMonthlyVolume] = useState(5);
  const [analystQuestion, setAnalystQuestion] = useState("");
  const [analystAnswer, setAnalystAnswer] = useState<AnalystPayload | null>(null);
  const [analystLoading, setAnalystLoading] = useState(false);
  const [analystMemories, setAnalystMemories] = useState<AnalystMemoryItem[]>([]);
  const [analystMemoryLoading, setAnalystMemoryLoading] = useState(false);
  const [aiFocusPart, setAiFocusPart] = useState("");
  const [forecastPart, setForecastPart] = useState("");
  const [forecastHorizon, setForecastHorizon] = useState(3);
  const [inventoryCurrentStock, setInventoryCurrentStock] = useState(0);
  const [inventoryOnOrder, setInventoryOnOrder] = useState(0);
  const [inventoryLeadTimeDays, setInventoryLeadTimeDays] = useState(45);
  const [inventoryReviewDays, setInventoryReviewDays] = useState(30);
  const [inventoryServiceLevel, setInventoryServiceLevel] = useState(95);
  const [inventoryPackSize, setInventoryPackSize] = useState(1);
  const [inventoryManualBufferPct, setInventoryManualBufferPct] = useState(10);
  const [pivotData, setPivotData] = useState<PivotPayload | null>(null);
  const [pivotLoading, setPivotLoading] = useState(false);
  const [pivotRows, setPivotRows] = useState<string[]>(["part"]);
  const [pivotCols, setPivotCols] = useState<string[]>(["month"]);
  const [pivotMeasure, setPivotMeasure] = useState("quantity");
  const [pivotAgg, setPivotAgg] = useState("sum");
  const [pivotDragField, setPivotDragField] = useState<string | null>(null);
  const pivotFilterKey = JSON.stringify({
    search: tableState.search,
    brand: tableState.brand,
    model: tableState.model,
    modelYear: tableState.modelYear,
    part: tableState.part,
    startDate: tableState.startDate,
    endDate: tableState.endDate,
  });

  function resolveForecastSheetName(fallback: string) {
    const sheetNames = workbook?.sheetNames ?? workspace?.workbook.sheetNames ?? [];
    return sheetNames.find((name) => name.trim().toLowerCase() === "pio_sales_data") ?? fallback;
  }

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

  async function loadWorkspaceData(sheetName: string, state: TableState, silent = false, includeEdaDashboard = false) {
    const params = buildWorkspaceParams(state);
    if (includeEdaDashboard) {
      params.set("include_eda_dashboard", "true");
      setEdaLoading(true);
    } else if (!silent) {
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
      const governedForecastSheet = (
        payload.workbook.sheetNames.find((name) => name.trim().toLowerCase() === "pio_sales_data")
        ?? payload.sheetName
      );
      if (payload.sheetName === governedForecastSheet) {
        setForecastFilterOptions(payload.filterOptions);
      }
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
        if (payload.sheetName === governedForecastSheet) {
          setForecastFilterState(initialChartState);
          loadForecastData(governedForecastSheet, initialChartState, "", forecastHorizon);
          loadHierarchicalForecast(governedForecastSheet, initialChartState, "brand", "revenue");
        }
        loadAnalystMemories(payload.sheetName);
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load worksheet data.");
    } finally {
      if (includeEdaDashboard) {
        setEdaLoading(false);
      } else if (!silent) {
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
    loadWorkspaceData(workspace.sheetName, nextState, false, dataSubTab === "eda");
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
    const governedForecastSheet = resolveForecastSheetName(sheetName);
    const params = buildWorkspaceParams({ ...state, page: 1, part: [] });
    params.set("horizon", String(horizon));
    if (nextPart) {
      params.set("part_number", nextPart);
    }

    setForecastLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load forecast view.");
      }
      const payload = (await response.json()) as ForecastPayload;
      setForecastData(payload);
      setForecastPart(payload.selectedPart);
      setAiFocusPart((current) => current || payload.selectedPart);
      setForecastHorizon(horizon);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load forecast view.");
    } finally {
      setForecastLoading(false);
    }
  }

  async function loadMonthlyFacts(sheetName: string, state: TableState, page = 1, pageSize = 100) {
    const params = buildWorkspaceParams({ ...state, page, pageSize });
    setMonthlyFactsLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}/monthly-facts?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to build monthly facts.");
      }
      setMonthlyFacts((await response.json()) as MonthlyFactsPayload);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to build monthly facts.");
    } finally {
      setMonthlyFactsLoading(false);
    }
  }

  async function loadHierarchicalForecast(
    sheetName: string,
    state: TableState,
    level = hierarchyLevel,
    metric = forecastMetric,
    horizon = forecastHorizon,
  ) {
    const governedForecastSheet = resolveForecastSheetName(sheetName);
    const hierarchyState = {
      ...state,
      search: "",
      modelYear: [],
      part: [],
      page: 1,
    };
    const params = buildWorkspaceParams(hierarchyState);
    params.set("level", level);
    params.set("metric", metric);
    params.set("horizon", String(horizon));
    params.set("use_working_days", String(useWorkingDays));
    params.set("use_seasonality", String(useSeasonality));
    params.set("tariff_impact_pct", String(tariffImpactPct));
    params.set("model_strategy", hierarchyModelStrategy);
    params.set("min_monthly_volume", String(minimumMonthlyVolume));
    params.set("top_n", "10");
    setHierarchicalForecastLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast-center?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to run hierarchical forecast.");
      }
      setForecastCenterData((await response.json()) as ForecastCenterPayload);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to run hierarchical forecast.");
    } finally {
      setHierarchicalForecastLoading(false);
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
      setAnomalyFocusPart((current) => {
        if (current && payload.records.some((record) => record.part === current)) {
          return current;
        }
        return payload.records[0]?.part ?? "";
      });
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load anomaly center.");
    } finally {
      setAnomalyLoading(false);
    }
  }

  async function askAnalyst(question = analystQuestion) {
    if (!workspace) return;
    const trimmed = question.trim();
    if (!trimmed) {
      messageApi.warning("Enter a planning question first.");
      return;
    }

    setAnalystLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(workspace.sheetName)}/analyst`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: trimmed,
            focus_part: aiFocusPart || forecastPart,
            horizon: forecastHorizon,
            search: tableState.search,
            brand: tableState.brand,
            model: tableState.model,
            model_year: tableState.modelYear,
            part: tableState.part,
            start_date: tableState.startDate,
            end_date: tableState.endDate,
          }),
        }
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to run AI Analyst.");
      }
      const payload = (await response.json()) as AnalystPayload;
      setAnalystQuestion(trimmed);
      setAnalystAnswer(payload);
      loadAnalystMemories(workspace.sheetName);
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to run AI Analyst.");
    } finally {
      setAnalystLoading(false);
    }
  }

  async function loadAnalystMemories(sheetName: string) {
    setAnalystMemoryLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}/analyst/memories?limit=10`
      );
      if (!response.ok) {
        throw new Error("Failed to load analyst memory.");
      }
      const payload = (await response.json()) as { items: AnalystMemoryItem[] };
      setAnalystMemories(payload.items);
    } catch {
      setAnalystMemories([]);
    } finally {
      setAnalystMemoryLoading(false);
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
      if (payload.measure !== measure) {
        setPivotMeasure(payload.measure);
      }
      if (payload.agg !== agg) {
        setPivotAgg(payload.agg);
      }

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

  // Rebuild the pivot whenever its configuration changes (and the sheet is ready).
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
    const governedForecastSheet = resolveForecastSheetName(workspace.sheetName);
    if (forecastView === "hierarchy") {
      const compatibleState = {
        ...tableState,
        search: "",
        brand: tableState.brand.filter((brand) => ["HMA", "GMA", "KUS"].includes(brand)),
        modelYear: [],
        part: [],
        page: 1,
      };
      setForecastFilterState(compatibleState);
      loadHierarchicalForecast(
        governedForecastSheet,
        compatibleState,
        hierarchyLevel,
        forecastMetric,
      );
      messageApi.info(
        "Forecast Center synchronized governed HMA/GMA/KUS, model, and date filters. Source H/K, search, model year, and part filters stay in Data Workspace because they do not match the anchor grain."
      );
      return;
    }
    setForecastFilterState(tableState);
    loadForecastData(governedForecastSheet, tableState, forecastPart, forecastHorizon);
    messageApi.success("Part forecast refreshed with current Data Table filters");
  }

  function applyForecastFilters(updates: Partial<TableState>) {
    if (!workspace) return;
    const nextState = {
      ...forecastFilterState,
      ...updates,
      page: 1,
    };
    setForecastFilterState(nextState);
    setForecastPart("");
    if (forecastView === "hierarchy") {
      loadHierarchicalForecast(
        resolveForecastSheetName(workspace.sheetName),
        nextState,
        hierarchyLevel,
        forecastMetric,
      );
    } else {
      loadForecastData(resolveForecastSheetName(workspace.sheetName), nextState, "", forecastHorizon);
    }
  }

  function resetForecastFilters() {
    if (!workspace) return;
    const cleared = { ...defaultTableState, pageSize: forecastFilterState.pageSize || tableState.pageSize };
    setForecastFilterState(cleared);
    setForecastPart("");
    if (forecastView === "hierarchy") {
      loadHierarchicalForecast(
        resolveForecastSheetName(workspace.sheetName),
        cleared,
        hierarchyLevel,
        forecastMetric,
      );
    } else {
      loadForecastData(resolveForecastSheetName(workspace.sheetName), cleared, "", forecastHorizon);
    }
  }

  function syncAnomalyFromTable() {
    if (!workspace) return;
    loadAnomalyData(workspace.sheetName, tableState);
    messageApi.success("Anomaly Center refreshed with current Data Table filters");
  }

  function handleDataSubTabChange(key: string) {
    setDataSubTab(key);
    if (key === "eda" && workspace && !workspace.edaDashboard) {
      loadWorkspaceData(workspace.sheetName, tableState, true, true);
    }
    if (key === "monthly-facts" && workspace) {
      loadMonthlyFacts(workspace.sheetName, tableState, 1, monthlyFacts?.pageSize ?? 100);
    }
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
      loadWorkspaceData(workspace.sheetName, nextState, false, dataSubTab === "eda");
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

  function exportForecastCsv() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({ ...forecastFilterState, page: 1 });
    params.delete("page");
    params.delete("page_size");
    params.delete("sort_field");
    params.delete("sort_order");
    params.delete("part");
    params.set("part_number", forecastPart || forecastData?.selectedPart || "");
    params.set("horizon", String(forecastHorizon));
    const governedForecastSheet = resolveForecastSheetName(workspace.sheetName);
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast/export.csv?${params.toString()}`,
      "_blank"
    );
  }

  function exportForecastXlsx() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({ ...forecastFilterState, page: 1 });
    params.delete("page");
    params.delete("page_size");
    params.delete("sort_field");
    params.delete("sort_order");
    params.delete("part");
    params.set("part_number", forecastPart || forecastData?.selectedPart || "");
    params.set("horizon", String(forecastHorizon));
    const governedForecastSheet = resolveForecastSheetName(workspace.sheetName);
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast/export.xlsx?${params.toString()}`,
      "_blank"
    );
  }

  function exportForecastCenterCsv() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({
      ...forecastFilterState,
      search: "",
      modelYear: [],
      part: [],
      page: 1,
    });
    params.delete("page");
    params.delete("page_size");
    params.delete("sort_field");
    params.delete("sort_order");
    params.set("metric", forecastMetric);
    params.set("level", hierarchyLevel);
    params.set("horizon", String(forecastHorizon));
    params.set("top_n", "10");
    params.set("use_working_days", String(useWorkingDays));
    params.set("use_seasonality", String(useSeasonality));
    params.set("tariff_impact_pct", String(tariffImpactPct));
    params.set("model_strategy", hierarchyModelStrategy);
    params.set("min_monthly_volume", String(minimumMonthlyVolume));
    const governedForecastSheet = resolveForecastSheetName(workspace.sheetName);
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast-center/export.csv?${params.toString()}`,
      "_blank"
    );
  }

  function exportForecastCenterXlsx() {
    if (!workbook || !workspace) return;
    const params = new URLSearchParams({
      horizon: String(forecastHorizon),
      top_n: "10",
      use_working_days: String(useWorkingDays),
      use_seasonality: String(useSeasonality),
      tariff_impact_pct: String(tariffImpactPct),
      model_strategy: hierarchyModelStrategy,
      min_monthly_volume: String(minimumMonthlyVolume),
    });
    const governedForecastSheet = resolveForecastSheetName(workspace.sheetName);
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(governedForecastSheet)}/forecast-center/export.xlsx?${params.toString()}`,
      "_blank"
    );
  }

  const governedForecastFilterOptions = forecastFilterOptions ?? workspace?.filterOptions;
  const columnsList = columnOrder.length > 0
    ? columnOrder.map((key) => workspace?.table.columns.find((c) => c.key === key)!)
    : (workspace?.table.columns ?? []);

  function formatOptionalNumber(value: number | null | undefined, currency = false, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
    return currency
      ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)
      : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
  }

  function renderForecastCenterPanel() {
    return (
      <ForecastCenterPanel
        data={forecastCenterData}
        loading={hierarchicalForecastLoading}
        metric={forecastMetric}
        level={hierarchyLevel}
        modelStrategy={hierarchyModelStrategy}
        useWorkingDays={useWorkingDays}
        useSeasonality={useSeasonality}
        tariffImpactPct={tariffImpactPct}
        minMonthlyVolume={minimumMonthlyVolume}
        onMetricChange={(nextMetric) => {
          const nextLevel = nextMetric === "wholesale_quantity" && ["plc", "model_plc"].includes(hierarchyLevel)
            ? "model"
            : hierarchyLevel;
          setForecastMetric(nextMetric);
          if (nextMetric !== "revenue" && hierarchyModelStrategy === "reference_portfolio") {
            setHierarchyModelStrategy("auto");
          }
          setHierarchyLevel(nextLevel);
          if (workspace) {
            loadHierarchicalForecast(workspace.sheetName, forecastFilterState, nextLevel, nextMetric);
          }
        }}
        onLevelChange={(nextLevel) => {
          setHierarchyLevel(nextLevel);
          if (workspace) {
            loadHierarchicalForecast(workspace.sheetName, forecastFilterState, nextLevel, forecastMetric);
          }
        }}
        onModelStrategyChange={(strategy) => {
          setHierarchyModelStrategy(strategy);
          if (strategy === "reference_portfolio") {
            setUseWorkingDays(true);
            setUseSeasonality(true);
          }
        }}
        onWorkingDaysChange={setUseWorkingDays}
        onSeasonalityChange={setUseSeasonality}
        onTariffImpactChange={setTariffImpactPct}
        onMinMonthlyVolumeChange={setMinimumMonthlyVolume}
        onRun={() => workspace && loadHierarchicalForecast(
          workspace.sheetName,
          forecastFilterState,
          hierarchyLevel,
          forecastMetric,
        )}
        onExportCsv={exportForecastCenterCsv}
        onExportXlsx={exportForecastCenterXlsx}
      />
    );
  }

  function renderEdaDashboard() {
    const eda = workspace?.edaDashboard;
    if (!eda) {
      return (
        <Card className="content-card">
          <Spin spinning={edaLoading}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="Open this tab to build EDA metrics for the current filtered slice."
            />
          </Spin>
        </Card>
      );
    }

    const topTableColumns: TableColumnsType<{ name: string; value: number }> = [
      {
        title: "Name",
        dataIndex: "name",
        key: "name",
        ellipsis: true,
      },
      {
        title: "Revenue",
        dataIndex: "value",
        key: "value",
        align: "right",
        render: (value: number) => formatMetric(value, true),
      },
    ];

    return (
      <Spin spinning={edaLoading}>
        <div className="tab-stack">
          <Card className="content-card major-tab-intro">
            <div className="major-tab-header">
              <div>
                <div className="eyebrow" style={{ marginBottom: 8 }}>EDA Dashboard</div>
                <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                  Exploratory checks for the uploaded sales slice, with wholesale trends read from the workbook when a wholesale sheet is available.
                </Paragraph>
              </div>
              <Tag color="blue">EDA-only</Tag>
            </div>
          </Card>

          <Row gutter={[18, 18]}>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="Rows in scope" value={formatMetric(eda.overview.rowCount)} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="Detected models" value={formatMetric(eda.overview.modelCount)} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="Model codes" value={formatMetric(eda.overview.modelCodeCount)} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="Distinct parts" value={formatMetric(eda.overview.partCount)} />
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24} xl={8}>
              <Card className="content-card" title="Data overview" style={{ height: "100%" }}>
                <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr", rowGap: 12 }}>
                  <div>
                    <span className="health-label">Time range</span>
                    <strong>
                      {eda.overview.timeRange.min && eda.overview.timeRange.max
                        ? `${eda.overview.timeRange.min} to ${eda.overview.timeRange.max}`
                        : "N/A"}
                    </strong>
                  </div>
                  <div>
                    <span className="health-label">Brands</span>
                    <strong>{formatMetric(eda.overview.brandCount)}</strong>
                  </div>
                  <div>
                    <span className="health-label">PIO revenue</span>
                    <strong>{formatOptionalNumber(eda.overview.totalRevenue, true)}</strong>
                  </div>
                  <div>
                    <span className="health-label">Installed qty</span>
                    <strong>{formatOptionalNumber(eda.overview.totalQuantity)}</strong>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card className="content-card" title="Missing value check" style={{ height: "100%" }}>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="field"
                  columns={[
                    { title: "Field", dataIndex: "field", key: "field" },
                    { title: "Column", dataIndex: "column", key: "column", render: (value) => value ?? "-" },
                    { title: "Missing", dataIndex: "missing", key: "missing", align: "right" },
                    {
                      title: "%",
                      dataIndex: "missingPct",
                      key: "missingPct",
                      align: "right",
                      render: (value: number) => `${value.toFixed(2)}%`,
                    },
                  ]}
                  dataSource={eda.dataQuality.missing}
                />
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card className="content-card" title="Outlier and consistency check" style={{ height: "100%" }}>
                <div className="summary-stack">
                  <div className="summary-row"><span className="summary-dot" /><span>Negative revenue rows: {eda.dataQuality.outliers.negativeRevenueRows}</span></div>
                  <div className="summary-row"><span className="summary-dot" /><span>Negative quantity rows: {eda.dataQuality.outliers.negativeQuantityRows}</span></div>
                  <div className="summary-row"><span className="summary-dot" /><span>Zero quantity rows: {eda.dataQuality.outliers.zeroQuantityRows}</span></div>
                  <div className="summary-row"><span className="summary-dot" /><span>Unit price p01/p99 outliers: {eda.dataQuality.outliers.unitPriceOutlierRows}</span></div>
                  <div className="summary-row">
                    <span className="summary-dot" />
                    <span>
                      Unit price range: {formatOptionalNumber(eda.dataQuality.outliers.unitPriceP01, true)} to{" "}
                      {formatOptionalNumber(eda.dataQuality.outliers.unitPriceP99, true)}
                    </span>
                  </div>
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24} xl={10}>
              <Card className="content-card" title="Top brands">
                <Table
                  size="small"
                  rowKey="name"
                  pagination={false}
                  columns={topTableColumns}
                  dataSource={eda.rankings.topBrands}
                />
              </Card>
            </Col>
            <Col xs={24} xl={14}>
              <Card className="content-card" title="Revenue and wholesale relationship" style={{ height: "100%" }}>
                <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr", rowGap: 12 }}>
                  <div>
                    <span className="health-label">Monthly correlation</span>
                    <strong>{formatOptionalNumber(eda.relationship.revenueWholesaleCorrelation, false, 3)}</strong>
                  </div>
                  <div>
                    <span className="health-label">Model code coverage</span>
                    <strong>
                      {eda.relationship.modelCodeCoveragePct === null
                        ? "N/A"
                        : `${eda.relationship.modelCodeCoveragePct.toFixed(2)}%`}
                    </strong>
                  </div>
                  <div>
                    <span className="health-label">Sales model codes</span>
                    <strong>{eda.relationship.salesModelCodes}</strong>
                  </div>
                  <div>
                    <span className="health-label">Wholesale model codes</span>
                    <strong>{eda.relationship.wholesaleModelCodes}</strong>
                  </div>
                  <div>
                    <span className="health-label">Model-name coverage</span>
                    <strong>
                      {eda.relationship.modelNameCoveragePct === null
                        ? "N/A"
                        : `${eda.relationship.modelNameCoveragePct.toFixed(2)}%`}
                    </strong>
                  </div>
                  <div>
                    <span className="health-label">Ambiguous model codes</span>
                    <strong>
                      {eda.relationship.ambiguousSalesModelCodes.length} sales /{" "}
                      {eda.relationship.ambiguousWholesaleModelCodes.length} wholesale
                    </strong>
                  </div>
                </div>
                {eda.relationship.ambiguousWholesaleModelCodes.length ? (
                  <Alert
                    style={{ marginTop: 12 }}
                    type="warning"
                    showIcon
                    message="Model Code is not a unique vehicle key"
                    description={eda.relationship.ambiguousWholesaleModelCodes
                      .slice(0, 5)
                      .map((item) => `${item.value}: ${item.models.join(", ")}`)
                      .join(" · ")}
                  />
                ) : null}
                {eda.relationship.unmatchedSalesModelCodes.length ? (
                  <Alert
                    style={{ marginTop: 12 }}
                    type="warning"
                    showIcon
                    message="Unmatched PIS_SERI samples"
                    description={
                      <div className="summary-stack">
                        {eda.relationship.unmatchedSalesModelCodes.map((item) => {
                          const value = typeof item === "string" ? item : item.value;
                          const rows = typeof item === "string" ? [] : item.rows ?? [];
                          return (
                            <div key={value} className="summary-row">
                              <span className="summary-dot" />
                              <span>
                                {value}: {rows.length ? `Excel row ${rows.join(", ")}` : "source row unavailable"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    }
                  />
                ) : null}
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24}>
              <Card
                className="content-card"
                title={`Source H/K code → official anchor audit${eda.sourceAnchorAudit.latestMonth ? ` (${eda.sourceAnchorAudit.latestMonth})` : ""}`}
              >
                <Alert
                  type="warning"
                  showIcon
                  message="PIS_CMP_KND is a source-system code, not the final forecast brand"
                  description="The tables below make the H/K-to-HMA/GMA/KUS mapping visible. In particular, Source H can contain Kia models, so the official anchor is assigned from the dealer-wholesale model mapping."
                  style={{ marginBottom: 16 }}
                />
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => `${record.sourceCode}:${record.anchorBrand}`}
                  dataSource={eda.sourceAnchorAudit.summary}
                  columns={[
                    { title: "Source code", dataIndex: "sourceCode", key: "sourceCode" },
                    {
                      title: "Official anchor",
                      dataIndex: "anchorBrand",
                      key: "anchorBrand",
                      render: (value: string) => <Tag color={value === "KUS" ? "purple" : value === "GMA" ? "cyan" : "blue"}>{value}</Tag>,
                    },
                    {
                      title: "PIO Quantity",
                      dataIndex: "pioQuantity",
                      key: "pioQuantity",
                      align: "right" as const,
                      render: (value: number) => formatMetric(value),
                    },
                    {
                      title: "PIO Revenue",
                      dataIndex: "pioRevenue",
                      key: "pioRevenue",
                      align: "right" as const,
                      render: (value: number) => formatMetric(value, true),
                    },
                  ]}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24}>
              <Card className="content-card" title="Source H model, model-year, and sales-period audit">
                <Paragraph className="workspace-copy">
                  This table shows exactly which Source H models become HMA, GMA, or KUS, their vehicle model years,
                  invoice-date coverage, latest-month PIO quantity, and the mapping method used.
                </Paragraph>
                <Table
                  size="small"
                  rowKey={(record) => `${record.anchorBrand}:${record.modelName}`}
                  pagination={{ pageSize: 12, hideOnSinglePage: true }}
                  dataSource={eda.sourceAnchorAudit.sourceHModels}
                  columns={[
                    {
                      title: "Anchor",
                      dataIndex: "anchorBrand",
                      key: "anchorBrand",
                      fixed: "left" as const,
                      render: (value: string) => <Tag color={value === "KUS" ? "purple" : value === "GMA" ? "cyan" : "blue"}>{value}</Tag>,
                    },
                    { title: "Source H model", dataIndex: "modelName", key: "modelName", fixed: "left" as const },
                    {
                      title: "Model year(s)",
                      dataIndex: "modelYears",
                      key: "modelYears",
                      render: (values: string[]) => values.length ? values.join(", ") : "-",
                    },
                    {
                      title: "Sales year(s)",
                      dataIndex: "salesYears",
                      key: "salesYears",
                      render: (values: string[]) => values.length ? values.join(", ") : "-",
                    },
                    {
                      title: "Invoice-date coverage",
                      key: "coverage",
                      render: (_: unknown, record) => `${record.firstSaleDate} to ${record.lastSaleDate}`,
                    },
                    {
                      title: `${eda.sourceAnchorAudit.latestMonth ?? "Latest"} PIO Qty`,
                      dataIndex: "latestMonthQuantity",
                      key: "latestMonthQuantity",
                      align: "right" as const,
                      render: (value: number) => formatMetric(value),
                    },
                    {
                      title: "All-period PIO Qty",
                      dataIndex: "totalQuantity",
                      key: "totalQuantity",
                      align: "right" as const,
                      render: (value: number) => formatMetric(value),
                    },
                    {
                      title: "All-period PIO Revenue",
                      dataIndex: "totalRevenue",
                      key: "totalRevenue",
                      align: "right" as const,
                      render: (value: number) => formatMetric(value, true),
                    },
                    { title: "Mapping", dataIndex: "mappingMethod", key: "mappingMethod" },
                  ]}
                  scroll={{ x: 1450 }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24}>
              <Card className="content-card" title="Model entity mapping and lifecycle">
                <Paragraph className="workspace-copy">
                  Vehicle entities are keyed by brand and normalized model name. Model code is retained only as an attribute,
                  so variants sharing a code remain distinct. Lifecycle status is calculated from positive PIO activity rather
                  than manually assigned.
                </Paragraph>
                <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
                  <Col xs={12} md={6}>
                    <Statistic title="Model entities" value={eda.modelEntities.count} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title={`Discontinued through ${eda.modelLifecycle.cutoffYear}`} value={eda.modelLifecycle.discontinuedCount} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="Reintroduced" value={eda.modelLifecycle.reintroducedCount} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="Lifecycle as of" value={eda.modelLifecycle.asOfMonth ?? "N/A"} />
                  </Col>
                </Row>
                <Table
                  size="small"
                  rowKey="entityKey"
                  pagination={{ pageSize: 12, hideOnSinglePage: true }}
                  columns={[
                    { title: "Model", dataIndex: "modelName", key: "modelName", fixed: "left" as const },
                    { title: "Brand", dataIndex: "brand", key: "brand" },
                    {
                      title: "Model code(s)",
                      dataIndex: "modelCodes",
                      key: "modelCodes",
                      render: (values: string[]) => values.length ? values.join(", ") : "-",
                    },
                    {
                      title: "Status",
                      dataIndex: "statusCode",
                      key: "statusCode",
                      render: (value: "active" | "inactive" | "discontinued" | "reintroduced", record) => (
                        <Tag color={value === "discontinued" ? "red" : value === "reintroduced" ? "blue" : value === "inactive" ? "gold" : "green"}>
                          {record.status}
                        </Tag>
                      ),
                    },
                    { title: "Last positive", dataIndex: "lastPositiveMonth", key: "lastPositiveMonth" },
                    { title: "Restarted", dataIndex: "reintroducedMonth", key: "reintroducedMonth", render: (value: string | null) => value ?? "-" },
                    { title: "Code-derived evidence", dataIndex: "evidence", key: "evidence", ellipsis: true },
                  ]}
                  dataSource={eda.modelLifecycle.records}
                  scroll={{ x: 1050 }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24}>
              <Card className="content-card" title="Part number vs description discrepancies">
                <Paragraph className="workspace-copy">
                  This check finds cases where one part number maps to multiple part descriptions. It helps catch naming drift,
                  duplicated descriptions, or source-system text changes before part-level analysis and forecasting.
                </Paragraph>
                {eda.dataQuality.partDescriptionIssues.length ? (
                  <Table
                    size="small"
                    rowKey="partNumber"
                    pagination={false}
                    columns={[
                      { title: "Part number", dataIndex: "partNumber", key: "partNumber" },
                      {
                        title: "Type",
                        dataIndex: "issueType",
                        key: "issueType",
                        render: (value: "description_mismatch" | "format_warning") => (
                          <Tag color={value === "description_mismatch" ? "red" : "gold"}>
                            {value === "description_mismatch" ? "Description mismatch" : "Case/format warning"}
                          </Tag>
                        ),
                      },
                      { title: "Descriptions", dataIndex: "descriptionCount", key: "descriptionCount", align: "right" },
                      { title: "Variants", dataIndex: "variantCount", key: "variantCount", align: "right" },
                      { title: "Rows", dataIndex: "rows", key: "rows", align: "right" },
                      {
                        title: "Samples",
                        dataIndex: "descriptions",
                        key: "descriptions",
                        render: (values: string[]) => values.join(" | "),
                      },
                    ]}
                    dataSource={eda.dataQuality.partDescriptionIssues}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No part-description discrepancies found." />
                )}
              </Card>
            </Col>
          </Row>
        </div>
      </Spin>
    );
  }

  function renderMonthlyFacts() {
    if (!monthlyFacts) {
      return (
        <Card className="content-card">
          <Spin spinning={monthlyFactsLoading}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Open this tab to build the unified 2023–2026 monthly fact table." />
          </Spin>
        </Card>
      );
    }
    return (
      <div className="tab-stack">
        <Alert
          type="info"
          showIcon
          message="Forecasting source of truth"
          description={`One row represents ${monthlyFacts.summary.grain}. PIO source brand stays visible, while HMA/GMA/KUS is the governed forecast anchor. Wholesale units are a dealer/non-fleet model-month reference and must not be summed across accessories.`}
        />
        <Row gutter={[18, 18]}>
          <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Fact rows" value={monthlyFacts.summary.rowCount} /></Card></Col>
          <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Months" value={monthlyFacts.summary.monthCount} /></Card></Col>
          <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Model entities" value={monthlyFacts.summary.modelCount} /></Card></Col>
          <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Accessories" value={monthlyFacts.summary.partCount} /></Card></Col>
        </Row>
        <Row gutter={[18, 18]}>
          <Col xs={24} md={12}>
            <Card className="content-card" title="Coverage">
              <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <div><span className="health-label">Period</span><strong>{monthlyFacts.summary.minMonth} to {monthlyFacts.summary.maxMonth}</strong></div>
                <div><span className="health-label">Working Days</span><strong>{monthlyFacts.summary.workingDaysCoveragePct.toFixed(1)}%</strong></div>
                <div><span className="health-label">Wholesale reference</span><strong>{monthlyFacts.summary.wholesaleCoveragePct.toFixed(1)}%</strong></div>
                <div><span className="health-label">Anchor mapping coverage</span><strong>{monthlyFacts.summary.dealerWholesaleExactQuantityCoveragePct.toFixed(1)}%</strong></div>
                <div><span className="health-label">Official anchors</span><strong>{monthlyFacts.summary.anchorCount}</strong></div>
                <div><span className="health-label">PIO revenue</span><strong>{formatMetric(monthlyFacts.summary.totalRevenue, true)}</strong></div>
              </div>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card className="content-card" title="Why this table exists">
              <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                It converts transaction-like PIO rows and wide wholesale sheets into one auditable monthly grain used by brand,
                model, and model-accessory forecasts. Working Days and lifecycle status are joined once here so every model uses
                identical inputs.
              </Paragraph>
            </Card>
          </Col>
        </Row>
        <Card className="content-card" title="Unified monthly facts">
          <Table
            size="small"
            rowKey={(record) => `${record.month}-${record.entityKey}-${record.partNumber}`}
            loading={monthlyFactsLoading}
            dataSource={monthlyFacts.rows}
            columns={[
              { title: "Month", dataIndex: "month", key: "month", fixed: "left" as const },
              { title: "Source H/K code", dataIndex: "brand", key: "brand" },
              { title: "Anchor", dataIndex: "anchorBrand", key: "anchorBrand" },
              { title: "Anchor mapping", dataIndex: "anchorMappingMethod", key: "anchorMappingMethod" },
              { title: "Model", dataIndex: "modelName", key: "modelName" },
              { title: "PLC", dataIndex: "plc", key: "plc" },
              { title: "Accessory", dataIndex: "partNumber", key: "partNumber" },
              { title: "Description", dataIndex: "partDescription", key: "partDescription", ellipsis: true },
              { title: "Lifecycle", dataIndex: "lifecycleStatus", key: "lifecycleStatus" },
              { title: "PIO qty", dataIndex: "installationQuantity", key: "installationQuantity", align: "right" as const, render: (value: number) => formatMetric(value) },
              { title: "PIO revenue", dataIndex: "pioRevenue", key: "pioRevenue", align: "right" as const, render: (value: number) => formatMetric(value, true) },
              { title: "Wholesale", dataIndex: "wholesaleUnits", key: "wholesaleUnits", align: "right" as const, render: (value: number | null) => value === null ? "-" : formatMetric(value) },
              { title: "Units / vehicle", dataIndex: "accessoryUnitsPerVehicle", key: "accessoryUnitsPerVehicle", align: "right" as const, render: (value: number | null) => value === null ? "-" : formatOptionalNumber(value, false, 3) },
              { title: "Revenue / vehicle (PNVW)", dataIndex: "revenuePerVehicle", key: "revenuePerVehicle", align: "right" as const, render: (value: number | null) => value === null ? "-" : formatOptionalNumber(value, true) },
              { title: "Working days", dataIndex: "workingDays", key: "workingDays", align: "right" as const, render: (value: number | null) => value ?? "-" },
              { title: "Qty/day", dataIndex: "quantityPerWorkingDay", key: "quantityPerWorkingDay", align: "right" as const, render: (value: number | null) => value === null ? "-" : value.toFixed(2) },
            ]}
            pagination={{
              current: monthlyFacts.page,
              pageSize: monthlyFacts.pageSize,
              total: monthlyFacts.totalRows,
              showSizeChanger: true,
              onChange: (page, pageSize) => workspace && loadMonthlyFacts(workspace.sheetName, tableState, page, pageSize),
            }}
            scroll={{ x: 1500 }}
          />
        </Card>
      </div>
    );
  }

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
  const selectedAnomalyRecord =
    anomalyData?.records.find((record) => record.part === anomalyFocusPart) ??
    anomalyData?.records[0] ??
    null;
  const analystPrompts = [
    topAlert ? `Why did ${topAlert.part} move so sharply in ${topAlert.latestMonth}?` : "Why did the top alert part move so sharply last month?",
    forecastData ? `Can the current forecast for ${forecastData.selectedPart} be trusted?` : "Can the current part-level forecast be trusted?",
    "Which parts look like structural demand drops rather than normal monthly volatility?",
    "Which alerts are explained by vehicle wholesale movement versus part-specific factors?",
  ];
  const selectedPortfolioRecord = forecastData?.portfolio.records.find((record) => record.part === forecastData.selectedPart);
  const inventorySources: InventorySource[] = forecastData
    ? [
        {
          part: forecastData.selectedPart,
          partDescription: forecastData.partDescription,
          monthlyForecast: forecastData.summary.nextForecast,
          wape: forecastData.summary.wape,
          forecastRisk: forecastData.summary.forecastRisk,
          reliabilityTier: selectedPortfolioRecord?.reliabilityTier ?? forecastData.summary.confidence,
        },
        ...forecastData.portfolio.records
          .filter((record) => record.part !== forecastData.selectedPart)
          .slice(0, 24)
          .map((record) => ({
            part: record.part,
            partDescription: record.partDescription,
            monthlyForecast: record.nextForecast,
            wape: record.wape,
            forecastRisk: record.forecastRisk,
            reliabilityTier: record.reliabilityTier,
          })),
      ]
    : [];

  function buildInventoryPlan(source: InventorySource, isSelected: boolean): InventoryPlanRow {
    const monthlyForecast = Math.max(0, source.monthlyForecast || 0);
    const dailyForecast = monthlyForecast / 30;
    const protectionDays = Math.max(1, inventoryLeadTimeDays + inventoryReviewDays);
    const leadTimeDemand = dailyForecast * Math.max(0, inventoryLeadTimeDays);
    const horizonDemand = monthlyForecast * Math.max(1, forecastHorizon);
    const demandDuringProtection = dailyForecast * protectionDays;
    const forecastError = source.wape ?? riskErrorFallback(source.forecastRisk);
    const buffer = Math.max(0, inventoryManualBufferPct) / 100;
    const safetyStock = demandDuringProtection * (forecastError + buffer) * serviceLevelMultiplier(inventoryServiceLevel);
    const reorderPoint = leadTimeDemand + safetyStock;
    const targetStock = demandDuringProtection + safetyStock;
    const currentInventory = isSelected ? Math.max(0, inventoryCurrentStock) : null;
    const onOrder = isSelected ? Math.max(0, inventoryOnOrder) : null;
    const netAvailable = (currentInventory ?? 0) + (onOrder ?? 0);
    const suggestedOrder = isSelected ? roundToPack(targetStock - netAvailable, inventoryPackSize) : null;
    const coverageMonths = isSelected && monthlyForecast > 0 ? netAvailable / monthlyForecast : null;
    let riskCode: InventoryPlanRow["riskCode"] = "input_needed";
    let riskLabel = "Inventory input needed";

    if (isSelected) {
      if (monthlyForecast === 0) {
        riskCode = netAvailable > 0 ? "overstock" : "balanced";
        riskLabel = netAvailable > 0 ? "No demand signal / possible excess" : "No immediate reorder";
      } else if (netAvailable < reorderPoint) {
        riskCode = "stockout";
        riskLabel = "Below reorder point";
      } else if (netAvailable > targetStock * 1.5) {
        riskCode = "overstock";
        riskLabel = "Potential overstock";
      } else {
        riskCode = "balanced";
        riskLabel = "Within planning band";
      }
    }

    return {
      ...source,
      key: source.part,
      horizonDemand,
      leadTimeDemand,
      safetyStock,
      reorderPoint,
      targetStock,
      currentInventory,
      onOrder,
      suggestedOrder,
      coverageMonths,
      riskLabel,
      riskCode,
    };
  }

  const inventoryPlanRows = inventorySources.map((source, index) =>
    buildInventoryPlan(source, index === 0)
  );
  const selectedInventoryPlan = inventoryPlanRows[0] ?? null;
  const inventoryRiskColor =
    selectedInventoryPlan?.riskCode === "stockout"
      ? "red"
      : selectedInventoryPlan?.riskCode === "overstock"
        ? "gold"
        : "green";

  function exportInventoryCsv() {
    if (!inventoryPlanRows.length) return;
    const headers = [
      "Part",
      "Part Description",
      "Monthly Forecast",
      "Horizon Demand",
      "Lead Time Demand",
      "Safety Stock",
      "Reorder Point",
      "Target Stock",
      "Current Inventory",
      "On Order",
      "Suggested Order",
      "Coverage Months",
      "Risk",
      "Forecast Risk",
      "WAPE",
      "Reliability",
    ];
    const rows = inventoryPlanRows.map((row) => [
      row.part,
      row.partDescription,
      Math.round(row.monthlyForecast),
      Math.round(row.horizonDemand),
      Math.round(row.leadTimeDemand),
      Math.round(row.safetyStock),
      Math.round(row.reorderPoint),
      Math.round(row.targetStock),
      row.currentInventory,
      row.onOrder,
      row.suggestedOrder,
      row.coverageMonths === null ? "" : row.coverageMonths.toFixed(2),
      row.riskLabel,
      row.forecastRisk,
      row.wape === null ? "" : `${(row.wape * 100).toFixed(1)}%`,
      row.reliabilityTier,
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map(escapeCsvCell).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `inventory-simulator-${forecastData?.selectedPart ?? "plan"}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="page-shell">
      {contextHolder}

      <div style={{ marginBottom: 20 }}>
        <Link href="/" style={{ color: "var(--accent)", fontWeight: 500, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <LeftOutlined style={{ fontSize: 12 }} /> Back to Home
        </Link>
      </div>

      {loading ? (
        <WorkspaceLoading message={loadingMsg} />
      ) : error ? (
        <WorkspaceError error={error} onGoHome={() => router.push("/")} />
      ) : workspace ? (
        <section className="workspace-shell">
          <WorkspaceHeader
            filename={workspace.workbook.filename}
            headerRow={workspace.profile.header_row}
            headerDepth={workspace.profile.header_depth}
            rowCount={workspace.profile.row_count}
            sheetName={workspace.sheetName}
            sheetNames={workspace.workbook.sheetNames}
            onSheetChange={(value) => {
              setVisibleColumns([]);
              loadWorkspaceData(value, { ...defaultTableState, pageSize: tableState.pageSize });
            }}
          />

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            className="workspace-tabs"
            items={[
              {
                key: "data",
                label: (
                  <div className="major-tab-label">
                    <span className="major-tab-icon">
                      <DatabaseOutlined />
                    </span>
                    <span className="major-tab-copy">
                      <strong>Data Workspace</strong>
                      <small>Inspect and shape the source slice</small>
                    </span>
                  </div>
                ),
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
                        <Space wrap className="major-tab-actions">
                          <Tag color="blue">Current filtered slice</Tag>
                          <Button onClick={exportCsv}>Export CSV</Button>
                          <Button type="primary" onClick={exportXlsx}>
                            Export Excel
                          </Button>
                        </Space>
                      </div>
                    </Card>
                    <Tabs
                      className="workspace-subtabs"
                      activeKey={dataSubTab}
                      onChange={handleDataSubTabChange}
                      items={[
              {
                key: "overview",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Overview</strong>
                    <small>Summary</small>
                  </span>
                ),
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
                key: "eda",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>EDA Dashboard</strong>
                    <small>Diagnostics</small>
                  </span>
                ),
                children: renderEdaDashboard(),
              },
              {
                key: "monthly-facts",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Monthly Facts</strong>
                    <small>2023–2026</small>
                  </span>
                ),
                children: renderMonthlyFacts(),
              },
              {
                key: "pivot",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Pivot Table</strong>
                    <small>Cross-tab</small>
                  </span>
                ),
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
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Data Table</strong>
                    <small>Records</small>
                  </span>
                ),
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
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Visual Charts</strong>
                    <small>Trends</small>
                  </span>
                ),
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
                        {chartData.insights.monthlyWholesale ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                chartData.insights.monthlyWholesale.title,
                                chartData.insights.monthlyWholesale.labels,
                                chartData.insights.monthlyWholesale.values,
                                "line"
                              )}
                              style={{ height: 320 }}
                            />
                          </Card>
                        ) : null}
                        {chartData.insights.monthlyPnvw ? (
                          <Card className="chart-card">
                            <ReactECharts
                              option={chartOption(
                                chartData.insights.monthlyPnvw.title,
                                chartData.insights.monthlyPnvw.labels,
                                chartData.insights.monthlyPnvw.values,
                                "line"
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
                label: (
                  <div className="major-tab-label">
                    <span className="major-tab-icon">
                      <AreaChartOutlined />
                    </span>
                    <span className="major-tab-copy">
                      <strong>Forecast Center</strong>
                      <small>Backtest, explain, and export forecasts</small>
                    </span>
                  </div>
                ),
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
                        <div>
                          <Space wrap className="major-tab-actions">
                            {forecastData?.selectedPart ? <Tag color="blue">Focus part: {forecastData.selectedPart}</Tag> : null}
                            <Button onClick={exportForecastCsv} disabled={!forecastData}>
                              Export Forecast CSV
                            </Button>
                            <Button type="primary" onClick={exportForecastXlsx} disabled={!forecastData}>
                              Export Forecast Excel
                            </Button>
                          </Space>
                          <div style={{ marginTop: 6, color: "#6b7b95", fontSize: 12, textAlign: "right" }}>
                            Reminder: HMA currently uses dealer/non-fleet wholesale as its vehicle denominator; fleet is excluded.
                          </div>
                        </div>
                      </div>
                    </Card>
                    <Tabs
                      className="workspace-subtabs"
                      defaultActiveKey="anomaly"
                      items={[
              {
                key: "anomaly",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Anomaly Center</strong>
                    <small>Signals</small>
                  </span>
                ),
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
                            <Card
                              className="content-card"
                              title="Alert part selector"
                              extra={<Tag>{anomalyData.records.length} alerts</Tag>}
                            >
                              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                                <Select
                                  showSearch
                                  value={selectedAnomalyRecord?.part || undefined}
                                  placeholder="Select an alert part"
                                  optionFilterProp="label"
                                  style={{ width: "100%" }}
                                  options={anomalyData.records.map((record) => ({
                                    label: `${record.part}${record.partDescription ? ` · ${record.partDescription}` : ""}`,
                                    value: record.part,
                                  }))}
                                  onChange={setAnomalyFocusPart}
                                />
                                {selectedAnomalyRecord ? (
                                  <div style={{ color: "#607087", fontSize: 13 }}>
                                    Showing the detailed anomaly view for <strong style={{ color: "#122033" }}>{selectedAnomalyRecord.part}</strong>.
                                  </div>
                                ) : null}
                              </Space>
                            </Card>
                            {selectedAnomalyRecord ? (
                              <Card
                                key={selectedAnomalyRecord.part}
                                className="content-card"
                                title={`${selectedAnomalyRecord.part}${selectedAnomalyRecord.partDescription ? ` · ${selectedAnomalyRecord.partDescription}` : ""}`}
                                extra={
                                  <Space wrap size={8}>
                                    <Tag color={selectedAnomalyRecord.forecastRisk === "High" ? "red" : selectedAnomalyRecord.forecastRisk === "Medium" ? "gold" : "blue"}>
                                      {selectedAnomalyRecord.forecastRisk} forecast risk
                                    </Tag>
                                    <Tag color={selectedAnomalyRecord.confidence === "High" ? "blue" : selectedAnomalyRecord.confidence === "Medium" ? "gold" : "default"}>
                                      {selectedAnomalyRecord.confidence} confidence
                                    </Tag>
                                    <Tag color={selectedAnomalyRecord.regimeSeverity === "High" ? "red" : selectedAnomalyRecord.regimeSeverity === "Medium" ? "gold" : "default"}>
                                      {selectedAnomalyRecord.regime}
                                    </Tag>
                                  </Space>
                                }
                              >
                                <Row gutter={[18, 18]}>
                                  <Col xs={24} xl={8}>
                                    <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                                      <div>
                                        <span className="health-label">Latest month</span>
                                        <strong>{selectedAnomalyRecord.latestMonth}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">History months</span>
                                        <strong>{selectedAnomalyRecord.historyMonths}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Latest actual</span>
                                        <strong>{formatMetric(selectedAnomalyRecord.latestActual)} pcs</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Recent 3M avg</span>
                                        <strong>{formatMetric(selectedAnomalyRecord.recent3MonthAverage)} pcs</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">MoM change</span>
                                        <strong>{selectedAnomalyRecord.deltaPct !== null ? `${selectedAnomalyRecord.deltaPct >= 0 ? "+" : ""}${selectedAnomalyRecord.deltaPct.toFixed(1)}%` : "N/A"}</strong>
                                      </div>
                                      <div>
                                        <span className="health-label">Backtest WAPE</span>
                                        <strong>{selectedAnomalyRecord.wape !== null ? `${(selectedAnomalyRecord.wape * 100).toFixed(1)}%` : "N/A"}</strong>
                                      </div>
                                      <div style={{ gridColumn: "span 2" }}>
                                        <span className="health-label">Next baseline forecast</span>
                                        <strong>
                                          {formatMetric(selectedAnomalyRecord.nextForecast)} pcs
                                          {selectedAnomalyRecord.forecastDeltaPct !== null ? ` (${selectedAnomalyRecord.forecastDeltaPct >= 0 ? "+" : ""}${selectedAnomalyRecord.forecastDeltaPct.toFixed(1)}%)` : ""}
                                        </strong>
                                      </div>
                                    </div>
                                  </Col>
                                  <Col xs={24} xl={8}>
                                    <Card variant="borderless" style={{ background: "rgba(248, 250, 255, 0.82)", height: "100%" }}>
                                      <div style={{ fontWeight: 700, marginBottom: 10 }}>Evidence trail</div>
                                      <div className="summary-stack">
                                        {selectedAnomalyRecord.evidence.map((line) => (
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
                                      <Card variant="borderless" style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Wholesale-linked model</div>
                                        {selectedAnomalyRecord.wholesaleSignal ? (
                                          <div className="health-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                                            <div>
                                              <span className="health-label">Link strength</span>
                                              <strong>{selectedAnomalyRecord.wholesaleSignal.relationshipStrength}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Model WAPE</span>
                                              <strong>{selectedAnomalyRecord.wholesaleSignal.modelWape !== null ? `${(selectedAnomalyRecord.wholesaleSignal.modelWape * 100).toFixed(1)}%` : "N/A"}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Wholesale delta</span>
                                              <strong>{selectedAnomalyRecord.wholesaleSignal.wholesaleDeltaPct !== null ? `${selectedAnomalyRecord.wholesaleSignal.wholesaleDeltaPct >= 0 ? "+" : ""}${selectedAnomalyRecord.wholesaleSignal.wholesaleDeltaPct.toFixed(1)}%` : "N/A"}</strong>
                                            </div>
                                            <div>
                                              <span className="health-label">Expected by model</span>
                                              <strong>{formatMetric(selectedAnomalyRecord.wholesaleSignal.expectedFromModel)} pcs</strong>
                                            </div>
                                            <div style={{ gridColumn: "span 2" }}>
                                              <span className="health-label">Unexplained residual</span>
                                              <strong>
                                                {selectedAnomalyRecord.wholesaleSignal.unexplainedResidualPct !== null
                                                  ? `${selectedAnomalyRecord.wholesaleSignal.unexplainedResidualPct >= 0 ? "+" : ""}${selectedAnomalyRecord.wholesaleSignal.unexplainedResidualPct.toFixed(1)}%`
                                                  : "N/A"}
                                              </strong>
                                            </div>
                                          </div>
                                        ) : (
                                          <Text type="secondary">No wholesale-linked model could be fit for this part with the current workbook structure.</Text>
                                        )}
                                      </Card>
                                      <Card variant="borderless" style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Brand drivers</div>
                                        {selectedAnomalyRecord.brandDrivers.length ? (
                                          <div className="summary-stack">
                                            {selectedAnomalyRecord.brandDrivers.map((item) => (
                                              <div key={`${selectedAnomalyRecord.part}-brand-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
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
                                      <Card variant="borderless" style={{ background: "rgba(248, 250, 255, 0.82)" }}>
                                        <div style={{ fontWeight: 700, marginBottom: 10 }}>Model drivers</div>
                                        {selectedAnomalyRecord.modelDrivers.length ? (
                                          <div className="summary-stack">
                                            {selectedAnomalyRecord.modelDrivers.map((item) => (
                                              <div key={`${selectedAnomalyRecord.part}-model-${item.name}`} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
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
                            ) : null}
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
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Forecast Center</strong>
                    <small>Output</small>
                  </span>
                ),
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div className="tab-stack">
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                          <div>
                            <div className="eyebrow" style={{ marginBottom: 8 }}>Part-Month Baseline Forecast</div>
                            <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                              {forecastView === "hierarchy"
                                ? "Forecast Center always uses the governed PIO_Sales_Data source. Anchor, model, and date filters are separate from the active Data Workspace sheet."
                                : "Choose a time range, business slice, and focus part directly in Forecast Center. The result includes chart output, forecast table, and downloadable Excel."}
                            </Paragraph>
                          </div>
                          <Space wrap>
                            <Select
                              style={{ width: 180 }}
                              value={forecastView}
                              options={[
                                { label: "Forecast Center", value: "hierarchy" },
                                { label: "Output", value: "output" },
                                { label: "Detail", value: "detail" },
                                { label: "Leaderboard", value: "leaderboard" },
                                { label: "Series Table", value: "series" },
                                { label: "Interpretation", value: "interpretation" },
                                { label: "Signals", value: "signals" },
                              ]}
                              onChange={(value) => {
                                setForecastView(value);
                                if (value === "hierarchy" && workspace) {
                                  const hierarchyState = {
                                    ...forecastFilterState,
                                    search: "",
                                    brand: forecastFilterState.brand.filter((brand) =>
                                      ["HMA", "GMA", "KUS"].includes(brand)
                                    ),
                                    modelYear: [],
                                    part: [],
                                  };
                                  setForecastFilterState(hierarchyState);
                                  loadHierarchicalForecast(workspace.sheetName, hierarchyState);
                                } else if (workspace) {
                                  const partState = {
                                    ...forecastFilterState,
                                    brand: forecastFilterState.brand.filter((brand) =>
                                      !["HMA", "GMA", "KUS"].includes(brand)
                                    ),
                                  };
                                  setForecastFilterState(partState);
                                  loadForecastData(
                                    workspace.sheetName,
                                    partState,
                                    forecastPart,
                                    forecastHorizon,
                                  );
                                }
                              }}
                            />
                            <Button onClick={syncForecastFromTable}>
                              {forecastView === "hierarchy" ? "Use compatible Data Table filters" : "Use Data Table filters"}
                            </Button>
                            <Button onClick={resetForecastFilters}>Reset Forecast filters</Button>
                          </Space>
                        </div>
                        <div className="toolbar-grid">
                          {forecastView !== "hierarchy" ? (
                            <Input
                              allowClear
                              prefix={<SearchOutlined />}
                              placeholder="Search in the current forecast slice"
                              value={forecastFilterState.search}
                              onChange={(event) => {
                                const value = event.target.value;
                                setForecastFilterState({ ...forecastFilterState, search: value });
                                if (!value) {
                                  applyForecastFilters({ search: "" });
                                }
                              }}
                              onPressEnter={() => applyForecastFilters({ search: forecastFilterState.search })}
                            />
                          ) : null}
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Brand"
                            optionFilterProp="label"
                            popupMatchSelectWidth={false}
                            value={forecastFilterState.brand}
                            options={forecastView === "hierarchy"
                              ? [
                                  { label: "HMA · Hyundai Motor America", value: "HMA" },
                                  { label: "GMA · Genesis Motor America", value: "GMA" },
                                  { label: "KUS · Kia US", value: "KUS" },
                                ]
                              : (governedForecastFilterOptions?.brand.map((option) => ({
                                  label: `${option.label} (${option.count.toLocaleString()})`,
                                  value: option.value,
                                })) ?? [])}
                            onChange={(value) => applyForecastFilters({ brand: value })}
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            maxTagCount="responsive"
                            placeholder="Model"
                            optionFilterProp="label"
                            showSearch
                            popupMatchSelectWidth={false}
                            value={forecastFilterState.model}
                            options={(governedForecastFilterOptions?.model ?? []).map((option) => ({
                              label: `${option.label} (${option.count.toLocaleString()})`,
                              value: option.value,
                            }))}
                            onChange={(value) => applyForecastFilters({ model: value })}
                          />
                          {forecastView !== "hierarchy" ? (
                            <Select
                              mode="multiple"
                              allowClear
                              maxTagCount="responsive"
                              placeholder="Model year"
                              optionFilterProp="label"
                              popupMatchSelectWidth={false}
                              value={forecastFilterState.modelYear}
                              options={(governedForecastFilterOptions?.modelYear ?? []).map((option) => ({
                                label: `${option.label} (${option.count.toLocaleString()})`,
                                value: option.value,
                              }))}
                              onChange={(value) => applyForecastFilters({ modelYear: value })}
                            />
                          ) : null}
                          <RangePicker
                            value={
                              forecastFilterState.startDate && forecastFilterState.endDate
                                ? [dayjs(forecastFilterState.startDate), dayjs(forecastFilterState.endDate)]
                                : null
                            }
                            onChange={(value) =>
                              applyForecastFilters({
                                startDate: value?.[0]?.format("YYYY-MM-DD") ?? "",
                                endDate: value?.[1]?.format("YYYY-MM-DD") ?? "",
                              })
                            }
                          />
                          {forecastView !== "hierarchy" ? (
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
                                loadForecastData(workspace.sheetName, forecastFilterState, value, forecastHorizon);
                              }}
                            />
                          ) : null}
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
                              if (forecastView === "hierarchy") {
                                loadHierarchicalForecast(
                                  workspace.sheetName,
                                  forecastFilterState,
                                  hierarchyLevel,
                                  forecastMetric,
                                  value,
                                );
                              } else {
                                loadForecastData(workspace.sheetName, forecastFilterState, forecastPart, value);
                              }
                            }}
                          />
                        </div>
                      </div>
                    </Card>

                    {forecastView === "hierarchy" ? (
                      renderForecastCenterPanel()
                    ) : forecastLoading ? (
                      <div className="loading-shell" style={{ minHeight: "40vh" }}>
                        <div className="loading-card">
                          <Spin size="large" />
                          <p className="loading-msg">Building part-level forecast…</p>
                        </div>
                      </div>
                    ) : forecastData ? (
                      <>
                        {forecastView !== "hierarchy" ? (
                          <Row gutter={[18, 18]}>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Scanned parts" value={forecastData.portfolio.summary.scannedParts} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Planner-ready" value={forecastData.portfolio.summary.plannerReadyCount} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Needs review" value={forecastData.portfolio.summary.reviewCount} />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Do not auto-plan" value={forecastData.portfolio.summary.doNotAutoPlanCount} />
                            </Card>
                          </Col>
                          </Row>
                        ) : null}

                        {forecastView === "output" ? (
                          <div className="tab-stack">
                            <Card
                              className="content-card"
                              title="Standardized forecast output"
                              extra={(
                                <Space wrap>
                                  <Button icon={<DownloadOutlined />} onClick={exportForecastCenterCsv}>Current view CSV</Button>
                                  <Button type="primary" icon={<DownloadOutlined />} onClick={exportForecastCenterXlsx}>Download SOP Excel</Button>
                                </Space>
                              )}
                            >
                              <Alert
                                type="info"
                                showIcon
                                message={`The workbook will cover ${forecastHorizon} forecast month${forecastHorizon === 1 ? "" : "s"}.`}
                                description="The current partial month is labeled Nowcast; subsequent months are labeled Forecast. Brand is the official anchor and every lower-level revenue and quantity table includes reconciliation checks."
                              />
                              <div className="health-grid" style={{ marginTop: 16, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                                <div><span className="health-label">Executive Summary</span><strong>Period, totals, Top 10 PLC</strong></div>
                                <div><span className="health-label">Revenue Forecast</span><strong>Brand → Model → PLC</strong></div>
                                <div><span className="health-label">Quantity Forecast</span><strong>PIO quantity hierarchy</strong></div>
                                <div><span className="health-label">Part Planning</span><strong>PIS_PNO allocation detail</strong></div>
                                <div><span className="health-label">Wholesale Drivers</span><strong>Brand and model quantity</strong></div>
                                <div><span className="health-label">QA & Assumptions</span><strong>Formulas and reconciliation</strong></div>
                              </div>
                            </Card>
                          </div>
                        ) : null}

                        {forecastView === "legacy_hierarchy" ? (
                          <Spin spinning={hierarchicalForecastLoading}>
                            <div className="tab-stack">
                              <Card className="content-card" title="Hierarchical forecast controls">
                                <div className="toolbar-grid">
                                  <Select
                                    value={hierarchyLevel}
                                    options={[
                                      { label: "Brand", value: "brand" },
                                      { label: "Model", value: "model" },
                                      { label: "Model × PLC", value: "model_plc" },
                                    ]}
                                    onChange={setHierarchyLevel}
                                  />
                                  {hierarchyLevel !== "model_plc" ? (
                                    <Select
                                      value={hierarchyModelStrategy}
                                      onChange={setHierarchyModelStrategy}
                                      options={[
                                        { label: "Auto: baselines + drivers", value: "auto" },
                                        { label: "Auto: statistical baselines only", value: "baseline_auto" },
                                        { label: "Driver regression (OLS)", value: "driver_adjusted_regression" },
                                        { label: "Naive last", value: "naive_last" },
                                        { label: "Mean", value: "mean" },
                                        { label: "Weighted moving average", value: "weighted_moving_average" },
                                        { label: "Trailing 12-month mean", value: "trailing_12_mean" },
                                        { label: "Trend-adjusted moving average", value: "trend_adjusted_moving_average" },
                                        { label: "Damped trend", value: "damped_trend" },
                                        { label: "Log-linear trend", value: "log_linear_trend" },
                                        { label: "Seasonal naive", value: "seasonal_naive" },
                                        { label: "Seasonal mean", value: "seasonal_mean" },
                                        { label: "Croston SBA", value: "croston_sba" },
                                        { label: "LightGBM (future ML)", value: "lightgbm", disabled: true },
                                        { label: "XGBoost (future ML)", value: "xgboost", disabled: true },
                                      ]}
                                    />
                                  ) : null}
                                  <Select
                                    value={useWorkingDays}
                                    options={[{ label: "Working Days on", value: true }, { label: "Working Days off", value: false }]}
                                    onChange={setUseWorkingDays}
                                  />
                                  <Select
                                    value={useSeasonality}
                                    options={[{ label: "Seasonality on", value: true }, { label: "Seasonality off", value: false }]}
                                    onChange={setUseSeasonality}
                                  />
                                  <Space.Compact block>
                                    <InputNumber
                                      min={-100}
                                      max={100}
                                      value={tariffImpactPct}
                                      onChange={(value) => setTariffImpactPct(Number(value ?? 0))}
                                      style={{ width: "100%" }}
                                    />
                                    <Input value="% tariff demand impact" readOnly style={{ width: 180 }} />
                                  </Space.Compact>
                                  <Space.Compact block>
                                    <InputNumber
                                      min={0}
                                      value={minimumMonthlyVolume}
                                      onChange={(value) => setMinimumMonthlyVolume(Number(value ?? 0))}
                                      style={{ width: "100%" }}
                                    />
                                    <Input value="min avg qty/month" readOnly style={{ width: 165 }} />
                                  </Space.Compact>
                                  <Button
                                    type="primary"
                                    onClick={() => workspace && loadHierarchicalForecast(workspace.sheetName, forecastFilterState, hierarchyLevel)}
                                  >
                                    Run hierarchy forecast
                                  </Button>
                                </div>
                                {hierarchyLevel === "model_plc" ? (
                                  <Alert
                                    style={{ marginTop: 12 }}
                                    type="info"
                                    showIcon
                                    message="Model × accessory uses automatic per-series model selection"
                                    description={(
                                      <ol style={{ margin: "8px 0 0", paddingLeft: 20 }}>
                                        <li>Build one monthly series for every brand × model entity × accessory combination.</li>
                                        <li>Exclude series below the minimum average quantity or with fewer than six active months.</li>
                                        <li>For each remaining series, compare its eligible baseline and driver models using inner rolling validation.</li>
                                        <li>Select that series&apos; lowest-WAPE model, then score it on untouched final test months.</li>
                                        <li>Apply lifecycle rules and the optional tariff scenario only after the model forecast is produced.</li>
                                      </ol>
                                    )}
                                  />
                                ) : null}
                                <Paragraph className="workspace-copy" style={{ marginTop: 12, marginBottom: 0 }}>
                                  Tariff is an explicit demand scenario applied after model selection; it is not presented as a learned historical effect.
                                  Low-volume series below the selected monthly average or with fewer than six active months are excluded.
                                </Paragraph>
                              </Card>
                              <Card className="content-card" title="How this forecast is calculated" size="small">
                                <div className="health-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
                                  <div><span className="health-label">Working Days</span><strong>OLS-learned coefficient; no fixed weight</strong><Text type="secondary">Feature: (days - mean days) / mean days. It matters only when driver regression is selected.</Text></div>
                                  <div><span className="health-label">Seasonality</span><strong>OLS sin/cos coefficients + model eligibility</strong><Text type="secondary">Adds annual sin/cos features and allows seasonal naive/mean candidates.</Text></div>
                                  <div><span className="health-label">Tariff</span><strong>Scenario multiplier, not learned</strong><Text type="secondary">Final = model forecast × max(0, 1 + tariff% / 100).</Text></div>
                                  <div><span className="health-label">Minimum volume</span><strong>Eligibility filter, not a weight</strong><Text type="secondary">Average monthly quantity must meet the threshold and the series needs at least six active months.</Text></div>
                                </div>
                                <pre style={{ whiteSpace: "pre-wrap", margin: "16px 0 0", padding: 14, borderRadius: 10, background: "#f6f8fb", fontSize: 12 }}>{`group monthly quantity at the selected hierarchy grain
select model on inner rolling validation
evaluate on untouched final 3-6 months
if driver regression:
  y_hat = beta0 + betaTrend*t + betaWD*x_wd + betaSin*sin(month) + betaCos*cos(month)
final_forecast = max(0, y_hat * max(0, 1 + tariff_pct/100))`}</pre>
                              </Card>
                              {hierarchicalForecast ? (
                                <>
                                  <Row gutter={[18, 18]}>
                                    <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Backtest accuracy" value={hierarchicalForecast.summary.accuracyPct ?? "N/A"} suffix={hierarchicalForecast.summary.accuracyPct === null ? "" : "%"} /></Card></Col>
                                    <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Weighted WAPE" value={hierarchicalForecast.summary.weightedWape === null ? "N/A" : (hierarchicalForecast.summary.weightedWape * 100).toFixed(1)} suffix={hierarchicalForecast.summary.weightedWape === null ? "" : "%"} /></Card></Col>
                                    <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Forecasted series" value={hierarchicalForecast.summary.seriesCount} /></Card></Col>
                                    <Col xs={12} md={6}><Card className="metric-card"><Statistic title="Low-volume excluded" value={hierarchicalForecast.summary.excludedLowVolumeSeries} /></Card></Col>
                                  </Row>
                                  <Alert
                                    type={hierarchicalForecast.summary.latestMonthExcluded ? "warning" : "info"}
                                    showIcon
                                    message={hierarchicalForecast.summary.accuracyDefinition}
                                    description={`Latest complete month: ${hierarchicalForecast.summary.latestCompleteMonth ?? "N/A"}. ${hierarchicalForecast.summary.latestMonthExcluded ? `Observed ${hierarchicalForecast.summary.latestObservedMonth} was excluded because its volume was only ${((hierarchicalForecast.summary.latestMonthCompletenessRatio ?? 0) * 100).toFixed(1)}% of the recent 3-month median, below the ${(hierarchicalForecast.summary.latestMonthCompletenessThreshold * 100).toFixed(0)}% completeness threshold. ` : ""}Models: ${Object.entries(hierarchicalForecast.summary.modelCounts).map(([name, count]) => `${name} (${count})`).join(", ") || "none"}.`}
                                  />
                                  <Card className="content-card" title="Forecast results">
                                    <Table
                                      size="small"
                                      rowKey="seriesKey"
                                      pagination={{ pageSize: 20, hideOnSinglePage: true }}
                                      dataSource={hierarchicalForecast.records}
                                      columns={[
                                        { title: "Brand", dataIndex: "brand", key: "brand" },
                                        { title: "Model", dataIndex: "modelName", key: "modelName", render: (value: string) => value || "All models" },
                                        { title: "Accessory", dataIndex: "partNumber", key: "partNumber", render: (value: string) => value || "All accessories" },
                                        { title: "Lifecycle", dataIndex: "lifecycleStatus", key: "lifecycleStatus" },
                                        { title: "Selected model", dataIndex: "selectedModel", key: "selectedModel" },
                                        { title: "Independent test model", dataIndex: "backtestModel", key: "backtestModel" },
                                        { title: "Selection reason", dataIndex: "selectionNote", key: "selectionNote", width: 280 },
                                        { title: "Learned weights", dataIndex: "learnedCoefficients", key: "learnedCoefficients", width: 300, render: (values: Record<string, number>) => Object.keys(values).length ? Object.entries(values).map(([name, value]) => `${name}=${value.toFixed(3)}`).join(" | ") : "Not used by this model" },
                                        { title: "History avg", dataIndex: "monthlyAverage", key: "monthlyAverage", align: "right" as const, render: (value: number) => formatMetric(value) },
                                        { title: "Next forecast", dataIndex: "nextForecast", key: "nextForecast", align: "right" as const, render: (value: number) => formatMetric(value) },
                                        { title: "WAPE", dataIndex: "wape", key: "wape", align: "right" as const, render: (value: number | null) => value === null ? "N/A" : `${(value * 100).toFixed(1)}%` },
                                        { title: "Accuracy", dataIndex: "accuracyPct", key: "accuracyPct", align: "right" as const, render: (value: number | null) => value === null ? "N/A" : `${value.toFixed(1)}%` },
                                        { title: "Forecast months", dataIndex: "forecast", key: "forecast", render: (values: Array<{ month: string; value: number }>) => values.map((item) => `${item.month}: ${formatMetric(item.value)}`).join(" | ") },
                                      ]}
                                      scroll={{ x: 1500 }}
                                    />
                                  </Card>
                                </>
                              ) : (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run a hierarchical forecast to calculate rolling-backtest accuracy." />
                              )}
                            </div>
                          </Spin>
                        ) : null}

                        {forecastView === "leaderboard" ? (
                          <Card
                            className="content-card"
                            title="Forecast reliability leaderboard"
                            extra={
                              <Space size={8} wrap>
                                <Tag color="geekblue">
                                  Planner-ready volume share {(forecastData.portfolio.summary.plannerReadyShare * 100).toFixed(1)}%
                                </Tag>
                                {forecastData.portfolio.recommendedPart ? (
                                  <Tag color="blue">Recommended focus: {forecastData.portfolio.recommendedPart}</Tag>
                                ) : null}
                              </Space>
                            }
                          >
                            <div className="summary-stack">
                              {forecastData.portfolio.records.map((item) => (
                                <div
                                  key={`portfolio-${item.part}`}
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    gap: 16,
                                    padding: "10px 0",
                                    borderBottom: "1px solid #f0f4f9",
                                    alignItems: "flex-start",
                                  }}
                                >
                                  <div style={{ minWidth: 0 }}>
                                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 4 }}>
                                      <Text strong>{item.part}</Text>
                                      <Tag color={item.reliabilityCode === "planner_ready" ? "green" : item.reliabilityCode === "needs_review" ? "gold" : "red"}>
                                        {item.reliabilityTier}
                                      </Tag>
                                      <Tag>{item.regime}</Tag>
                                      <Tag color={item.forecastRisk === "High" ? "red" : item.forecastRisk === "Medium" ? "gold" : "green"}>
                                        {item.forecastRisk} risk
                                      </Tag>
                                    </div>
                                    <div style={{ color: "#607087", fontSize: 12, marginBottom: 6 }}>
                                      {item.partDescription || "No part description"} · {item.historyMonths} months · model {item.modelName.replaceAll("_", " ")}
                                    </div>
                                    <div style={{ color: "#334155", fontSize: 13 }}>
                                      {item.reliabilityReason}
                                    </div>
                                  </div>
                                  <div style={{ minWidth: 220, textAlign: "right" }}>
                                    <div style={{ fontWeight: 700, marginBottom: 4 }}>Score {item.reliabilityScore.toFixed(1)}</div>
                                    <div style={{ color: "#607087", fontSize: 12, marginBottom: 8 }}>
                                      WAPE {item.wape !== null ? `${(item.wape * 100).toFixed(1)}%` : "N/A"} · Bias {item.bias !== null ? `${(item.bias * 100).toFixed(1)}%` : "N/A"}
                                    </div>
                                    <div style={{ color: "#607087", fontSize: 12, marginBottom: 8 }}>
                                      Latest {formatMetric(item.latestActual)} pcs {"->"} Forecast {formatMetric(item.nextForecast)} pcs
                                    </div>
                                    <Button
                                      size="small"
                                      onClick={() => loadForecastData(workspace.sheetName, forecastFilterState, item.part, forecastHorizon)}
                                    >
                                      Inspect this part
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </Card>
                        ) : null}

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

                        {forecastView === "detail" ? (
                          <Row gutter={[18, 18]}>
                            <Col xs={24} xl={16}>
                              <Card
                                className="chart-card"
                                title={`${forecastData.selectedPart}${forecastData.partDescription ? ` · ${forecastData.partDescription}` : ""}`}
                                extra={
                                  <Space size={8} wrap>
                                    <Tag color={forecastData.summary.forecastRisk === "High" ? "red" : forecastData.summary.forecastRisk === "Medium" ? "gold" : "green"}>
                                      {forecastData.summary.forecastRisk} risk
                                    </Tag>
                                    <Tag color={forecastData.summary.confidence === "High" ? "blue" : forecastData.summary.confidence === "Medium" ? "gold" : "default"}>
                                      {forecastData.summary.confidence} confidence
                                    </Tag>
                                  </Space>
                                }
                              >
                                {forecastData.summary.forecastRisk === "High" ? (
                                  <Alert
                                    type="warning"
                                    showIcon
                                    style={{ marginBottom: 16 }}
                                    message={`This part currently looks ${forecastData.summary.regime.toLowerCase()} and the forecast should be treated as a short-horizon baseline.`}
                                  />
                                ) : null}
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
                                    <span className="health-label">Series regime</span>
                                    <strong>{forecastData.summary.regime}</strong>
                                  </div>
                                  <div>
                                    <span className="health-label">Forecast risk</span>
                                    <strong>{forecastData.summary.forecastRisk}</strong>
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
                        ) : null}

                        {forecastView === "series" ? (
                          <Card className="content-card" title="Forecast series table">
                            <Table
                              size="small"
                              pagination={false}
                              rowKey={(record) => `${record.month}-${record.actual ?? "na"}-${record.forecast ?? "na"}`}
                              scroll={{ x: "max-content" }}
                              columns={[
                                {
                                  title: "Month",
                                  dataIndex: "month",
                                  key: "month",
                                  width: 120,
                                },
                                {
                                  title: "Actual",
                                  dataIndex: "actual",
                                  key: "actual",
                                  width: 140,
                                  align: "right",
                                  render: (value: number | null) => (value === null ? "—" : formatMetric(value)),
                                },
                                {
                                  title: "Forecast",
                                  dataIndex: "forecast",
                                  key: "forecast",
                                  width: 140,
                                  align: "right",
                                  render: (value: number | null) => (value === null ? "—" : formatMetric(value)),
                                },
                                {
                                  title: "Lower bound",
                                  dataIndex: "lower",
                                  key: "lower",
                                  width: 140,
                                  align: "right",
                                  render: (value: number | null) => (value === null ? "—" : formatMetric(value)),
                                },
                                {
                                  title: "Upper bound",
                                  dataIndex: "upper",
                                  key: "upper",
                                  width: 140,
                                  align: "right",
                                  render: (value: number | null) => (value === null ? "—" : formatMetric(value)),
                                },
                              ]}
                              dataSource={forecastData.series}
                            />
                          </Card>
                        ) : null}

                        {forecastView === "interpretation" ? (
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
                        ) : null}

                        {forecastView === "signals" ? (
                          <>
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
                        ) : null}
                      </>
                    ) : (
                      <Card className="content-card">
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Forecast data is not available for this worksheet yet." />
                      </Card>
                    )}
                  </div>
                ),
              },
              {
                key: "inventory",
                label: (
                  <span className="workspace-subtab-label">
                    <strong>Inventory Simulator</strong>
                    <small>Planning</small>
                  </span>
                ),
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div className="major-tab-header">
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Inventory Simulator</div>
                          <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                            Convert the selected part forecast into reorder point, safety stock, and recommended purchase quantity. Inventory values are planner inputs until a stock file is connected.
                          </Paragraph>
                        </div>
                        <Space wrap>
                          {forecastData?.selectedPart ? <Tag color="blue" icon={<CalculatorOutlined />}>Planning part: {forecastData.selectedPart}</Tag> : null}
                          <Button icon={<DownloadOutlined />} onClick={exportInventoryCsv} disabled={!inventoryPlanRows.length}>
                            Export Plan CSV
                          </Button>
                        </Space>
                      </div>
                    </Card>

                    {forecastLoading ? (
                      <div className="loading-shell" style={{ minHeight: "40vh" }}>
                        <div className="loading-card">
                          <Spin size="large" />
                          <p className="loading-msg">Preparing inventory planning inputs…</p>
                        </div>
                      </div>
                    ) : forecastData && selectedInventoryPlan ? (
                      <>
                        <Row gutter={[18, 18]}>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Recommended order" value={formatMetric(selectedInventoryPlan.suggestedOrder ?? 0)} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Reorder point" value={formatMetric(Math.round(selectedInventoryPlan.reorderPoint))} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic title="Safety stock" value={formatMetric(Math.round(selectedInventoryPlan.safetyStock))} suffix="pcs" />
                            </Card>
                          </Col>
                          <Col xs={24} md={12} xl={6}>
                            <Card className="metric-card">
                              <Statistic
                                title="Coverage"
                                value={selectedInventoryPlan.coverageMonths === null ? "N/A" : selectedInventoryPlan.coverageMonths.toFixed(1)}
                                suffix={selectedInventoryPlan.coverageMonths === null ? "" : "months"}
                              />
                            </Card>
                          </Col>
                        </Row>

                        <Row gutter={[18, 18]}>
                          <Col xs={24} xl={9}>
                            <Card className="content-card" title="Planning assumptions" style={{ height: "100%" }}>
                              <div className="inventory-control-grid">
                                <label>
                                  <span>Current inventory</span>
                                  <Space.Compact block>
                                    <InputNumber min={0} value={inventoryCurrentStock} onChange={(value) => setInventoryCurrentStock(Number(value ?? 0))} style={{ width: "100%" }} />
                                    <Input value="pcs" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                                <label>
                                  <span>Open purchase / in transit</span>
                                  <Space.Compact block>
                                    <InputNumber min={0} value={inventoryOnOrder} onChange={(value) => setInventoryOnOrder(Number(value ?? 0))} style={{ width: "100%" }} />
                                    <Input value="pcs" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                                <label>
                                  <span>Lead time</span>
                                  <Space.Compact block>
                                    <InputNumber min={0} value={inventoryLeadTimeDays} onChange={(value) => setInventoryLeadTimeDays(Number(value ?? 0))} style={{ width: "100%" }} />
                                    <Input value="days" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                                <label>
                                  <span>Review period</span>
                                  <Space.Compact block>
                                    <InputNumber min={1} value={inventoryReviewDays} onChange={(value) => setInventoryReviewDays(Number(value ?? 1))} style={{ width: "100%" }} />
                                    <Input value="days" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                                <label>
                                  <span>Service level</span>
                                  <Select
                                    value={inventoryServiceLevel}
                                    onChange={setInventoryServiceLevel}
                                    options={[
                                      { label: "90%", value: 90 },
                                      { label: "95%", value: 95 },
                                      { label: "98%", value: 98 },
                                      { label: "99%", value: 99 },
                                    ]}
                                  />
                                </label>
                                <label>
                                  <span>Order pack size</span>
                                  <Space.Compact block>
                                    <InputNumber min={1} value={inventoryPackSize} onChange={(value) => setInventoryPackSize(Number(value ?? 1))} style={{ width: "100%" }} />
                                    <Input value="pcs" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                                <label>
                                  <span>Manual buffer</span>
                                  <Space.Compact block>
                                    <InputNumber min={0} max={200} value={inventoryManualBufferPct} onChange={(value) => setInventoryManualBufferPct(Number(value ?? 0))} style={{ width: "100%" }} />
                                    <Input value="%" readOnly style={{ width: 64 }} />
                                  </Space.Compact>
                                </label>
                              </div>
                            </Card>
                          </Col>
                          <Col xs={24} xl={8}>
                            <Card
                              className="content-card inventory-risk-card"
                              title="Planner signal"
                              extra={<Tag color={inventoryRiskColor}>{selectedInventoryPlan.riskLabel}</Tag>}
                              style={{ height: "100%" }}
                            >
                              <div className="inventory-plan-strip">
                                <div>
                                  <span className="health-label">Part</span>
                                  <strong>{selectedInventoryPlan.part}</strong>
                                </div>
                                <div>
                                  <span className="health-label">Monthly forecast</span>
                                  <strong>{formatMetric(Math.round(selectedInventoryPlan.monthlyForecast))} pcs</strong>
                                </div>
                                <div>
                                  <span className="health-label">Lead time demand</span>
                                  <strong>{formatMetric(Math.round(selectedInventoryPlan.leadTimeDemand))} pcs</strong>
                                </div>
                                <div>
                                  <span className="health-label">Target stock</span>
                                  <strong>{formatMetric(Math.round(selectedInventoryPlan.targetStock))} pcs</strong>
                                </div>
                                <div>
                                  <span className="health-label">Forecast risk</span>
                                  <strong>{selectedInventoryPlan.forecastRisk}</strong>
                                </div>
                                <div>
                                  <span className="health-label">WAPE input</span>
                                  <strong>{selectedInventoryPlan.wape === null ? "Risk fallback" : `${(selectedInventoryPlan.wape * 100).toFixed(1)}%`}</strong>
                                </div>
                              </div>
                              {selectedInventoryPlan.riskCode === "stockout" ? (
                                <Alert
                                  type="warning"
                                  showIcon
                                  style={{ marginTop: 16 }}
                                  message="Net available inventory is below the reorder point. This part should be reviewed for purchase timing."
                                />
                              ) : selectedInventoryPlan.riskCode === "overstock" ? (
                                <Alert
                                  type="info"
                                  showIcon
                                  style={{ marginTop: 16 }}
                                  message="Net available inventory is above the target band. Reorder can likely wait unless demand is changing."
                                />
                              ) : (
                                <Alert
                                  type="success"
                                  showIcon
                                  style={{ marginTop: 16 }}
                                  message="Current inputs are inside the planning band for this forecast."
                                />
                              )}
                            </Card>
                          </Col>
                          <Col xs={24} xl={7}>
                            <Card className="chart-card" title="Stock threshold view" style={{ height: "100%" }}>
                              <ReactECharts
                                option={{
                                  tooltip: { trigger: "axis" },
                                  grid: { left: 16, right: 16, top: 28, bottom: 20, containLabel: true },
                                  xAxis: {
                                    type: "category",
                                    data: ["Net available", "Reorder point", "Target stock"],
                                    axisLabel: { color: "#607087" },
                                  },
                                  yAxis: {
                                    type: "value",
                                    axisLabel: { color: "#607087" },
                                    splitLine: { lineStyle: { color: "#edf2f7" } },
                                  },
                                  series: [
                                    {
                                      type: "bar",
                                      barWidth: 34,
                                      data: [
                                        inventoryCurrentStock + inventoryOnOrder,
                                        Math.round(selectedInventoryPlan.reorderPoint),
                                        Math.round(selectedInventoryPlan.targetStock),
                                      ],
                                      itemStyle: {
                                        borderRadius: [8, 8, 0, 0],
                                        color: (params: { dataIndex: number }) =>
                                          params.dataIndex === 0 ? "#2054f4" : params.dataIndex === 1 ? "#f59e0b" : "#12b76a",
                                      },
                                    },
                                  ],
                                }}
                                style={{ height: 300 }}
                              />
                            </Card>
                          </Col>
                        </Row>

                        <Card
                          className="content-card"
                          title="Planning table"
                          extra={<Tag>{inventoryPlanRows.length} parts in current forecast slice</Tag>}
                        >
                          <Paragraph className="workspace-copy inventory-table-note">
                            Suggested order is calculated only for the selected part because current inventory is entered at part level. Other rows show target stock reference from forecast demand and uncertainty.
                          </Paragraph>
                          <Table
                            size="small"
                            rowKey="key"
                            pagination={{ pageSize: 10, showSizeChanger: true }}
                            scroll={{ x: "max-content" }}
                            columns={[
                              {
                                title: "Part",
                                dataIndex: "part",
                                key: "part",
                                width: 170,
                                fixed: "left",
                                render: (value: string, record: InventoryPlanRow) => (
                                  <div>
                                    <Text strong>{value}</Text>
                                    {record.part === forecastData.selectedPart ? <Tag color="blue" style={{ marginLeft: 6 }}>selected</Tag> : null}
                                  </div>
                                ),
                              },
                              {
                                title: "Description",
                                dataIndex: "partDescription",
                                key: "partDescription",
                                width: 260,
                                render: (value: string | null) => value || "—",
                              },
                              {
                                title: "Monthly forecast",
                                dataIndex: "monthlyForecast",
                                key: "monthlyForecast",
                                align: "right",
                                width: 150,
                                render: (value: number) => formatMetric(Math.round(value)),
                              },
                              {
                                title: "Safety stock",
                                dataIndex: "safetyStock",
                                key: "safetyStock",
                                align: "right",
                                width: 140,
                                render: (value: number) => formatMetric(Math.round(value)),
                              },
                              {
                                title: "Reorder point",
                                dataIndex: "reorderPoint",
                                key: "reorderPoint",
                                align: "right",
                                width: 150,
                                render: (value: number) => formatMetric(Math.round(value)),
                              },
                              {
                                title: "Target stock",
                                dataIndex: "targetStock",
                                key: "targetStock",
                                align: "right",
                                width: 140,
                                render: (value: number) => formatMetric(Math.round(value)),
                              },
                              {
                                title: "Suggested order",
                                dataIndex: "suggestedOrder",
                                key: "suggestedOrder",
                                align: "right",
                                width: 150,
                                render: (value: number | null) => (value === null ? "—" : <strong>{formatMetric(value)}</strong>),
                              },
                              {
                                title: "Risk",
                                dataIndex: "riskLabel",
                                key: "riskLabel",
                                width: 180,
                                render: (value: string, record: InventoryPlanRow) => (
                                  <Tag color={record.riskCode === "stockout" ? "red" : record.riskCode === "overstock" ? "gold" : record.riskCode === "balanced" ? "green" : "default"}>
                                    {value}
                                  </Tag>
                                ),
                              },
                              {
                                title: "Forecast WAPE",
                                dataIndex: "wape",
                                key: "wape",
                                align: "right",
                                width: 130,
                                render: (value: number | null) => (value === null ? "N/A" : `${(value * 100).toFixed(1)}%`),
                              },
                              {
                                title: "Forecast risk",
                                dataIndex: "forecastRisk",
                                key: "forecastRisk",
                                width: 130,
                                render: (value: string) => (
                                  <Tag color={value === "High" ? "red" : value === "Medium" ? "gold" : "green"}>{value}</Tag>
                                ),
                              },
                            ]}
                            dataSource={inventoryPlanRows}
                          />
                        </Card>
                      </>
                    ) : (
                      <Card className="content-card">
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run Forecast Center first, then open Inventory Simulator." />
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
                label: (
                  <div className="major-tab-label">
                    <span className="major-tab-icon">
                      <PartitionOutlined />
                    </span>
                    <span className="major-tab-copy">
                      <strong>AI Analyst</strong>
                      <small>Reason over trusted planning signals</small>
                    </span>
                  </div>
                ),
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
                        <Space wrap className="major-tab-actions">
                          <Tag color="blue">Agent-ready foundation</Tag>
                          <Button onClick={exportCsv}>Export CSV</Button>
                          <Button type="primary" onClick={exportXlsx}>
                            Export Excel
                          </Button>
                        </Space>
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
                        <Card className="content-card" title="Ask The Analyst" style={{ height: "100%" }}>
                          <div className="summary-stack">
                            <Select
                              value={aiFocusPart || undefined}
                              placeholder="Optional: focus on a specific part"
                              options={(forecastData?.partOptions ?? []).map((option) => ({
                                label: option.label,
                                value: option.value,
                              }))}
                              onChange={(value) => setAiFocusPart(value)}
                              allowClear
                              showSearch
                              optionFilterProp="label"
                            />
                            <Input.TextArea
                              value={analystQuestion}
                              onChange={(event) => setAnalystQuestion(event.target.value)}
                              placeholder="Ask about anomalies, forecast trust, why a part moved, or what deserves planner review."
                              rows={5}
                            />
                            <Space wrap>
                              <Button type="primary" loading={analystLoading} onClick={() => askAnalyst()}>
                                Run AI Analyst
                              </Button>
                              {topAlert ? (
                                <Button
                                  onClick={() => setAiFocusPart(topAlert.part)}
                                  disabled={analystLoading}
                                >
                                  Use top alert part
                                </Button>
                              ) : null}
                              <Button onClick={() => setAnalystQuestion("")} disabled={analystLoading}>
                                Clear
                              </Button>
                            </Space>
                            <div className="health-label">Suggested prompts</div>
                            <Space wrap size={[8, 8]}>
                              {analystPrompts.map((prompt) => (
                                <Button
                                  key={prompt}
                                  size="small"
                                  onClick={() => {
                                    setAnalystQuestion(prompt);
                                    askAnalyst(prompt);
                                  }}
                                  disabled={analystLoading}
                                >
                                  {prompt}
                                </Button>
                              ))}
                            </Space>
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

                    <Card
                      className="content-card"
                      title="Analyst Answer"
                      extra={
                        analystAnswer ? (
                          <Space size={8} wrap>
                            <Tag color={analystAnswer.riskLevel === "High" ? "red" : analystAnswer.riskLevel === "Medium" ? "gold" : "green"}>
                              {analystAnswer.riskLevel} risk
                            </Tag>
                            <Tag color={analystAnswer.mode === "llm_assisted" ? "blue" : "default"}>
                              {analystAnswer.mode === "llm_assisted" ? "LLM-assisted" : "Grounded tools"}
                            </Tag>
                            {analystAnswer.focusPart ? <Tag>{analystAnswer.focusPart}</Tag> : null}
                          </Space>
                        ) : null
                      }
                    >
                      {analystLoading ? (
                        <div className="loading-shell" style={{ minHeight: 180 }}>
                          <div className="loading-card">
                            <Spin size="large" />
                            <p className="loading-msg">Reviewing the current slice with trusted tools…</p>
                          </div>
                        </div>
                      ) : analystAnswer ? (
                        <div className="summary-stack">
                          <div className="summary-row">
                            <span className="summary-dot" />
                            <span><strong>Question:</strong> {analystAnswer.question}</span>
                          </div>
                          <Card size="small" style={{ background: "#faf7f2", borderColor: "#eadfce" }}>
                            <Paragraph style={{ marginBottom: 0, lineHeight: 1.8 }}>
                              <strong>Conclusion:</strong> {analystAnswer.answer}
                            </Paragraph>
                          </Card>
                          <div className="health-label">Evidence used</div>
                          {analystAnswer.evidence.map((line) => (
                            <div key={line} className="summary-row">
                              <span className="summary-dot" />
                              <span>{line}</span>
                            </div>
                          ))}
                          {analystAnswer.retrievedContext.length ? (
                            <>
                              <div className="health-label">Retrieved context</div>
                              <div className="summary-stack">
                                {analystAnswer.retrievedContext.map((item) => (
                                  <Card
                                    key={`${item.source}-${item.title}-${item.score}`}
                                    size="small"
                                    style={{ borderColor: "#e5ebf3", background: "#fcfdff" }}
                                  >
                                    <Space wrap size={[8, 8]} style={{ marginBottom: 8 }}>
                                      <Tag color="blue">{item.source.replaceAll("_", " ")}</Tag>
                                      <Tag>{item.title}</Tag>
                                      <Tag>{item.score.toFixed(1)}</Tag>
                                    </Space>
                                    <Paragraph style={{ marginBottom: 8, color: "#334155" }}>
                                      {item.content}
                                    </Paragraph>
                                    {item.tags.length ? (
                                      <Space wrap size={[6, 6]}>
                                        {item.tags.map((tag) => (
                                          <Tag key={`${item.title}-${tag}`}>{tag}</Tag>
                                        ))}
                                      </Space>
                                    ) : null}
                                  </Card>
                                ))}
                              </div>
                            </>
                          ) : null}
                          <div className="health-label">Recommended actions</div>
                          {analystAnswer.recommendedActions.map((line) => (
                            <div key={line} className="summary-row">
                              <span className="summary-dot" />
                              <span>{line}</span>
                            </div>
                          ))}
                          <div className="health-label">Good next questions</div>
                          <Space wrap size={[8, 8]}>
                            {analystAnswer.followUpQuestions.map((line) => (
                              <Button
                                key={line}
                                size="small"
                                disabled={analystLoading}
                                onClick={() => {
                                  setAnalystQuestion(line);
                                  askAnalyst(line);
                                }}
                              >
                                {line}
                              </Button>
                            ))}
                          </Space>
                          <div className="health-label">Tool calls</div>
                          <Space wrap size={[8, 8]}>
                            {analystAnswer.usedTools.map((tool) => (
                              <Tag key={tool}>{tool.replaceAll("_", " ")}</Tag>
                            ))}
                            {analystAnswer.model ? <Tag color="blue">{analystAnswer.model}</Tag> : null}
                          </Space>
                          {analystAnswer.warnings.length ? (
                            <Alert
                              type="warning"
                              showIcon
                              message={analystAnswer.warnings.join(" ")}
                            />
                          ) : null}
                        </div>
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Ask a planning question to generate a grounded analyst answer." />
                      )}
                    </Card>

                    <Card
                      className="content-card"
                      title="Recent Analyst Memory"
                      extra={analystMemories.length ? <Tag>{analystMemories.length} saved</Tag> : null}
                    >
                      {analystMemoryLoading ? (
                        <div className="loading-shell" style={{ minHeight: 160 }}>
                          <div className="loading-card">
                            <Spin size="large" />
                            <p className="loading-msg">Loading recent analyst history…</p>
                          </div>
                        </div>
                      ) : analystMemories.length ? (
                        <div className="summary-stack">
                          {analystMemories.map((item) => (
                            <Card key={item.id} size="small" style={{ borderColor: "#e5ebf3", background: "#fbfcfe" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 8 }}>
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{item.question}</div>
                                  <Text type="secondary" style={{ fontSize: 12 }}>
                                    {new Date(item.createdAt).toLocaleString("en-US", {
                                      month: "short",
                                      day: "numeric",
                                      hour: "numeric",
                                      minute: "2-digit",
                                    })}
                                  </Text>
                                </div>
                                <Space size={[6, 6]} wrap style={{ justifyContent: "flex-end" }}>
                                  {item.riskLevel ? (
                                    <Tag color={item.riskLevel === "High" ? "red" : item.riskLevel === "Medium" ? "gold" : "green"}>
                                      {item.riskLevel} risk
                                    </Tag>
                                  ) : null}
                                  {item.focusPart ? <Tag>{item.focusPart}</Tag> : null}
                                </Space>
                              </div>
                              <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 10, color: "#334155" }}>
                                {item.answer}
                              </Paragraph>
                              <Space wrap size={[8, 8]}>
                                <Button
                                  size="small"
                                  onClick={() => {
                                    setAnalystQuestion(item.question);
                                    if (item.focusPart) {
                                      setAiFocusPart(item.focusPart);
                                    }
                                    askAnalyst(item.question);
                                  }}
                                  disabled={analystLoading}
                                >
                                  Ask again
                                </Button>
                                {item.followUpQuestions.slice(0, 2).map((line) => (
                                  <Button
                                    key={`${item.id}-${line}`}
                                    size="small"
                                    disabled={analystLoading}
                                    onClick={() => {
                                      setAnalystQuestion(line);
                                      if (item.focusPart) {
                                        setAiFocusPart(item.focusPart);
                                      }
                                      askAnalyst(line);
                                    }}
                                  >
                                    {line}
                                  </Button>
                                ))}
                              </Space>
                            </Card>
                          ))}
                        </div>
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No analyst memory yet. Ask a question to create the first saved analysis." />
                      )}
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
