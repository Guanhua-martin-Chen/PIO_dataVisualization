# AGENTS.md

## Project role

This repository is the web, dashboard, data-intake, and interaction layer for the PIO Accessories Forecasting project.

It is **not** the source of truth for the Official Forecast.

The governed forecasting repository is:

`Guanhua-martin-Chen/pio-accessories-forecasting-optimization`

Its versioned Forecast API and immutable Approved Runs are the authoritative source for official forecast values, model selections, reconciliations, Kia Fleet treatment, release QA, and the exact Sponsor workbook.

## Mandatory pre-change gate

Before modifying code, documentation, configuration, tests, or UI:

1. read this file completely;
2. read `README.md`;
3. read `docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md`;
4. read `docs/DASHBOARD_IMPLEMENTATION_TIPS.md`;
5. read `docs/INTEGRATION_STATUS.md`;
6. read the current Forecast API contract in the forecasting repository;
7. run `git status -sb`, `git log -5 --oneline`, and `git remote -v`;
8. inspect the current implementation instead of relying on old branch notes or chat summaries;
9. for a material architecture, official-data-source, navigation, or public release change, list the intended files and behavior before editing.

## Repository boundaries

- Keep this website repository and the forecasting repository independent.
- Do not merge Git histories, use a submodule, or copy forecasting model code into this repository.
- Official Forecast pages consume one Approved Run through the Forecast API.
- The website must not fit production models, select production strategies, regenerate the Sponsor workbook, or create a competing Official total.
- The website FastAPI backend is the server-side proxy/adapter. The browser must never receive the governed API key.
- Data Workspace upload, EDA, Data Table, Pivot, and filtered CSV export remain exploratory and cannot change the Approved Run.
- Legacy/internal website forecasting code, where retained, must remain clearly separated from Official Forecast behavior.

## Official Forecast rules the UI must preserve

- `actual`, `nowcast`, `Original Forecast`, and future `Forecast` labels must reflect the governed period semantics.
- A partial month must never be labeled final Actual.
- Official lower-level planning uses PLC at Brand + PLC and Brand + Model + PLC grain.
- Exact `PIS_PNO` and Part Description are not Official Forecast grains.
- KUS Fleet Carpet Floor Mat is a separate governed component and is added exactly once.
- Regular PNVW must remain a regular non-Fleet metric.
- Kia Fleet must not be manufactured into vehicle-model attribution when no governed model allocation exists.
- Completed Historical Reporting is observed all-in PIO actual and must not claim a row-level Fleet/dealer split.
- Official total Revenue remains supplied by the governed Forecast API.
- Run ID, registry version, cutoff, schema, confidence, and QA come from approved-run metadata rather than hardcoded UI text.
- The downloadable Sponsor workbook comes from the Approved Run and is not recreated by this website.

## Top Movers rules

The detailed Top Movers page currently supports:

1. completed Actual -> completed Actual movement;
2. latest completed Actual -> current-month Original Forecast bridge;
3. adjacent Forecast-month movement.

Rules:

- Forecast-to-Forecast ranking remains the governed `/top-movers` API ranking.
- Completed-Actual comparisons may calculate Brand + PLC Revenue differences only from approved `/historical-reporting` records from the same run.
- The Actual-to-Plan bridge may calculate Brand + PLC Revenue differences only from approved Historical Reporting and PLC Planning records from the same run.
- For the bridge, regular and Kia Fleet planning components are combined to all-in Brand + PLC before comparison because completed Actual does not assert a row-level Fleet/dealer split.
- Do not introduce causal explanations, anomalies, alerts, or materiality classifications without a separately governed rule.

## Update Forecast rules

The protected Update Forecast workflow is implemented and is the normal monthly refresh path.

```text
4 governed source-role uploads
  -> validation
  -> existing forecast pipeline
  -> QA / reconciliation
  -> Draft
  -> explicit approval
  -> immutable Approved Run
```

- `FORECAST_UPDATE_TOKEN` protects operator actions.
- Validation / pipeline / QA failures must leave the previous Approved Run unchanged.
- Only explicit approval may switch the latest Approved Run.
- The website forwards the operator token but does not own the forecasting pipeline.

## Public-repository and privacy rules

This repository is public. Never commit:

- company raw Excel files;
- processed proprietary data or Approved Run bundles;
- Sponsor workbooks;
- API keys, operator tokens, `.env` files, or private deployment URLs;
- proprietary screenshots, presentations, or business notes;
- local absolute paths that disclose private artifacts.

Use synthetic fixtures in tests. Runtime secrets belong in environment variables or other private local deployment configuration.

`private_reference_templates/` remains git-ignored and is for local visual reference only.

## Git workflow

- `origin` is the user's fork.
- `upstream` is `Noah-wang/PIO_dataVisualization`.
- Do not push to `upstream` unless explicitly requested and authorized.
- Use a focused feature/docs branch for changes unless a direct `main` change is explicitly requested.
- Preserve unrelated user changes.
- Run relevant backend tests and the frontend production build before merge.

## Current delivery state

The capstone delivery implementation is complete on `main` for:

- governed Forecast API proxy integration;
- Official Forecast dashboard surfaces;
- protected Update Forecast UI;
- Model & PLC Planning with completed Actual / Original Forecast / future Forecast month semantics;
- completed Actual and Actual-to-Plan Top Movers analysis using approved governed inputs;
- API-ranked Forecast-to-Forecast Top Movers;
- exact Sponsor workbook download;
- deployment and handoff documentation.

Future work should be treated as optional enhancement unless Mobis explicitly requests it. Examples include enterprise hosting, SSO/RBAC, managed secrets, monitoring, auto-start services, backups, and retention controls.
