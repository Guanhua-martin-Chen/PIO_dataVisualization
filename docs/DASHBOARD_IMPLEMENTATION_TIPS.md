# Dashboard Implementation Tips

## Purpose

Use this document when refining the Official Forecast dashboard. It translates the governed Forecast API contract, Historical Reporting, and the Sponsor workbook into practical UI guidance. It is not a new data contract and does not authorize the website to create a second forecasting system.

The Official Forecast pages, server-side proxy, protected Update Forecast workflow, Model & PLC Planning, and the three Top Movers comparison classes already exist. Improve them incrementally; do not rebuild the forecasting logic inside this repository.

## 1. Preserve the product split

Keep two visibly separate areas:

- **Official Forecast**: one Approved Run plus contract-safe display analysis from approved records;
- **Data Workspace**: exploratory upload, EDA, Data Table, Pivot, filtering, and CSV export.

A Data Workspace upload must never update the Approved Run, Official Forecast label, registry, or Sponsor workbook.

## 2. Preserve the two-repository architecture

The forecasting repository is the system of record.

The Dashboard may:

- call approved API endpoints through the website backend;
- format/filter approved records;
- compute completed-Actual Brand + PLC movement from Historical Reporting;
- compute the Actual-to-Plan all-in Brand + PLC bridge from Historical Reporting plus PLC Planning.

It must not:

- fit or select production models;
- reconstruct Official totals;
- infer Fleet rows or model attribution that are not governed;
- create another Sponsor workbook.

The browser must never receive `GOVERNED_FORECAST_API_KEY`.

## 3. Executive Overview

Keep the first screen decision-first:

- current Actual/Nowcast landing;
- pre-month comparison;
- next-month outlook;
- expected range when available;
- HMA/GMA/KUS contribution;
- actual-data cutoff;
- Approved Run / QA context.

Do not turn all metadata into KPI cards. Run ID, registry, schema, source commit, and timestamps should remain visible but secondary.

A partial month is a Nowcast, never final Actual.

## 4. Revenue and Quantity

Revenue pages should display governed total, brand, and model values without browser-side forecast reconstruction.

At quantity/model level:

- label quantity as **accessory units**, not vehicles;
- `accessory_units_per_wholesale_vehicle` is an average unit count, not penetration/attach rate;
- values may legitimately exceed 1;
- reconciliation/review flags provide context but never overwrite the approved number.

Regular PNVW remains a regular non-Fleet metric.

## 5. Model & PLC Planning

The implemented page uses one unified month selector.

Current period semantics:

- completed Historical Reporting month -> `Actual`;
- current lower-level planning month -> `Original Forecast`;
- later month -> `Forecast`.

The latest completed Actual month should remain the default when Historical Reporting is available.

Summary treatment:

- Top Models by Revenue;
- Top PLCs by Revenue;
- Model bars may use brand identity;
- PLC summaries may stack governed brand/components where appropriate.

Important rules:

- completed Actual remains observed all-in PIO and does not assert a row-level Fleet/dealer split;
- when approved Historical Reporting supplies `plc_component_records`, completed-Actual PLC summaries may show the governed Kia Fleet Carpet Floor Mat component separately at Brand + PLC level while preserving the all-in total;
- forecast Model ranking must not invent Kia Fleet model attribution;
- forecast PLC planning may preserve Kia Fleet as a separate governed component;
- Brand + PLC and Brand + Model + PLC are two views of the same hierarchy and must not be added together;
- exact `PIS_PNO` and Part Description are not Official planning levels;
- PLC units per Wholesale vehicle is a decimal unit intensity, never a percentage.

For completed Actual months, forecast-only detailed planning controls/table may be hidden when they would imply planning metadata that does not apply.

## 6. Top Movers behavior

The current page supports three distinct comparison classes. Keep the algorithms and wording separate.

### Completed Actual -> Completed Actual

Use approved `/historical-reporting` Brand + PLC Revenue records from one Approved Run.

The website may calculate:

```text
revenue_change = target_actual_revenue - comparison_actual_revenue
```

and rank the largest real movements for display.

Top Movers continues to use the all-in `plc_records` view for completed Actual comparisons. Do not substitute component-level Regular/Kia Fleet rows into this ranking unless the governed comparison contract is deliberately changed.

### Completed Actual -> Current-month Original Forecast

This is the **Actual-to-Plan bridge**.

Aggregate planning rows to all-in Brand + PLC before comparison:

```text
July all-in planning = regular + kia_fleet_cfm_adjustment
```

because the completed Actual comparison side uses the all-in `plc_records` view.

Do not:

- compare completed Actual with separate Regular/Fleet rows;
- show component/confidence tags on bridge rows;
- call this `Landing`;
- fabricate a current-month Model/PLC landing from the brand Nowcast.

### Original Forecast / Forecast -> Forecast

Use the governed `/top-movers` API directly for Forecast-to-Forecast movement.

Preserve:

- API-published net all-in Brand + PLC ranking;
- `forecast_component = "all_components"` as the published ranking-grain marker;
- upside/downside direction;
- Revenue change;
- percentage context.

Before the Forecast API calculates movement, it sums `regular` and
`kia_fleet_cfm_adjustment` for the same month, Brand, and PLC. Therefore,
Kia Carpet Floor Mat appears once as a net all-in mover, not as separate
Regular and Fleet movers. The browser must display the published API ranking
without calculation or re-ranking and must not show Regular/Fleet or
confidence badges on Forecast Top Movers.

For all mover classes:

- use chronological labels: earlier period -> later period;
- do not invent causes;
- do not add `Alert`, `Strength`, anomaly, severity, or materiality classifications without a governed rule;
- do not pad with zero-change rows.

