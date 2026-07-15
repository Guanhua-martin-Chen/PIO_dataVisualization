import dayjs from "dayjs";

const rawApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "";

export const API_BASE_URL = rawApiBaseUrl
  .replace(/\/api\/?$/, "")
  .replace(/\/$/, "");

export type WorkbookMeta = {
  id: string;
  filename: string;
  sheetNames: string[];
  defaultSheet?: string;
};

export type Kpis = {
  "Total Records": number | null;
  "Total Installation Quantity": number | null;
  "Total Sales Revenue": number | null;
  "Distinct Part Count": number | null;
};

export type LeaderMetric = {
  name: string;
  value: number;
  metric: "Revenue" | "Quantity";
};

export type EdaDashboardPayload = {
  overview: {
    rowCount: number;
    timeRange: { min: string | null; max: string | null };
    modelCount: number;
    modelCodeCount: number;
    partCount: number;
    brandCount: number;
    totalRevenue: number | null;
    totalQuantity: number | null;
  };
  dataQuality: {
    missing: Array<{ field: string; column: string | null; missing: number; missingPct: number }>;
    outliers: {
      negativeRevenueRows: number;
      negativeQuantityRows: number;
      zeroQuantityRows: number;
      unitPriceOutlierRows: number;
      unitPriceP01: number | null;
      unitPriceP99: number | null;
    };
    partDescriptionIssues: Array<{
      partNumber: string;
      issueType: "description_mismatch" | "format_warning";
      descriptionCount: number;
      variantCount: number;
      descriptions: string[];
      rows: number;
    }>;
  };
  monthly: Array<{
    month: string;
    pioRevenue: number;
    pioQuantity: number;
    wholesaleUnits: number | null;
    pnvw: number | null;
  }>;
  rankings: {
    topModels: Array<{ name: string; value: number }>;
    topParts: Array<{ name: string; value: number }>;
    topBrands: Array<{ name: string; value: number }>;
  };
  relationship: {
    revenueWholesaleCorrelation: number | null;
    matchedModelCodes: number;
    salesModelCodes: number;
    wholesaleModelCodes: number;
    modelCodeCoveragePct: number | null;
    matchedModelNames: number;
    salesModelNames: number;
    wholesaleModelNames: number;
    modelNameCoveragePct: number | null;
    ambiguousSalesModelCodes: Array<{ value: string; models: string[] }>;
    ambiguousWholesaleModelCodes: Array<{ value: string; models: string[] }>;
    unmatchedSalesModelCodes: Array<{ value: string; rows: number[] }>;
  };
};

export type WorkspacePayload = {
  workbook: WorkbookMeta;
  sheetName: string;
  roles: Record<string, string>;
  profile: {
    header_row: number;
    header_depth: number;
    row_count: number;
    column_count: number;
  };
  overview: {
    datasetTitle: string;
    sheetName: string;
    kpis: Kpis;
    summary: string[];
    health: {
      dateFieldCount: number;
      numericFieldCount: number;
      categoryFieldCount: number;
      mappedRoleCount: number;
      highMissingFields: string[];
    };
    autoInsights: string[];
    leaders: {
      topBrand?: LeaderMetric;
      topModel?: LeaderMetric;
      topPart?: LeaderMetric;
    };
    stats?: {
      avgUnitPrice?: number;
      avgQtyPerRow?: number;
      avgRevPerRow?: number;
      completenessRate?: number;
    };
  };
  table: {
    columns: Array<{ key: string; title: string; role: string; type: string }>;
    rows: Array<Record<string, string | number | null>>;
    totalRows: number;
    page: number;
    pageSize: number;
    defaultVisibleColumns: string[];
  };
  classification: Record<
    string,
    Array<{
      column: string;
      group: string;
      detectedRole: string;
      confidence: string;
      type: string;
      missingPct: number;
      uniqueCount: number;
      sampleValues: string;
    }>
  >;
  insights: Record<string, { title: string; labels: string[]; values: number[] }>;
  filters: {
    search: string;
    brand: string[];
    model: string[];
    modelYear: string[];
    part: string[];
    modelQuery: string;
    partQuery: string;
    startDate: string;
    endDate: string;
  };
  filterOptions: {
    dateRange: { min: string | null; max: string | null };
    brand: Array<{ label: string; value: string; count: number }>;
    model: Array<{ label: string; value: string; count: number }>;
    modelYear: Array<{ label: string; value: string; count: number }>;
    part: Array<{ label: string; value: string; count: number }>;
  };
  edaDashboard?: EdaDashboardPayload;
};

