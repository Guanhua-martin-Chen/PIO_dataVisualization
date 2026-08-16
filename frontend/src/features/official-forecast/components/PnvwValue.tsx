"use client";

import { Tooltip } from "antd";

import { exactCurrency } from "../formatters";
import { PNVW_EXPLANATION, pnvwDisplayState } from "../pnvw";
import styles from "./PnvwValue.module.css";

export function PnvwValue({
  value,
  selectedWholesale,
  forecastComponent,
}: {
  value: unknown;
  selectedWholesale: unknown;
  forecastComponent: unknown;
}) {
  const state = pnvwDisplayState(value, selectedWholesale, forecastComponent);

  if (state.available) {
    return <span className={styles.value}>{exactCurrency(value)}</span>;
  }

  const label = `N/A. ${state.secondary}. ${state.tooltip}`;
  return (
    <Tooltip title={state.tooltip}>
      <span className={styles.unavailable} aria-label={label} tabIndex={0}>
        <strong>N/A</strong>
        <small>{state.secondary}</small>
      </span>
    </Tooltip>
  );
}

export function PnvwNote() {
  return <p className={styles.note}>{PNVW_EXPLANATION}</p>;
}
