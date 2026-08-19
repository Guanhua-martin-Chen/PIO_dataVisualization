"use client";

import { Alert, Button, Skeleton } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ForecastRequestError, governedFetch, officialErrorContent } from "./api";
import RunStatusBar from "./components/RunStatusBar";
import SectionSubnav from "./components/SectionSubnav";
import type { LatestRunResponse, ModelPerformanceEnvelope, PlcEnvelope, QaEnvelope, QuantityEnvelope, RevenueEnvelope, TopMoversEnvelope, WholesaleEnvelope, ExecutiveSummaryEnvelope, GovernedRunMetadata } from "./contract";
import { monthLabel } from "./formatters";
import { modelPlcMonths } from "./modelPlcSummary";
import OfficialNavigation from "./OfficialNavigation";
import { monthQueryValue, officialHref, resolveChoiceQuery, resolveMonthQuery, type OfficialQuery } from "./officialQuery";
import type { BrandPayload, GovernancePayload, OutputPayload } from "./payloads";
import BrandDriversView from "./views/BrandDriversView";
import GovernanceView from "./views/GovernanceView";
import ModelPlcPlanningView, { type HistoricalReportingEnvelope, type ModelPlcPlanningPayload } from "./views/ModelPlcPlanningView";
import OutputView from "./views/OutputView";
import QuantityView from "./views/QuantityView";
import RevenueView from "./views/RevenueView";
import TopMoversView from "./views/TopMoversView";
import WholesaleDriversView from "./views/WholesaleDriversView";
import { defaultPlanningMonth, uniqueMonths } from "./viewModels";
import styles from "./OfficialForecastSection.module.css";

const OFFICIAL_SECTIONS = ["brands", "revenue", "quantity", "wholesale", "plc", "governance", "top-movers", "output"] as const;
export type OfficialSection = typeof OFFICIAL_SECTIONS[number];
const MONTH_SECTIONS: OfficialSection[] = ["brands", "revenue", "quantity", "wholesale", "plc"];
const PLC_LEVELS = ["brand-plc", "model-plc"] as const;

type SectionPayload = BrandPayload | GovernancePayload | OutputPayload | RevenueEnvelope | QuantityEnvelope | WholesaleEnvelope | ModelPlcPlanningPayload | TopMoversEnvelope;
const copy: Record<OfficialSection, { eyebrow: string; title: string; description: string }> = {
  brands: { eyebrow: "Approved brand view", title: "Brand Performance", description: "Revenue movement, regular Wholesale scale, PNVW, and separately disclosed Kia Fleet components." },
  revenue: { eyebrow: "Approved forecast", title: "Revenue", description: "Official total, brand, and model revenue from one immutable approved run." },
  quantity: { eyebrow: "Approved forecast", title: "Quantity", description: "Accessory units, units per vehicle, and the separate Kia Fleet component." },
  wholesale: { eyebrow: "Governed input", title: "Wholesale Inputs", description: "Selected regular Wholesale is built model by model: Sponsor Plan where available, Internal Forecast only where missing." },
  plc: { eyebrow: "Official planning grain", title: "Model & PLC Planning", description: "Select a month to compare completed Actual detail with Original Forecast and future Forecast planning concentration." },
  governance: { eyebrow: "Release evidence", title: "Governance & QA", description: "Model performance, release checks, and immutable run metadata supplied by the API." },
  "top-movers": { eyebrow: "Approved movement ranking", title: "Top Movers", description: "Planning movements between adjacent forecast months, ranked by the governed API." },
  output: { eyebrow: "Approved deliverable", title: "Output Center", description: "Seven API-backed previews and the exact approved Sponsor XLSX download." },
};

function verifyRun(envelopes: Array<{ meta: GovernedRunMetadata }>) {
  if (new Set(envelopes.map((item) => item.meta.run_id)).size !== 1) throw new ForecastRequestError(502, "governed_forecast_run_mismatch", "Dashboard inputs came from different approved runs.");
}

async function loadBrand(signal: AbortSignal): Promise<BrandPayload> {
  const [executive, revenue, quantity, wholesale] = await Promise.all([
    governedFetch<ExecutiveSummaryEnvelope>("/executive-summary", signal),
    governedFetch<RevenueEnvelope>("/revenue", signal),
    governedFetch<QuantityEnvelope>("/quantity", signal),
    governedFetch<WholesaleEnvelope>("/wholesale-drivers", signal),
  ]);
  verifyRun([executive, revenue, quantity, wholesale]);
  return { executive, revenue, quantity, wholesale };
}

