# Forecast API and Dashboard Integration Status

Last updated: 2026-08-22

## Current status

The governed forecasting backend, protected monthly update workflow, Dashboard integration, Model & PLC Planning, and Top Movers extensions are implemented and merged to `main`.

Current website delivery state:

```text
Governed Forecasting Repository
  -> protected source upload / validation
  -> existing forecast pipeline
  -> QA / Draft / explicit approval
  -> immutable Approved Run
  -> versioned Forecast API
  -> exact Sponsor XLSX
             |
             v
Website FastAPI server-side proxy
             |
             v
Next.js Official Forecast Dashboard
```

The Dashboard remains a presentation / operator layer. The forecasting repository remains the system of record.

## Implemented Official Forecast surfaces

- Executive Overview
- Brand Performance
- Revenue
- Quantity
- Wholesale Inputs
- Model & PLC Planning
- Top Movers
- Governance & QA
- Output Center
- Update Forecast

The exploratory Data Workspace remains separate and cannot replace the Approved Run.

## Model & PLC Planning

The current implementation provides one month selector across completed Actual and planning months.

- completed months come from approved `/historical-reporting` data;
- the latest complete month is the default Actual detail month;
- the current planning month is labeled `Original Forecast` at Model/PLC grain;
- later months are labeled `Forecast`;
- Top Models and Top PLCs are shown by Revenue;
- detailed Brand + PLC / Brand + Model + PLC planning remains available for planning months;
- Kia Fleet is not manufactured into model attribution when governed model allocation is unavailable;
- completed Actual detail remains observed all-in PIO actual and does not assert a row-level Fleet/dealer split.

## Top Movers

The current page supports three comparison classes.

### Completed Actual movement

Examples:

```text
Apr Actual -> May Actual
May Actual -> Jun Actual
```

These rankings are calculated from approved `/historical-reporting` Brand + PLC Revenue records from the same immutable run.

### Actual-to-Plan bridge

```text
Latest completed Actual -> current-month Original Forecast
```

The bridge compares all-in Brand + PLC values. Current-month regular and Kia Fleet planning components are combined before comparison because completed Actual does not assert a row-level Fleet/dealer split.

### Forecast movement

```text
Current-month Original Forecast -> next-month Forecast
Next-month Forecast -> following Forecast
...
```

Forecast-to-Forecast ranking is supplied by the governed `/top-movers` API at net all-in Brand + PLC grain. Before ranking, the API combines `regular` and governed `kia_fleet_cfm_adjustment` Revenue for the same month, Brand, and PLC; published mover rows use `forecast_component = "all_components"`. Component-level Regular/Fleet planning remains preserved outside Top Movers in PLC Planning, the Sponsor workbook, PNVW treatment, QA, and other governed Fleet detail views. The browser does not re-rank movers or show component/confidence badges in this Forecast Top Movers view.

No website-side model fitting, forecast reselection, anomaly classification, causal explanation, or materiality threshold is introduced by these display analyses.

## Protected Update Forecast workflow

The complete browser-driven workflow is implemented:

```text
Four source-role workbooks
  -> Upload and validation
  -> Governed forecast pipeline
  -> QA / reconciliation
  -> Draft Run
  -> explicit approval
  -> immutable Approved Run
  -> Dashboard + Sponsor XLSX update together
```

Required workbook roles:

- CapStone / PIO
- HMA plan
- GMA plan
- Kia plan

The operator workflow is protected by `FORECAST_UPDATE_TOKEN`.

The Forecast API itself may be protected by `FORECAST_API_KEY`; the website backend uses the same value through `GOVERNED_FORECAST_API_KEY`.

The browser never receives the Forecast API key.

## Current validation evidence

Final Phase 3 website validation completed before merge:

- focused governed proxy tests: **13 passed**;
- Official Forecast frontend tests: **25 passed**;
- Next.js 15 production build: **passed**, including compilation, lint/type validation, static page generation, and build finalization;
- GitHub Actions CI now reruns the focused governed proxy test, Official Forecast frontend tests, and production build for each push and pull request; it has no deployment step or secrets;
- live local Model & PLC Planning visual checks completed for completed Actual, current-month Original Forecast, and future Forecast views;
- live local Top Movers visual checks completed for Actual movement, Actual-to-Plan bridge, and Forecast movement;
- feature branch merged to `main` and removed locally/remotely.

Protected Update Forecast validation completed previously:

- real four-workbook upload and validation passed;
- governed pipeline reached Draft / Ready for approval;
- release QA passed **22/22** during the smoke test;
- the smoke test intentionally stopped before approval while running the feature branch, preserving the existing Approved Run;
- forecasting-repository full regression suite passed before workflow merge.

## Final reference-host acceptance

The final P0 reference-host acceptance is complete for the current Approved Run:

- the Governed Forecast API and Website proxy health endpoints both reported an available Approved Run with matching metadata;
- the Dashboard rendered the Official Forecast acceptance path: Overview, Revenue, Model & PLC Planning for Actual and planning periods, Top Movers, and Governance & QA;
- Governance & QA reported all release checks passing for the displayed run;
- Output Center downloaded a Sponsor workbook whose SHA-256 value matched the latest-run metadata.

This evidence validates the local three-service reference deployment and its immutable-run linkage. It is not a claim that the application is publicly hosted or operated as a Mobis production service.

## Repository / privacy boundary

This repository is public.

Never commit:

- company raw Excel files;
- processed proprietary data;
- Approved Run bundles;
- Sponsor workbooks;
- API keys, operator tokens, or `.env` files with real secrets;
- private sponsor PowerPoint files or screenshots;
- local private artifact paths.

The fixed website proxy allowlist includes the approved read-only Forecast API endpoints required by the Dashboard, including `historical-reporting`.

## Reference deployment

The recommended capstone handoff is a single-host internal deployment.

- One host runs ports 8100, 8000, and 3000.
- Windows + desktop Microsoft Excel is the validated/recommended host environment for the complete Sponsor workbook release workflow.
- Client users may access the Dashboard from Windows or macOS browsers.
- Public cloud hosting or a domain purchase is not required for the reference handoff.
- ngrok may be used only for temporary external demos.

See [`../DEPLOYMENT.md`](../DEPLOYMENT.md).

## Final human handoff actions

The documentation and local reference-host P0 acceptance are complete. The following actions require the designated project or Mobis owners:

1. create a fixed capstone release tag on both repositories;
2. confirm designated Mobis technical owners have access to the private forecasting repository;
3. deliver the validated Sponsor workbook through an approved private channel;
4. provide initial deployment credentials separately from GitHub, or have Mobis choose host-specific values on deployment.

Long-term hosting, SSO, enterprise secret management, monitoring, backup, and retention remain Mobis IT decisions rather than capstone blockers.