export type TableState = {
  search: string;
  brand: string[];
  model: string[];
  modelYear: string[];
  part: string[];
  startDate: string;
  endDate: string;
  page: number;
  pageSize: number;
  sortField: string;
  sortOrder: string;
};

export type ForecastPayload = {
  selectedPart: string;
  partDescription: string | null;
  partOptions: Array<{
    label: string;
    value: string;
    description: string | null;
    count: number;
    quantity: number;
  }>;
  summary: {
    historyMonths: number;
    horizon: number;
    modelName: string;
    confidence: string;
    preprocessing: string;
    selectionBasis: string | null;
    adjustedMonths: number;
    candidateScores: Array<{
      model: string;
      label?: string;
      preprocessing?: string;
      adjustedMonths?: number;
      mae: number | null;
      wape: number | null;
      bias: number | null;
    }>;
    latestActual: number;
    recent3MonthAverage: number;
    nextForecast: number;
    deltaPct: number | null;
    mae: number | null;
    wape: number | null;
    bias: number | null;
    regime: string;
    regimeCode: string;
    forecastRisk: string;
  };
  series: Array<{
    month: string;
    actual: number | null;
    forecast: number | null;
    lower: number | null;
    upper: number | null;
  }>;
  insights: string[];
  anomalies: Array<{
    month: string;
    actual: number;
    baseline: number | null;
    deltaPct: number | null;
    severity: string;
  }>;
  changeAnalysis: {
    latestMonth: string;
    previousMonth: string;
    latestActual: number;
    previousActual: number;
    delta: number;
    deltaPct: number | null;
    notes: string[];
    brandDrivers: Array<{
      name: string;
      latest: number;
      previous: number;
      delta: number;
    }>;
    modelDrivers: Array<{
      name: string;
      latest: number;
      previous: number;
      delta: number;
    }>;
  } | null;
  watchlist: Array<{
    part: string;
    latestActual: number;
    nextForecast: number;
    deltaPct: number | null;
    confidence: string;
  }>;
  portfolio: {
    summary: {
      scannedParts: number;
      plannerReadyCount: number;
      reviewCount: number;
      doNotAutoPlanCount: number;
      plannerReadyShare: number;
    };
    recommendedPart: string | null;
    records: Array<{
      part: string;
      partDescription: string | null;
      historyMonths: number;
      latestActual: number;
      nextForecast: number;
      deltaPct: number | null;
      confidence: string;
      forecastRisk: string;
      regime: string;
      regimeCode: string;
      wape: number | null;
      bias: number | null;
      modelName: string;
      preprocessing: string;
      reliabilityTier: string;
      reliabilityCode: string;
      reliabilityPriority: number;
      reliabilityReason: string;
      reliabilityScore: number;
      totalQuantity: number;
      quantityShare: number;
    }>;
  };
};

