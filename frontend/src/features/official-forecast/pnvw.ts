import { finite } from "./formatters.ts";

export type PnvwDisplayState = {
  available: boolean;
  secondary: string | null;
  tooltip: string | null;
};

export const PNVW_EXPLANATION = "Regular PNVW = regular Revenue ÷ selected regular Wholesale. It is unavailable when the Wholesale denominator is zero or missing; Fleet uses a separate metric.";

export function pnvwDisplayState(
  value: unknown,
  selectedWholesale: unknown,
  forecastComponent: unknown,
): PnvwDisplayState {
  if (forecastComponent === "kia_fleet_cfm_adjustment") {
    return {
      available: false,
      secondary: "Fleet component",
      tooltip: "Fleet component — Regular PNVW does not apply.",
    };
  }

  if (finite(value) !== null) {
    return { available: true, secondary: null, tooltip: null };
  }

  if (finite(selectedWholesale) === 0) {
    return {
      available: false,
      secondary: "Selected Wholesale = 0",
      tooltip: "Selected regular Wholesale is 0 for this model-month, so PNVW cannot be calculated.",
    };
  }

  return {
    available: false,
    secondary: "Selected Wholesale unavailable",
    tooltip: "No positive selected regular Wholesale is available for this model-month, so PNVW cannot be calculated.",
  };
}
