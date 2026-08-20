# Sponsor Feedback Implementation — 2026-08-20

This note records two sponsor-facing presentation changes without changing the governed forecast itself.

## Period styling

- Completed Actual months keep the existing full brand colors.
- Current-month Nowcast keeps its existing light amber background treatment.
- Future Forecast bars are only slightly lighter (`opacity: 0.88`) so unfinished months read differently without losing HMA/KUS/GMA brand identity.
- Regular PNVW highlights the current-month Nowcast with the same light amber background. Actual PNVW bars remain unchanged.

These are display-only changes. Forecast values, PNVW formulas, and period semantics are unchanged.

## Top Movers

Forecast-to-Forecast Top Movers are sponsor-facing **net Brand + PLC** movements.
The governed Forecast API sums Regular and Kia Fleet components for the same month, brand, and PLC before calculating movement and ranking. The Dashboard displays that API ranking without re-ranking it.

This netting applies only to Top Movers. Model & PLC Planning, Sponsor XLSX output, PNVW, QA, and Kia Fleet governance continue to preserve Regular and Kia Fleet separately where governed.

For Carpet Floor Mat, the mover therefore appears once as the all-in KUS Carpet Floor Mat movement rather than as separate Regular upside and Kia Fleet downside records.