async function loadModelPlcPlanning(signal: AbortSignal): Promise<ModelPlcPlanningPayload> {
  const [plc, revenue, historical] = await Promise.all([
    governedFetch<PlcEnvelope>("/plc-planning", signal),
    governedFetch<RevenueEnvelope>("/revenue", signal),
    governedFetch<HistoricalReportingEnvelope>("/historical-reporting", signal),
  ]);
  verifyRun([plc, revenue, historical]);
  return { plc, revenue, historical };
}

async function loadGovernance(signal: AbortSignal): Promise<GovernancePayload> {
  const [performance, qa, latest] = await Promise.all([governedFetch<ModelPerformanceEnvelope>("/model-performance", signal), governedFetch<QaEnvelope>("/qa", signal), governedFetch<LatestRunResponse>("/runs/latest", signal)]);
  verifyRun([performance, qa, latest]); return { performance, qa, latest };
}
async function loadOutput(signal: AbortSignal): Promise<OutputPayload> {
  const [latest, executive, revenue, quantity, plc, wholesale, performance, qa] = await Promise.all([
    governedFetch<LatestRunResponse>("/runs/latest", signal), governedFetch<ExecutiveSummaryEnvelope>("/executive-summary", signal), governedFetch<RevenueEnvelope>("/revenue", signal), governedFetch<QuantityEnvelope>("/quantity", signal), governedFetch<PlcEnvelope>("/plc-planning", signal), governedFetch<WholesaleEnvelope>("/wholesale-drivers", signal), governedFetch<ModelPerformanceEnvelope>("/model-performance", signal), governedFetch<QaEnvelope>("/qa", signal),
  ]);
  verifyRun([latest, executive, revenue, quantity, plc, wholesale, performance, qa]); return { latest, executive, revenue, quantity, plc, wholesale, performance, qa };
}
async function loadSection(section: OfficialSection, signal: AbortSignal): Promise<SectionPayload> {
  if (section === "brands") return loadBrand(signal);
  if (section === "governance") return loadGovernance(signal);
  if (section === "output") return loadOutput(signal);
  if (section === "plc") return loadModelPlcPlanning(signal);
  if (section === "revenue") return governedFetch<RevenueEnvelope>("/revenue", signal);
  if (section === "quantity") return governedFetch<QuantityEnvelope>("/quantity", signal);
  if (section === "wholesale") return governedFetch<WholesaleEnvelope>("/wholesale-drivers", signal);
  return governedFetch<TopMoversEnvelope>("/top-movers", signal);
}

function sectionMonths(payload: SectionPayload, section: OfficialSection) {
  if (section === "brands") return uniqueMonths((payload as BrandPayload).revenue.data);
  if (section === "plc") return modelPlcMonths(payload as ModelPlcPlanningPayload);
  if (["revenue", "quantity", "wholesale"].includes(section)) {
    return uniqueMonths((payload as RevenueEnvelope | QuantityEnvelope | WholesaleEnvelope).data);
  }
  return [];
}

function plcBrands(payload: ModelPlcPlanningPayload) {
  const order = ["HMA", "GMA", "KUS"];
  return [...new Set(payload.plc.data.flatMap((row) => row.brand_group ? [row.brand_group] : []))]
    .sort((left, right) => {
      const leftIndex = order.indexOf(left);
      const rightIndex = order.indexOf(right);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex) || left.localeCompare(right);
    });
}

