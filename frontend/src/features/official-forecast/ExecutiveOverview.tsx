"use client";

import { ArrowDownOutlined, ArrowRightOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { Alert, Button, Collapse, Skeleton, Typography } from "antd";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ForecastRequestError, governedFetch, officialErrorContent } from "./api";
import { brandRevenueTrendOption, pnvwBarOption } from "./charts/chartOptions";
import OfficialChart from "./charts/OfficialChart";
import RunStatusBar from "./components/RunStatusBar";
import {
  buildExecutiveViewModel,
  type ExecutiveSummaryEnvelope,
  type ExecutiveViewModel,
  type LatestRunResponse,
  type TopMoversEnvelope,
} from "./contract";
import styles from "./ExecutiveOverview.module.css";
import {
  compactCurrency,
  dateLabel,
  formatPercent,
  monthLabel,
  timestampLabel,
} from "./formatters";
import OfficialNavigation from "./OfficialNavigation";
import type { OfficialQuery } from "./officialQuery";
import {
  buildExecutiveBrandSnapshots,
  buildExecutiveBrandTrend,
  buildExecutivePnvwHistory,
  rangeState,
  selectOverviewMovers,
  type ExecutiveBrandSnapshot,
} from "./viewModels";

type OverviewPayload = {
  view: ExecutiveViewModel;
  executive: ExecutiveSummaryEnvelope;
  topMovers: TopMoversEnvelope;
};

function periodLabel(value: ExecutiveViewModel["currentPeriodType"]) {
  return value === "actual" ? "Actual" : value === "nowcast" ? "Nowcast" : "Forecast";
}

function isOutsideForecastWindow(view: ExecutiveViewModel) {
  const end = new Date(`${view.meta.forecast_end.slice(0, 10)}T23:59:59Z`);
  if (Number.isNaN(end.valueOf())) return false;
  end.setUTCMonth(end.getUTCMonth() + 1, 0);
  return Date.now() > end.valueOf();
}

function executiveCurrency(value: number | null) {
  if (value === null) return "Not provided";
  return Math.abs(value) >= 1_000_000 ? `$${(value / 1_000_000).toFixed(1)}M` : compactCurrency(value);
}

function signedCompactCurrency(value: number | null) {
  if (value === null) return "Not provided";
  return `${value >= 0 ? "+" : "-"}${executiveCurrency(Math.abs(value))}`;
}

function signedPercent(value: number | null) {
  if (value === null) return "Percentage unavailable";
  return `${value >= 0 ? "+" : "-"}${formatPercent(Math.abs(value))}`;
}

function monthSpan(points: Array<{ month: string }>) {
  if (!points.length) return "Approved period";
  return `${monthLabel(points[0].month, true)} - ${monthLabel(points.at(-1)?.month ?? points[0].month, true)}`;
}

function componentLabel(value: string) {
  return value === "kia_fleet_cfm_adjustment" ? "Kia Fleet CFM" : "Regular";
}

function topMoverComparisonLabel(targetMonth: string, comparisonMonth: string, context: string) {
  if (context === "next_month_forecast_vs_current_month_premonth_forecast") {
    return `${monthLabel(targetMonth)} Forecast vs ${monthLabel(comparisonMonth)} Original Forecast`;
  }
  return `${monthLabel(targetMonth)} vs ${monthLabel(comparisonMonth)}`;
}

function TotalCard({
  view,
  range,
}: {
  view: ExecutiveViewModel;
  range: { available: true; low: number; high: number } | { available: false; low: null; high: null };
}) {
  return (
    <article className={`${styles.brandCard} ${styles.totalCard}`} data-brand="Total">
      <div className={styles.brandCardTop}>
        <span>Total</span>
        <small className={styles.cardPeriod} data-period={view.currentPeriodType}>{monthLabel(view.currentMonth, true)} · {periodLabel(view.currentPeriodType)}</small>
      </div>
      <strong>{executiveCurrency(view.currentValue)}</strong>
      <div className={styles.totalComparisons}>
        <small>{signedCompactCurrency(view.changeVsPreviousActual)} vs {monthLabel(view.previousMonth, true)} Actual</small>
        <small>{signedCompactCurrency(view.changeValue)} vs Original Forecast</small>
      </div>
      <div className={styles.totalDetails}>
        <span>Expected Range<b>{range.available ? `${executiveCurrency(range.low)}-${executiveCurrency(range.high)}` : "Not available"}</b></span>
      </div>
    </article>
  );
}

