# Governed Forecast Dashboard Product Specification

## 1. Product outcome

The website gives Mobis planners one clear place to understand the latest approved PIO forecast, review completed Actual detail, inspect Model/PLC planning and movers, run the protected monthly refresh workflow, and download the matching Sponsor workbook.

The executive experience should answer quickly:

- Where is the current month expected to land?
- How does it compare with the pre-month forecast?
- What is the next-month outlook?
- Which brands, models, and PLCs are driving the planning view?
- What are the largest completed-Actual, Actual-to-Plan, and Forecast movements?
- Through what date are actuals available?
- Which Approved Run and registry are being shown?

## 2. Product boundary

The product has two deliberately separate areas.

### Data Workspace

The Data Workspace remains exploratory. It may support:

- Excel upload for exploratory analysis;
- sheet inspection;
- EDA;
- paginated Data Table;
- Pivot Table;
- filtered CSV export;
- data-quality diagnostics.

A Data Workspace upload must never retrain, replace, or relabel the Official Forecast.

### Official Forecast

The Official Forecast consumes one immutable Approved Run from the governed forecasting repository.

The website may:

- filter and format approved records;
- visualize approved records;
- perform contract-safe display aggregation;
- calculate completed-Actual movement from approved Historical Reporting records;
- calculate the Actual-to-Plan Brand + PLC bridge from approved Historical Reporting plus approved PLC Planning records.

The website may not:

- fit production models;
- select or promote production strategies;
- reconstruct a competing Official total;
- infer exact-part Official planning;
- invent Fleet attribution;
- generate a competing Sponsor workbook.

## 3. Architecture

```text
Governed Forecasting Repository
  four source-role uploads
    -> validation
    -> governed pipeline
    -> QA / reconciliation
    -> Draft
    -> explicit approval
    -> immutable Approved Run
         -> versioned Forecast API
         -> exact Sponsor XLSX
                    |
                    v
Website FastAPI server-side proxy / adapter
                    |
                    v
Next.js + React + Ant Design + ECharts Dashboard
```

The browser calls only the website layer. The website backend holds:

- `GOVERNED_FORECAST_API_URL`
- `GOVERNED_FORECAST_API_KEY`

The Forecast API key must never be exposed through a `NEXT_PUBLIC_` variable or returned to the browser.

The protected Update Forecast operator token is entered by the operator and forwarded through the website proxy to the governed forecasting service.

## 4. Information architecture

### 4.1 Executive Overview

Prioritize:

- current-month Actual or Nowcast;
- pre-month forecast and movement;
- next-month forecast;
- expected range when supplied;
- HMA / GMA / KUS contribution;
- actual-data cutoff;
- H1 performance context;
- Approved Run and release status.

A partial month is a Nowcast, never a final Actual.

### 4.2 Brand Performance

For HMA, GMA, and KUS, show approved Revenue, Quantity, regular non-Fleet Wholesale, regular PNVW, period context, and governed fallback/confidence information where available.

Kia Fleet Carpet Floor Mat remains a separate governed component and must not contaminate regular KUS PNVW.

### 4.3 Revenue and Quantity

Revenue and Quantity pages use only the Approved Run.

- Revenue shows approved total, brand, and model views.
- Quantity means PIO accessory units, not vehicles.
- `accessory_units_per_wholesale_vehicle` is an average unit count and may exceed 1; it is not a penetration percentage.
- Reconciliation and review flags are informational and do not overwrite approved values.

### 4.4 Model & PLC Planning

The page uses one month selector across completed Actual and planning months.

Period semantics:

- completed historical months -> `Actual`;
- current planning month at lower-level Model/PLC grain -> `Original Forecast`;
- later planning months -> `Forecast`.

The default month is the latest completed Actual month published by Historical Reporting.

Summary views:

- Top Models by Revenue;
- Top PLCs by Revenue.

Planning rules:

- PLC is the Official lower-level accessory planning category;
- completed Actual uses observed all-in PIO records and does not claim a row-level Fleet/dealer split;
- future planning may preserve `regular` and `kia_fleet_cfm_adjustment` separately where governed;
- Kia Fleet must not be manufactured into vehicle-model attribution when governed model allocation is unavailable;
- exact `PIS_PNO` and Part Description are not Official Forecast planning grains.

### 4.5 Top Movers

The detailed page supports three comparison classes.

#### Completed Actual movement

Examples:

```text
Apr Actual -> May Actual
May Actual -> Jun Actual
```

These comparisons use approved Historical Reporting Brand + PLC Revenue records from the same Approved Run. The website may calculate Revenue differences and rank the real movers for display.

#### Actual-to-Plan bridge

```text
Latest completed Actual -> current-month Original Forecast
```

The bridge compares all-in Brand + PLC Revenue. Current-month `regular` and `kia_fleet_cfm_adjustment` planning components are combined before comparison because completed Actual does not assert a row-level Fleet/dealer split.

Do not display Regular/Fleet component tags on bridge rows.

#### Forecast movement

Examples:

```text
Current-month Original Forecast -> next-month Forecast
Next-month Forecast -> following Forecast
```

