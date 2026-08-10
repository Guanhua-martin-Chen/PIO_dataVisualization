# Governed Forecast Dashboard Product Specification

## 1. Product outcome

The website should give Mobis planners one clear place to inspect source data,
understand the latest approved PIO forecast, identify material drivers, and
download the matching Sponsor workbook.

The first screen should answer, in under one minute:

- Where is the current month expected to land?
- How did that change from the pre-month forecast?
- What is the expected range?
- What is the next-month forecast?
- Which brands, models, and PLCs drive the change?
- Through what date are actuals available?
- Which approved run and registry are being shown?

## 2. Product boundary

The product has two deliberately separate areas.

### Data Workspace

Retain useful website-native capabilities when they pass audit:

- Excel upload for exploratory workspace use;
- sheet inspection;
- Raw Data EDA;
- Data Table with pagination and filters;
- Pivot Table;
- filtered CSV export;
- data-quality diagnostics.

These features are exploratory and operational. Uploading a workbook here must
not silently retrain the official model or replace the approved Forecast API
run.

### Official Forecast

All official numbers come from one approved Forecast API run. The website may
filter, aggregate for display where contract-safe, format, and visualize those
records. It may not select models, recalculate the official forecast, restore
exact-part planning, or create a different Sponsor workbook.

## 3. Target architecture

```text
Governed Forecasting Repository
  controlled pipeline -> QA -> approved immutable run
    -> versioned Forecast API
    -> exact seven-sheet Sponsor workbook
                    |
                    v
Website FastAPI server-side proxy / adapter
                    |
                    v
Next.js + React + Ant Design + ECharts dashboard
```

The browser calls only the website backend. The website backend stores:

- `GOVERNED_FORECAST_API_URL`
- `GOVERNED_FORECAST_API_KEY`

The key must not use a `NEXT_PUBLIC_` environment variable and must not be
returned to the browser.

## 4. Information architecture

### 4.1 Executive Overview — default Official Forecast page

Use a sponsor-facing hierarchy with a small number of large KPIs:

- Current Month Actual or Nowcast;
- Pre-Month Forecast;
- Change in dollars and percent;
- Expected Range;
- Next-Month Forecast;
- Actual Data Through;
- H1 WAPE;
- Forecast Status;
- HMA, GMA, and KUS contribution split;
- a short, rules-based BLUF draft.

The page must visibly label `actual`, `nowcast`, and `forecast`. It must show
run ID, registry version, data cutoff, generated timestamp, and confidence
without making metadata dominate the executive view.

### 4.2 Current Month + Next Month

Show the current landing view and the next planning month side by side:

- pre-month versus nowcast/actual;
- dollar and percentage movement;
- expected interval;
- brand decomposition;
- cutoff and period status.

A partial month is a nowcast as of the API cutoff, never a final actual.

### 4.3 Brand Drivers

For HMA, GMA, and KUS, show:

- revenue;
- PIO accessory quantity;
- regular non-Fleet Wholesale;
- official regular PNVW;
- MoM and YoY comparisons when valid;
- largest dollar-change driver;
- confidence and fallback visibility.

KUS Fleet Carpet Floor Mat must appear as a separate component row or callout.
Do not calculate regular PNVW from combined regular-plus-Fleet revenue.

### 4.4 Top Movers

Display the Forecast API's approved Brand + PLC movement ranking for each
comparison:

- upside and downside exactly in the order returned by `/top-movers`;
- rank, Brand, PLC, forecast component, dollar change, and percentage context;
- target and comparison months plus their explicit period types;
- Kia Fleet as the separate `kia_fleet_cfm_adjustment` component.

The website must not recalculate, sort, or pad this ranking. Version 1.1.0 uses
absolute revenue change for ranking, returns at most five real rows per
direction, and applies no thresholds or classifications. Percentage change is
context only and remains unavailable when comparison revenue is nonpositive.
This is an adjacent forecast-month comparison, not a same-target revision,
actual/nowcast change, alert, anomaly, or causal explanation.

### 4.5 PLC Planning

Provide:

- Brand + PLC quantity and revenue;
- Brand + Model + PLC drilldown;
- top growing and declining PLCs;
- planning confidence;
- regular and Kia Fleet components kept distinct;
- reconciliation status.

PLC is the official lower-level planning category. Do not present exact
`PIS_PNO` or Part Description as an Official Forecast level.

### 4.6 Methodology & Governance

Display concise API-supplied governance information:

- frozen selected methods by brand;
- H1, H2, H3, and combined performance evidence;
- fold coverage and prediction coverage;
- confidence hierarchy;
- allocation limitations at model/PLC detail;
- Kia Fleet treatment;
- release QA;
- run, registry, cutoff, schema, and source-commit metadata.

Technical formulas and detailed QA should be expandable rather than placed on
the executive landing screen.

### 4.7 Output Center

Provide one clearly labeled Official download:

- the exact hash-verified Sponsor workbook from the approved API run.

The Output Center may also offer current-view CSV exports that are explicitly
labeled as filtered display exports. It must not generate or imply a second
Official workbook.

### 4.8 About & Timeline

Static content may cover:

- the capstone and Mobis business problem;
- team roles and responsibilities;
- concise methodology;
- project timeline/Gantt;
- Phase 1 forecast system -> API -> Dashboard -> presentation.