export type AnomalyCenterPayload = {
  summary: {
    scannedParts: number;
    surfacedAlerts: number;
    structuralBreaks: number;
    highRiskForecasts: number;
    lowConfidenceForecasts: number;
  };
  regimeBreakdown: Array<{
    label: string;
    count: number;
  }>;
  records: Array<{
    part: string;
    partDescription: string | null;
    historyMonths: number;
    latestMonth: string;
    previousMonth: string | null;
    latestActual: number;
    previousActual: number;
    deltaPct: number | null;
    recent3MonthAverage: number;
    nextForecast: number;
    forecastDeltaPct: number | null;
    anomalyScore: number;
    regime: string;
    regimeCode: string;
    regimeSeverity: string;
    forecastRisk: string;
    confidence: string;
    wape: number | null;
    bias: number | null;
    modelName: string;
    preprocessing: string;
    adjustedMonths: number;
    evidence: string[];
    anomalies: Array<{
      month: string;
      actual: number;
      baseline: number | null;
      deltaPct: number | null;
      severity: string;
    }>;
    wholesaleSignal: {
      available: boolean;
      latestWholesale: number;
      wholesaleDeltaPct: number | null;
      expectedFromModel: number;
      modelWape: number | null;
      unexplainedResidualPct: number | null;
      wholesaleContribution: number | null;
      relationshipStrength: string;
    } | null;
    brandDrivers: Array<{
      name: string;
      latest: number;
      previous: number;
      delta: number;
    }>;
    modelDrivers: Array<{
      name: string;
      latest: number;
      previous: number;
      delta: number;
    }>;
  }>;
  filters: {
    search: string;
    brand: string[];
    model: string[];
    modelYear: string[];
    part: string[];
    startDate: string;
    endDate: string;
  };
};

export type PivotDimension = { key: string; label: string };
export type PivotMeasure = { key: string; label: string };

export type PivotPayload = {
  rowFields: string[];
  colFields: string[];
  measure: string;
  agg: string;
  availableDimensions: PivotDimension[];
  availableMeasures: PivotMeasure[];
  rowKeys: string[];
  colKeys: string[];
  cells: Record<string, Record<string, number>>;
  rowTotals: Record<string, number>;
  colTotals: Record<string, number>;
  grandTotal: number;
  rowCount: number;
  colCount: number;
  truncated: boolean;
  measureUnit: "currency" | "number";
};

export type AnalystPayload = {
  memoryId?: number;
  question: string;
  answer: string;
  evidence: string[];
  retrievedContext: Array<{
    source: string;
    title: string;
    content: string;
    tags: string[];
    score: number;
  }>;
  usedTools: string[];
  focusPart: string | null;
  riskLevel: string;
  recommendedActions: string[];
  followUpQuestions: string[];
  mode: string;
  model: string | null;
  warnings: string[];
};

export type AnalystMemoryItem = {
  id: number;
  createdAt: string;
  workbookId: string;
  sheetName: string;
  question: string;
  focusPart: string | null;
  riskLevel: string | null;
  answer: string;
  evidence: string[];
  recommendedActions: string[];
  followUpQuestions: string[];
  retrievedContext: Array<{
    source: string;
    title: string;
    content: string;
    tags: string[];
    score: number;
  }>;
  usedTools: string[];
  warnings: string[];
  mode: string | null;
  model: string | null;
  filters: {
    search: string;
    brand: string[];
    model: string[];
    modelYear: string[];
    part: string[];
    startDate: string;
    endDate: string;
  };
};

export const defaultTableState: TableState = {
  search: "",
  brand: [],
  model: [],
  modelYear: [],
  part: [],
  startDate: "",
  endDate: "",
  page: 1,
  pageSize: 50,
  sortField: "",
  sortOrder: "",
};