Forecast-to-Forecast rankings come directly from the governed `/api/v1/top-movers` endpoint. Preserve the API's component identity, rank, direction, Revenue change, percentage context, and confidence metadata.

For all mover classes:

- do not invent causes;
- do not add anomaly/severity/materiality labels unless separately governed;
- do not call the Actual-to-Plan bridge a Landing comparison;
- do not fabricate July/current-month lower-level landing from a brand-level Nowcast.

### 4.6 Wholesale Inputs

The page discloses the Wholesale input used by the Official Forecast, sponsor plan values, governed fallback values/reasons, and Kia Fleet vehicle-plan context where available.

An explicit sponsor zero is different from missing/unavailable input and must remain zero.

### 4.7 Governance & QA

Display concise approved-run evidence:

- selected methods by brand;
- H1/H2/H3 performance evidence and coverage;
- confidence and allocation limitations;
- Kia Fleet treatment;
- reconciliation checks;
- release QA;
- run ID, registry, cutoff, schema, and source commit.

### 4.8 Output Center

Provide one clearly labeled Official workbook download: the exact Sponsor XLSX from the current Approved Run.

The website must not generate a second Official workbook.

### 4.9 Update Forecast

The protected monthly workflow is implemented and is the normal Official refresh path.

```text
Upload 4 governed source roles
  -> validation
  -> governed forecasting pipeline
  -> QA / reconciliation
  -> Draft Run
  -> explicit approval
  -> immutable Approved Run
  -> Dashboard + Sponsor XLSX update together
```

Required source roles:

- CapStone / PIO;
- HMA plan;
- GMA plan;
- Kia plan.

Validation, pipeline, or QA failures leave the previous Approved Run unchanged. Only explicit approval may switch the latest Approved Run.

The exploratory Data Workspace upload is not this release workflow.

## 5. API-to-page mapping

The current API contract is versioned under `/api/v1`.

| Forecast API endpoint | Website use |
|---|---|
| `/health` | service health and approved-run availability |
| `/runs/latest` | Approved Run metadata |
| `/executive-summary` | Executive Overview |
| `/revenue` | total / brand / model Revenue |
| `/quantity` | total / brand / model Quantity |
| `/plc-planning` | planning-month Brand + PLC and Brand + Model + PLC records |
| `/historical-reporting` | completed-Actual Model and Brand + PLC detail; Actual mover analysis |
| `/wholesale-drivers` | Wholesale source / fallback disclosure |
| `/model-performance` | model governance / performance evidence |
| `/top-movers` | governed Forecast-to-Forecast Brand + PLC movement rankings |
| `/qa` | release, PLC, reconciliation, and Fleet checks |
| `/downloads/sponsor-workbook` | exact Official workbook download |
| `/admin/forecast-updates` | protected upload / run / QA / approval workflow |

The website proxy preserves safe HTTP meaning, validates schema compatibility, applies timeouts, and never falls back to legacy forecast values while retaining an Official label.

## 6. Legacy / exploratory boundary

The following must remain outside Official behavior unless the governed architecture is deliberately changed:

- browser-triggered production model fitting;
- Auto/manual production model selection in the website;
- website-generated Official forecast values;
- exact `PIS_PNO` Official planning;
- website-owned Fleet definitions;
- generic source-value reinterpretation;
- internally generated competing Sponsor workbooks;
- hardcoded cutoffs, selected methods, or confidence.

## 7. Required application states

Official surfaces must handle:

- loading;
- no Approved Run;
- unauthorized proxy/API request;
- upstream unavailable/timeout;
- unsupported schema version;
- stale-run warning;
- empty/unavailable endpoint;
- partial-month Nowcast;
- successful Approved Run.

## 8. Deployment and handoff boundary

The capstone reference deployment is a single internal host running the Forecast API, website proxy, and built Next.js Dashboard.

- Windows + desktop Microsoft Excel is the validated/recommended host environment for the complete Sponsor workbook release workflow.
- Client users may use Windows or macOS browsers.
- Public cloud hosting and a public domain are not required.
- ngrok may be used for temporary demos only.
- Long-term SSO, managed secrets, monitoring, backup, HTTPS/internal DNS, and enterprise hosting are optional Mobis IT extensions.

## 9. Definition of done

The capstone implementation is considered complete when:

- every Official forecast value belongs to one Approved Run;
- Actual / Nowcast / Original Forecast / Forecast semantics are correct;
- Dashboard totals and planning detail reconcile to governed records;
- KUS Fleet is separate and added exactly once;
- regular PNVW excludes Fleet;
- completed Actual detail does not assert a row-level Fleet/dealer split;
- Model & PLC Planning uses governed Historical Reporting and PLC Planning data;
- Top Movers correctly separates Actual, Actual-to-Plan, and Forecast movement behavior;
- Update Forecast preserves the previous Approved Run until explicit approval;
- the Sponsor XLSX download is the exact approved artifact;
- Data Workspace cannot overwrite the Official Forecast;
- no secrets or proprietary artifacts are committed to the public repository;
- backend tests, Official Forecast frontend tests, and production build pass before release.