## 7. Kia Fleet presentation

Keep `kia_fleet_cfm_adjustment` separate from `regular` wherever approved records expose it.

Rules:

- add Fleet exactly once;
- regular PNVW excludes Fleet;
- Fleet rows do not receive regular PNVW;
- do not use Part Description or `HBF14AC000` as a Fleet identifier;
- do not manufacture model attribution;
- completed Historical Reporting preserves all-in `plc_records` for comparisons and may also publish a reconciled `plc_component_records` view for Brand + PLC presentation; the component view does not assert row-level Fleet/dealer identity.

## 8. Wholesale Inputs

The Wholesale view is a disclosure page, not a second forecast engine.

Show approved:

- selected Wholesale used;
- sponsor plan;
- fallback increment/reason;
- source/status;
- Kia Fleet vehicle-plan context.

An explicit sponsor zero must remain zero. Missing/unavailable input is different from zero.

## 9. Governance & QA

Keep default governance content concise:

- frozen selected Revenue method per brand;
- H1/H2/H3 evidence and coverage;
- quantity/planning method context;
- confidence hierarchy;
- reconciliation status;
- Kia Fleet treatment;
- Approved Run/release QA.

Detailed formulas and candidate evidence can remain expandable.

## 10. Update Forecast

The protected browser-driven refresh workflow is implemented and should remain the normal monthly operator path.

```text
Upload 4 governed source roles
  -> validation
  -> pipeline
  -> QA / reconciliation
  -> Draft
  -> explicit approval
  -> immutable Approved Run
```

Required roles:

- CapStone / PIO;
- HMA plan;
- GMA plan;
- Kia plan.

Rules:

- `FORECAST_UPDATE_TOKEN` protects operator actions;
- the website forwards the token but does not own forecasting logic;
- validation/pipeline/QA failure leaves the previous Approved Run live;
- only approval switches the Approved Run;
- Dashboard and Sponsor XLSX update together after publication;
- the Data Workspace upload is unrelated to this controlled release path.

## 11. Output Center

The Official download is the exact Sponsor workbook from the Approved Run through the proxy.

Do not generate a competing Official workbook in the web repository.

## 12. Visual language

- Use compact values on cards/axes and exact values in tooltips/tables.
- Forecast upward is not automatically good, and downward is not automatically bad.
- Make period and unit semantics explicit.
- Currency may be compact on cards (`$12.3M`) and exact in detail.
- Quantity is accessory units.
- PNVW is dollars per regular non-Fleet Wholesale vehicle.
- Unit intensity is decimal units / Wholesale vehicle, never percent.
- Use horizontal bars for long model/PLC labels.
- Keep mobile/tablet behavior readable without page-level horizontal overflow.

## 13. Interaction and application states

Official pages must handle:

- loading;
- no Approved Run;
- unauthorized;
- upstream unavailable/timeout;
- unsupported schema;
- stale run;
- empty/unavailable data;
- partial-month Nowcast;
- successful Approved Run.

Never fall back to legacy forecast values while retaining the Official label.

## 14. Code organization

Preserve the current feature boundary:

```text
features/official-forecast/
  api.ts
  contract.ts
  modelPlcSummary.ts
  topMoverAnalysis.ts
  components/
  views/
```

Keep contract-safe data-to-view-model helpers small and testable.

Website display analysis is acceptable only when its inputs and semantics are explicitly governed, such as Historical Reporting Actual movement and the all-in Actual-to-Plan bridge. Production forecasting logic, registry selection, Fleet inference, and workbook publication remain outside this repository.

## 15. Public-repository safety

Never commit:

- raw/processed company data;
- Approved Run bundles;
- Sponsor workbooks;
- private sponsor presentations/screenshots;
- real API keys/operator tokens;
- `.env` files with secrets;
- private deployment URLs or local artifact paths.

Use synthetic test fixtures that preserve contract shape and business semantics.

## 16. Deployment guidance

The reference capstone deployment is one internal host.

- Build the frontend with `npm run build`.
- Run the shared frontend with `npm run start` rather than the development server.
- Expose only the Dashboard port to authorized internal users when possible.
- Keep the website backend and Forecast API internal/loopback on the same host.
- Windows + desktop Microsoft Excel is the validated/recommended host for the complete workbook release workflow.
- Client browsers may be Windows or macOS.
- Public hosting/domain purchase is not required.
- ngrok is for temporary demos only.

## 17. Acceptance checklist

- [ ] Every Official forecast value belongs to one Approved Run.
- [ ] Actual / Nowcast / Original Forecast / Forecast labels are correct.
- [ ] Official total remains governed and is not reconstructed by the browser.
- [ ] Kia Fleet is separate where governed and added exactly once.
- [ ] Regular PNVW excludes Fleet.
- [ ] Completed Actual does not claim a row-level Fleet/dealer split; any Fleet Actual presentation is limited to the governed reconciled Brand + PLC component view.
- [ ] Model & PLC Planning uses correct Actual/planning semantics.
- [ ] Actual-to-Plan bridge is all-in Brand + PLC and is not called Landing.
- [ ] Forecast-to-Forecast Top Movers preserves the API-published net all-in Brand + PLC ranking without browser re-ranking or component/confidence badges.
- [ ] No exact part number/Part Description is presented as Official planning grain.
- [ ] Update Forecast preserves the previous Approved Run until explicit approval.
- [ ] The Official workbook is the API-proxied approved artifact.
- [ ] Data Workspace cannot replace an Approved Run.
- [ ] Loading/error/stale/unsupported states remain explicit.
- [ ] No secrets/proprietary artifacts are committed.
- [ ] Proxy tests, Official Forecast tests, and production build pass before release.