This page does not require Forecast API data.

## 5. API-to-page mapping

The current API contract is versioned under `/api/v1`.

| Forecast API endpoint | Website use |
|---|---|
| `/health` | service health and approved-run availability |
| `/runs/latest` | global run banner and metadata |
| `/executive-summary` | Executive Overview and current/next month KPIs |
| `/revenue` | total, brand, and model revenue views |
| `/quantity` | total, brand, and model quantity views |
| `/plc-planning` | Brand + PLC and Brand + Model + PLC planning |
| `/wholesale-drivers` | regular Wholesale plan/fallback disclosures |
| `/model-performance` | methodology and model-governance evidence |
| `/top-movers` | API-ranked adjacent forecast-month Brand + PLC movements |
| `/qa` | release, PLC, reconciliation, and Fleet checks |
| `/downloads/sponsor-workbook` | exact Official workbook download |

The website proxy should preserve HTTP status meaning, validate schema version,
apply timeouts, and return safe errors. It should not silently fall back to the
website's internal forecast engine when the governed API is unavailable.

## 6. Existing website behavior: retain, isolate, or replace

### Likely retain after audit

- Next.js/React/Ant Design/ECharts framework;
- FastAPI website backend;
- upload and in-memory workbook workspace;
- Raw Data EDA, tables, Pivot, filters, and CSV export;
- reusable layout, navigation, loading, and error components;
- static About/Timeline content.

### Must be isolated as Legacy/Experimental or removed from Official paths

- browser-triggered official model fitting;
- Auto or manual model selection for Official Forecast;
- website-generated Official forecast values;
- exact `PIS_PNO` official planning;
- generic `-1 -> 0` business treatment;
- website-owned Fleet definitions;
- internally generated competing SOP/Sponsor workbook;
- hardcoded cutoff, current month, selected model, performance, or confidence.

Do not delete these areas before a code-level audit identifies dependencies and
reusable presentation components.

## 7. Visual and interaction direction

Use `private_reference_templates/Executive_Summary.pptx` only as a local visual
reference for information hierarchy, sponsor color cues, large KPI emphasis,
and BLUF/mover structure.

Do not copy its dense small text, proprietary numbers, screenshots, or manual
business conclusions. Translate the useful hierarchy into a cleaner web UI:

- few large KPIs above the fold;
- generous spacing and clear visual hierarchy;
- restrained sponsor-appropriate palette;
- consistent positive/negative semantics;
- readable charts with units and periods in titles/tooltips;
- details on demand rather than dense technical text;
- desktop-first but responsive for common laptop/tablet widths;
- keyboard-accessible controls and meaningful empty states.

The BLUF number foundation may be automatic. Manual context such as factory
shutdowns, supply issues, launches, and executive wording must be labeled
`Business Note` and must not feed the prediction model.

## 8. Required application states

Every Official Forecast surface must handle:

- loading;
- no approved run;
- unauthorized proxy/API request;
- upstream unavailable or timeout;
- unsupported schema version;
- stale run warning;
- empty/unavailable endpoint;
- partial data/nowcast;
- successful approved run.

Never replace a failed governed request with legacy forecast numbers while
keeping an Official label.

## 9. Upload and refresh roadmap

Upload-to-official-refresh is a later controlled phase, not the first API
integration.

The target workflow is:

```text
Mobis uploads governed file roles
  -> schema and source-role validation
  -> controlled pipeline job
  -> QA and reconciliation
  -> awaiting approval
  -> approved immutable run
  -> API latest pointer updates
  -> Dashboard and Sponsor workbook refresh together
```

The eventual admin flow should identify separate roles for the current primary
CapStone workbook and HMA, GMA, and Kia plan workbooks. Filenames may vary, but
the governed sheet/section schema must pass validation. A failed upload or QA
must leave the previous approved run visible.

The existing exploratory Data Workspace upload is not this release workflow.

## 10. Delivery phases

1. Read-only architecture audit of current backend, frontend, and internal
   forecasting paths.
2. Server-side Forecast API client/proxy, environment handling, schemas, and
   contract tests.
3. One Executive Overview end-to-end slice using a real approved local API run.
4. Revenue, quantity, brand, PLC, methodology/QA, and download surfaces.
5. API-ranked Top Movers with no website-side ranking or classification.
6. Cross-system reconciliation, privacy/security review, responsive and
   accessibility QA, backend tests, and frontend production build.
7. Only later: protected upload/run/QA/approval orchestration and deployment.

## 11. Definition of done

- Every Official number comes from one versioned approved API run.
- Dashboard totals, brands, components, and PLC detail reconcile to the API and
  the matching Sponsor workbook.
- Actual/nowcast/forecast labels are correct.
- KUS Fleet is separate and added exactly once; regular PNVW is preserved.
- Cutoff, run, registry, schema, confidence, and QA are visible.
- The homepage communicates the landing, change, range, next month, material
  drivers, and cutoff in under one minute.
- Raw EDA remains separate and cannot overwrite the approved run.
- No secrets or proprietary artifacts are committed to the public repository.
- Backend tests and frontend production build pass.
- Deployment and upload automation are described only as complete when they
  are actually implemented and validated.