export function compactNumber(value: number) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function formatMetric(value: number | null, currency = false) {
  if (value === null || Number.isNaN(value)) return "N/A";
  return currency
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

export function chartOption(title: string, labels: string[], values: number[], kind: "line" | "bar" | "area") {
  const baseSeries = {
    data: values,
    smooth: true,
    symbolSize: 8,
    itemStyle: { color: "#2054f4" },
    lineStyle: { color: "#2054f4", width: 3 },
    areaStyle: kind === "area" ? { color: "rgba(32, 84, 244, 0.18)" } : undefined,
  };

  return {
    backgroundColor: "transparent",
    animationDuration: 600,
    grid: { left: 40, right: 20, top: 55, bottom: 35 },
    toolbox: {
      show: true,
      right: 0,
      top: 5,
      feature: {
        saveAsImage: {
          show: true,
          title: "Save Image",
        },
      },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#101725",
      borderWidth: 0,
      textStyle: { color: "#f8fbff" },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#d7e2ef" } },
      axisLabel: { color: "#607087" },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e5ecf5" } },
      axisLabel: { color: "#607087", formatter: (value: number) => compactNumber(value) },
    },
    series: [
      kind === "bar"
        ? {
            type: "bar",
            data: values,
            itemStyle: { color: "#2054f4", borderRadius: [10, 10, 0, 0] },
            barMaxWidth: 36,
          }
        : {
            ...baseSeries,
            type: "line",
          },
    ],
    title: {
      text: title,
      left: 0,
      top: 8,
      textStyle: {
        color: "#122033",
        fontWeight: 700,
        fontSize: 15,
        fontFamily: "Manrope, sans-serif",
      },
    },
  };
}

export function forecastChartOption(payload: ForecastPayload) {
  const labels = payload.series.map((point) => point.month);
  const actual = payload.series.map((point) => point.actual);
  const forecast = payload.series.map((point) => point.forecast);
  const lower = payload.series.map((point) => point.lower);
  const upper = payload.series.map((point) => point.upper);

  return {
    backgroundColor: "transparent",
    animationDuration: 600,
    grid: { left: 48, right: 24, top: 56, bottom: 40 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#101725",
      borderWidth: 0,
      textStyle: { color: "#f8fbff" },
    },
    legend: {
      right: 12,
      top: 8,
      textStyle: { color: "#607087" },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#d7e2ef" } },
      axisLabel: { color: "#607087" },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e5ecf5" } },
      axisLabel: { color: "#607087", formatter: (value: number) => compactNumber(value) },
    },
    title: {
      text: "Part-level demand forecast",
      left: 0,
      top: 8,
      textStyle: {
        color: "#122033",
        fontWeight: 700,
        fontSize: 15,
        fontFamily: "Manrope, sans-serif",
      },
    },
    series: [
      {
        name: "Actual",
        type: "line",
        data: actual,
        smooth: true,
        symbolSize: 7,
        itemStyle: { color: "#2054f4" },
        lineStyle: { color: "#2054f4", width: 3 },
      },
      {
        name: "Forecast",
        type: "line",
        data: forecast,
        smooth: true,
        symbolSize: 7,
        itemStyle: { color: "#f97316" },
        lineStyle: { color: "#f97316", width: 3, type: "dashed" },
      },
      {
        name: "Lower bound",
        type: "line",
        data: lower,
        symbol: "none",
        lineStyle: { opacity: 0 },
        stack: "forecast-band",
      },
      {
        name: "Forecast range",
        type: "line",
        data: upper.map((value, index) => {
          const floor = lower[index];
          if (value === null || floor === null) return null;
          return value - floor;
        }),
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color: "rgba(249, 115, 22, 0.14)" },
        stack: "forecast-band",
      },
    ],
  };
}

export function buildWorkspaceParams(nextState: TableState) {
  const params = new URLSearchParams({
    page: String(nextState.page),
    page_size: String(nextState.pageSize),
    search: nextState.search,
    sort_field: nextState.sortField,
    sort_order: nextState.sortOrder,
    start_date: nextState.startDate,
    end_date: nextState.endDate,
  });
  nextState.brand.forEach((value) => params.append("brand", value));
  nextState.model.forEach((value) => params.append("model", value));
  nextState.modelYear.forEach((value) => params.append("model_year", value));
  nextState.part.forEach((value) => params.append("part", value));
  return params;
}