export default function OfficialForecastSection({
  section,
  initialQuery = {},
}: {
  section: OfficialSection;
  initialQuery?: OfficialQuery;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [payload, setPayload] = useState<SectionPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ForecastRequestError | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    loadSection(section, controller.signal).then(setPayload).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setPayload(null); setError(reason instanceof ForecastRequestError ? reason : new ForecastRequestError(502, "governed_forecast_unavailable", "The approved forecast service is unavailable."));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refreshKey, section]);
  const months = useMemo(() => payload ? sectionMonths(payload, section) : [], [payload, section]);
  const actualDataThrough = payload
    ? section === "brands"
      ? (payload as BrandPayload).revenue.meta.actual_data_through
      : section === "plc"
        ? (payload as ModelPlcPlanningPayload).plc.meta.actual_data_through
        : ["revenue", "quantity", "wholesale"].includes(section)
          ? (payload as RevenueEnvelope | QuantityEnvelope | WholesaleEnvelope).meta.actual_data_through
          : ""
    : "";
  const defaultMonth = payload && months.length
    ? section === "brands"
      ? months[0]
      : section === "plc"
        ? (payload as ModelPlcPlanningPayload).historical.data.latest_complete_month
        : defaultPlanningMonth(months, actualDataThrough)
    : "";
  const month = resolveMonthQuery(initialQuery.month, months, defaultMonth);
  const brands = section === "plc" && payload ? plcBrands(payload as ModelPlcPlanningPayload) : [];
  const brand = resolveChoiceQuery(initialQuery.brand, brands, brands[0] ?? "");
  const level = resolveChoiceQuery(initialQuery.level, PLC_LEVELS, "brand-plc");
  const navigationQuery: OfficialQuery = useMemo(() => ({
    month: month || initialQuery.month,
    brand: section === "plc" ? brand : initialQuery.brand,
    level: section === "plc" ? level : initialQuery.level,
  }), [brand, initialQuery.brand, initialQuery.level, initialQuery.month, level, month, section]);
  const updateQuery = useCallback((updates: OfficialQuery) => {
    router.replace(officialHref(pathname, { ...navigationQuery, ...updates }), { scroll: false });
  }, [navigationQuery, pathname, router]);
  useEffect(() => {
    if (!payload) return;
    const monthNeedsFallback = MONTH_SECTIONS.includes(section)
      && Boolean(initialQuery.month)
      && initialQuery.month !== monthQueryValue(month);
    const brandNeedsFallback = section === "plc" && Boolean(initialQuery.brand) && initialQuery.brand !== brand;
    const levelNeedsFallback = section === "plc" && Boolean(initialQuery.level) && initialQuery.level !== level;
    if (monthNeedsFallback || brandNeedsFallback || levelNeedsFallback) {
      router.replace(officialHref(pathname, navigationQuery), { scroll: false });
    }
  }, [brand, initialQuery.brand, initialQuery.level, initialQuery.month, level, month, navigationQuery, pathname, payload, router, section]);
  const content = useMemo(() => {
    if (!payload) return null;
    if (section === "brands") return <BrandDriversView payload={payload as BrandPayload} month={month} onMonthChange={(value) => updateQuery({ month: value })} />;
    if (section === "revenue") return <RevenueView payload={payload as RevenueEnvelope} month={month} onMonthChange={(value) => updateQuery({ month: value })} />;
    if (section === "quantity") return <QuantityView payload={payload as QuantityEnvelope} month={month} onMonthChange={(value) => updateQuery({ month: value })} />;
    if (section === "wholesale") return <WholesaleDriversView payload={payload as WholesaleEnvelope} month={month} onMonthChange={(value) => updateQuery({ month: value })} />;
    if (section === "plc") return <ModelPlcPlanningView payload={payload as ModelPlcPlanningPayload} month={month} brand={brand} level={level} onSelectionChange={(updates) => updateQuery(updates)} />;
    if (section === "governance") return <GovernanceView payload={payload as GovernancePayload} />;
    if (section === "top-movers") return <TopMoversView payload={payload as TopMoversEnvelope} />;
    return <OutputView payload={payload as OutputPayload} />;
  }, [brand, level, month, payload, section, updateQuery]);
  const sectionGroup = ["revenue", "quantity"].includes(section) ? "forecasts" : ["brands", "wholesale", "plc", "top-movers"].includes(section) ? "drivers" : null;
  const meta = payload ? section === "output"
    ? (payload as OutputPayload).latest.meta
    : section === "governance"
      ? (payload as GovernancePayload).performance.meta
      : section === "brands"
        ? (payload as BrandPayload).revenue.meta
        : section === "plc"
          ? (payload as ModelPlcPlanningPayload).plc.meta
          : (payload as RevenueEnvelope | QuantityEnvelope | WholesaleEnvelope | TopMoversEnvelope).meta
    : null;
  const title = section === "wholesale" && month
    ? `${monthLabel(month)} Governed Wholesale Inputs`
    : copy[section].title;
  return <main className={styles.page}>
    <OfficialNavigation query={navigationQuery} />
    <section className={styles.hero}><div><span>{copy[section].eyebrow}</span><h1>{title}</h1><p>{copy[section].description}</p></div></section>
    {sectionGroup ? <SectionSubnav group={sectionGroup} query={navigationQuery} /> : null}
    {meta ? <RunStatusBar meta={meta} loading={loading} onRefresh={() => setRefreshKey((value) => value + 1)} /> : null}
    {loading && !payload ? <section className={styles.loading}><Skeleton active paragraph={{ rows: 10 }} /></section> : null}
    {!loading && error ? <section className={styles.errorState}><Alert type="error" showIcon message={officialErrorContent(error).title} description={officialErrorContent(error).detail} /><Button type="primary" onClick={() => setRefreshKey((value) => value + 1)}>Try again</Button></section> : null}
    {payload ? content : null}
    <footer className={styles.footer}>Official values come from one immutable approved Forecast API run. This website does not fit models or generate an Official workbook.</footer>
  </main>;
}
