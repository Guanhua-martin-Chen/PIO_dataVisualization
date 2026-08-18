"use client";

import { SafetyCertificateOutlined } from "@ant-design/icons";
import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";

import { regularWholesaleWeightOption, sponsorPnvwBarOption } from "../charts/brandVisuals";
import OfficialChart from "../charts/OfficialChart";
import MetricCard from "../components/MetricCard";
import { PnvwNote, PnvwValue } from "../components/PnvwValue";
import type { GovernedForecastRecord } from "../contract";
import { compactCurrency, exactCurrency, finite, firstNumber, formatNumber, monthLabel, wholesaleSourceLabel } from "../formatters";
import type { BrandPayload } from "../payloads";
import { buildExecutivePnvwHistory, landingRevenueRows, revenueValue, uniqueMonths } from "../viewModels";
import { MonthControl } from "./controls";
import styles from "./OfficialViews.module.css";

export default function BrandDriversView({ payload, month, onMonthChange }: { payload: BrandPayload; month: string; onMonthChange: (month: string) => void }) {
  const months = uniqueMonths(payload.revenue.data);
  const actualComparison = payload.executive.data.current_vs_previous_actual;
  const comparisonMonth = actualComparison.comparison_month;
  const comparisonMonthLabel = monthLabel(comparisonMonth);
  const actualByBrand = new Map(actualComparison.brands.map((row) => [row.brand_group, row]));
  const hasActualComparison = actualComparison.status === "available" && month === actualComparison.current_month;
  const revenueRows = landingRevenueRows(payload.revenue.data, month).filter((row) => row.record_type.endsWith("_brand"));
  const forecastRows = payload.revenue.data.filter((row) => row.forecast_month === month && row.record_type === "forecast_brand");
  const wholesaleRows = payload.wholesale.data.filter((row) => row.forecast_month === month && row.record_type === "forecast_brand");
  const quantityRows = payload.quantity.data.filter((row) => row.forecast_month === month && row.record_type === "forecast_brand");
  const rows = (["HMA", "KUS", "GMA"] as const).map((brand) => {
    const revenue = revenueRows.find((row) => row.brand_group === brand);
    const forecast = forecastRows.find((row) => row.brand_group === brand);
    const wholesale = wholesaleRows.find((row) => row.brand_group === brand);
    const quantity = quantityRows.find((row) => row.brand_group === brand);
    const current = revenueValue(revenue);
    const preMonth = firstNumber(revenue?.premonth_forecast, revenue?.premonth_revenue_forecast);
    const originalForecastChange = finite(revenue?.change_from_premonth) ?? (current !== null && preMonth !== null ? current - preMonth : null);
    const previousActual = hasActualComparison ? actualByBrand.get(brand) : undefined;
    return {
      key: brand,
      brand,
      change: finite(previousActual?.revenue_change),
      originalForecastChange,
      wholesale: firstNumber(wholesale?.selected_hybrid_wholesale, wholesale?.forecast_vehicle_wholesale),
      pnvw: finite(forecast?.pnvw),
      source: wholesale?.wholesale_source,
      fleetQuantity: finite(quantity?.kia_fleet_adjustment_quantity),
    };
  });
  const totalWholesale = rows.every((row) => row.wholesale !== null)
    ? rows.reduce((sum, row) => sum + (row.wholesale ?? 0), 0)
    : null;
  const rowsWithShare = rows.map((row) => ({
    ...row,
    volumeShare: row.wholesale !== null && totalWholesale && totalWholesale > 0 ? row.wholesale / totalWholesale : null,
  }));
  const pnvwHistory = buildExecutivePnvwHistory(payload.executive);
  const columns: ColumnsType<(typeof rowsWithShare)[number]> = [
    { title: "Brand", dataIndex: "brand", key: "brand", render: (value) => <strong>{value}</strong> },
    { title: `Change vs ${comparisonMonthLabel} Actual`, dataIndex: "change", key: "change", align: "right", render: exactCurrency },
    { title: "Change vs Original Forecast", dataIndex: "originalForecastChange", key: "originalForecastChange", align: "right", render: exactCurrency },
    { title: "Regular Wholesale", dataIndex: "wholesale", key: "wholesale", align: "right", render: (value) => formatNumber(value) },
    { title: "Volume Share", dataIndex: "volumeShare", key: "volumeShare", align: "right", render: (value) => value === null ? "N/A" : `${(value * 100).toFixed(1)}%` },
    { title: "Regular PNVW ($ / regular Wholesale vehicle)", dataIndex: "pnvw", key: "pnvw", align: "right", render: (_, row) => <PnvwValue value={row.pnvw} selectedWholesale={row.wholesale} forecastComponent="regular" /> },
    { title: "Wholesale source", dataIndex: "source", key: "source", render: (value) => <Tag>{wholesaleSourceLabel(value)}</Tag> },
  ];
  const kus = rowsWithShare.find((row) => row.brand === "KUS");
  return <div className={styles.stack}>
    <div className={styles.controls}><label className={styles.controlField}><span>Forecast Month</span><MonthControl months={months} value={month} onChange={onMonthChange} /></label></div>
    <div className={styles.metricGrid}>
      {rowsWithShare.map((row) => (
        <MetricCard
          key={row.brand}
          label={`${row.brand} change vs ${comparisonMonthLabel} Actual`}
          value={row.change === null ? "Not available" : `${row.change >= 0 ? "+" : "−"}${compactCurrency(Math.abs(row.change))}`}
          detail={`Regular Wholesale ${formatNumber(row.wholesale)} · Volume Share ${row.volumeShare === null ? "N/A" : `${(row.volumeShare * 100).toFixed(1)}%`} · PNVW ${row.pnvw === null ? "N/A" : exactCurrency(row.pnvw)}`}
          tone={row.change === null ? "neutral" : row.change >= 0 ? "positive" : "negative"}
        />
      ))}
    </div>
    <div className={styles.chartGrid}>
      <OfficialChart
        eyebrow={`${monthLabel(month)} · selected full-month regular non-Fleet Wholesale`}
        title="Brand Weight by Regular Wholesale Volume"
        option={rowsWithShare.some((row) => row.wholesale !== null) ? regularWholesaleWeightOption(rowsWithShare) : null}
        summary="Full-month regular non-Fleet Wholesale input; Sponsor Plan is used where available, with governed fallback otherwise. Labels show each brand's share of the three-brand selected Wholesale base."
      />
      <OfficialChart
        eyebrow="Latest completed Actuals + current-month Nowcast · USD / regular Wholesale vehicle"
        title="Regular PNVW by Brand"
        option={pnvwHistory.length ? sponsorPnvwBarOption(pnvwHistory) : null}
        summary="Regular PNVW pairs regular non-Fleet PIO Revenue with the corresponding regular Wholesale denominator; the current month uses the API-published brand Nowcast and selected full-month Wholesale input."
      />
    </div>
    <section className={styles.callout}><SafetyCertificateOutlined /><div><h3>Kia Fleet stays separate</h3><p>{kus?.fleetQuantity === null || kus?.fleetQuantity === undefined ? "Fleet quantity is not available for this period." : `${formatNumber(kus.fleetQuantity)} governed Fleet accessory units are disclosed separately.`} Regular PNVW uses regular non-Fleet Wholesale only.</p></div></section>
    <section className={styles.tableCard}><div className={styles.sectionHeading}><div><span>API-supported performance</span><h2>Brand performance table</h2></div><Tag>No inferred causes</Tag></div><Table columns={columns} dataSource={rowsWithShare} pagination={false} scroll={{ x: 980 }} size="small" /><PnvwNote /></section>
  </div>;
}