function NextTotalCard({ view }: { view: ExecutiveViewModel }) {
  return (
    <article className={`${styles.brandCard} ${styles.nextTotalCard}`} data-brand="Next Total">
      <div className={styles.brandCardTop}>
        <span>Total</span>
        <small className={styles.cardPeriod} data-period="forecast">{monthLabel(view.nextMonth, true)} · Forecast</small>
      </div>
      <strong>{executiveCurrency(view.nextMonthRevenue)}</strong>
      <small className={styles.nextTotalContext}>Primary horizon</small>
    </article>
  );
}

function BrandCard({ snapshot, view }: { snapshot: ExecutiveBrandSnapshot; view: ExecutiveViewModel }) {
  const tone = snapshot.changeValue === null ? "" : snapshot.changeValue >= 0 ? styles.positive : styles.negative;
  return (
    <article className={styles.brandCard} data-brand={snapshot.brand}>
      <div className={styles.brandCardTop}>
        <span>{snapshot.brand}</span>
        <small className={styles.cardPeriod} data-period={view.currentPeriodType}>{monthLabel(view.currentMonth, true)} · {periodLabel(view.currentPeriodType)}</small>
      </div>
      <strong>{executiveCurrency(snapshot.currentValue)}</strong>
      <small className={tone}>
        {signedCompactCurrency(snapshot.changeValue)} vs {monthLabel(view.previousMonth, true)} Actual
      </small>
      <div className={styles.brandNext}>
        <span>{monthLabel(view.nextMonth, true)} Forecast</span>
        <b>{executiveCurrency(snapshot.nextValue)}</b>
      </div>
    </article>
  );
}

export default function ExecutiveOverview({ query = {} }: { query?: OfficialQuery }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [payload, setPayload] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ForecastRequestError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      governedFetch<ExecutiveSummaryEnvelope>("/executive-summary", controller.signal),
      governedFetch<LatestRunResponse>("/runs/latest", controller.signal),
      governedFetch<TopMoversEnvelope>("/top-movers", controller.signal),
    ])
      .then(([executive, latest, topMovers]) => {
        if (new Set([executive.meta.run_id, latest.meta.run_id, topMovers.meta.run_id]).size !== 1) {
          throw new ForecastRequestError(502, "governed_forecast_run_mismatch", "Overview inputs came from different approved runs.");
        }
        setPayload({ view: buildExecutiveViewModel(executive, latest), executive, topMovers });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setPayload(null);
        setError(reason instanceof ForecastRequestError
          ? reason
          : new ForecastRequestError(502, "governed_forecast_unavailable", "The approved forecast service is unavailable."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refreshKey]);

  const chartData = useMemo(() => payload ? {
    trend: buildExecutiveBrandTrend(payload.executive),
    brands: buildExecutiveBrandSnapshots(payload.executive),
    pnvw: buildExecutivePnvwHistory(payload.executive),
  } : null, [payload]);
  const governedRange = payload ? rangeState(payload.view) : { available: false as const, low: null, high: null };
  const defaultMoverComparison = payload?.topMovers.data.comparisons.find(
    (item) => item.comparison_id === payload.topMovers.data.default_comparison_id,
  );
  const overviewMovers = selectOverviewMovers(defaultMoverComparison);
  const refresh = () => setRefreshKey((value) => value + 1);

  return (
    <main className={styles.page}>
      <OfficialNavigation query={query} />
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}>Executive decision view</div>
          <h1>{payload ? `${monthLabel(payload.view.currentMonth)} Executive Overview` : "Executive Overview"}</h1>
          <p>{payload
            ? `Actuals through ${dateLabel(payload.view.meta.actual_data_through)} · ${monthLabel(payload.view.currentMonth)} ${periodLabel(payload.view.currentPeriodType)} · ${monthLabel(payload.view.nextMonth)} Next-Month Forecast`
            : "Current landing, brand results, and the approved outlook in one view."}</p>
        </div>
      </section>

      {loading ? (
        <section className={styles.loadingPanel} aria-label="Loading Official Forecast"><Skeleton active paragraph={{ rows: 10 }} /></section>
      ) : error ? (
        <section className={styles.statePanel}>
          <Alert type="error" showIcon message={officialErrorContent(error).title} description={officialErrorContent(error).detail} />
          <div className={styles.stateActions}><Button type="primary" onClick={refresh}>Try again</Button><Link href="/data-workspace">Open Data Workspace</Link></div>
        </section>
      ) : payload && chartData ? (
        <>
          {isOutsideForecastWindow(payload.view) ? <Alert className={styles.warning} type="warning" showIcon message="Approved run is outside its published forecast window" /> : null}
          <RunStatusBar meta={payload.view.meta} confidence={payload.view.confidence} h1Wape={payload.view.h1Wape} loading={loading} onRefresh={refresh} />

          <section className={styles.kpiGrid} aria-label="Total and brand current-month forecast KPIs">
            <TotalCard view={payload.view} range={governedRange} />
            <NextTotalCard view={payload.view} />
            {chartData.brands.map((snapshot) => <BrandCard snapshot={snapshot} view={payload.view} key={snapshot.brand} />)}
          </section>

          <section className={styles.primaryChart}>
            <OfficialChart
              eyebrow={`${monthSpan(chartData.trend)} · USD · Actual / Nowcast / Forecast`}
              title="Monthly PIO Revenue by Brand and Total"
              option={chartData.trend.length ? brandRevenueTrendOption(
                chartData.trend,
                governedRange.available ? { month: payload.view.currentMonth, low: governedRange.low, high: governedRange.high } : undefined,
              ) : null}
              summary="Brand Revenue bars and the API-published Official Total share one USD axis."
              height={310}
              compact
            />
          </section>

          <section className={styles.bottomGrid}>
            <OfficialChart
              eyebrow={`${monthSpan(chartData.pnvw)} · Actual · USD / regular Wholesale vehicle`}
              title="Regular PNVW by Brand"
              option={chartData.pnvw.length ? pnvwBarOption(chartData.pnvw) : null}
              summary="Regular non-Fleet Revenue per regular Wholesale vehicle."
              height={190}
              compact
            />
            <article className={styles.moversCard}>
              <div className={styles.sectionHeading}><div><span>API-ranked movement</span><h2>Largest Forecast Movements</h2></div></div>
              <p>{defaultMoverComparison
                ? topMoverComparisonLabel(defaultMoverComparison.target_month, defaultMoverComparison.comparison_month, defaultMoverComparison.comparison_context)
                : "The default API comparison was not returned."}</p>
              {overviewMovers.length ? (
                <ol className={styles.moverList}>
                  {overviewMovers.map((mover) => (
                    <li key={`${mover.direction}-${mover.rank}-${mover.brand_group}-${mover.plc}-${mover.forecast_component}`}>
                      <span className={mover.direction === "upside" ? styles.upsideIcon : styles.downsideIcon}>
                        {mover.direction === "upside" ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                      </span>
                      <span><b>{mover.brand_group} · {mover.plc}</b><small>{componentLabel(mover.forecast_component)} · API rank #{mover.rank}</small></span>
                      <strong className={styles.moverValue}>
                        <span>{signedCompactCurrency(mover.revenue_change)}</span>
                        {mover.revenue_change_pct === null ? null : <small>{signedPercent(mover.revenue_change_pct)}</small>}
                      </strong>
                    </li>
                  ))}
                </ol>
              ) : <div className={styles.moversEmpty}>No ranked movement is available in this approved run.</div>}
              <small className={styles.moversNote}>Adjacent forecast-month movement only; not a revision, alert, anomaly, or business cause.</small>
              <Link href="/official-forecast/top-movers">View all movers <ArrowRightOutlined /></Link>
            </article>
          </section>

          <Collapse
            className={styles.metadataCollapse}
            items={[{
              key: "run-metadata",
              label: "Run metadata and publication evidence",
              children: (
                <dl className={styles.metadataGrid}>
                  <div><dt>Run ID</dt><dd><Typography.Text className={styles.copyableId} copyable={{ text: payload.view.meta.run_id }}>{payload.view.meta.run_id}</Typography.Text></dd></div>
                  <div><dt>Generated</dt><dd>{timestampLabel(payload.view.meta.generated_at)}</dd></div>
                  <div><dt>Published</dt><dd>{timestampLabel(payload.view.meta.published_at)}</dd></div>
                  <div><dt>Training through</dt><dd>{dateLabel(payload.view.meta.completed_training_data_through)}</dd></div>
                  <div><dt>Forecast window</dt><dd>{dateLabel(payload.view.meta.forecast_start)} - {dateLabel(payload.view.meta.forecast_end)}</dd></div>
                  <div><dt>Release QA</dt><dd>{payload.view.releaseChecksPassed}/{payload.view.releaseCheckCount} passed</dd></div>
                  <div><dt>Workbook</dt><dd>{payload.view.workbookVerified ? "Hash verified" : "Verification not provided"}</dd></div>
                  <div><dt>Source commit</dt><dd>{payload.view.meta.source_git_commit}</dd></div>
                </dl>
              ),
            }]}
          />
        </>
      ) : null}
    </main>
  );
}
