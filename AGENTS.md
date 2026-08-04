# AGENTS.md

## Project role

This repository is the web, dashboard, data-intake, and interaction layer for
the PIO Accessories Forecasting project. It is not the source of truth for the
official forecast.

The governed forecasting repository is:

<https://github.com/Guanhua-martin-Chen/pio-accessories-forecasting-optimization>

Its versioned, read-only Forecast API is the only approved source for official
forecast values, model selections, reconciliations, Kia Fleet treatment,
release QA, and the seven-sheet Sponsor workbook.

## Mandatory pre-change gate

Before modifying code, documentation, configuration, tests, or UI:

1. Read this file completely.
2. Read `README.md`.
3. Read `docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md` completely.
4. Read `docs/INTEGRATION_STATUS.md` completely.
5. Read the current Forecast API contract in the forecasting repository:
   `docs/phase2_api_contract.md`.
6. Run `git status -sb`, `git log -5 --oneline`, and `git remote -v`.
7. Inspect the current implementation instead of assuming README descriptions
   or older chat summaries are current.
8. For a material architecture, official-data-source, navigation, or public
   release change, list the exact intended files and behavior before editing.

## Repository boundaries

- Keep this website repository and the forecasting repository independent.
- Do not merge Git histories, use a submodule, or copy forecasting model code
  into this repository.
- Official Forecast pages must consume an approved run through the Forecast
  API. They must not fit models, select strategies, parse the Sponsor workbook,
  or recalculate official values.
- The website FastAPI backend acts as a server-side proxy/adapter. The browser
  must never receive the governed API key.
- Existing internal forecasting code is legacy or experimental until a
  read-only audit proves it is compatible with the current API contract. It
  must not be presented as Official Forecast.
- Raw-data upload, EDA, Data Table, Pivot, and filtered CSV export may remain as
  a separate Data Workspace. They do not change an approved official run.

## Official forecast rules the UI must preserve

- `period_type` is explicit: `actual`, `nowcast`, or `forecast`. A partial
  month must never be labeled final actual.
- Official lower-level planning uses PLC, at Brand + PLC and Brand + Model +
  PLC. Exact `PIS_PNO` and Part Description are not official forecast grains.
- KUS Fleet Carpet Floor Mat is a separate forecast component and is added
  exactly once. It must not contaminate regular PNVW.
- Official total revenue is the sum of the governed brand forecasts. The
  website does not substitute an internally calculated total.
- Confidence, cutoff, run ID, registry version, source commit, and QA status
  remain visible and come from API metadata rather than hardcoded UI text.
- The downloadable Sponsor workbook comes from the API's approved run. The
  website must not generate a competing Official workbook.

## Public-repository and privacy rules

This fork is public. Never commit:

- company raw Excel files;
- processed proprietary data or approved-run bundles;
- Sponsor workbooks;
- API keys, tokens, `.env` files, or private deployment URLs;
- proprietary screenshots, presentations, or business notes;
- local absolute paths that disclose private artifacts.

Use sanitized schemas, fixtures, or small synthetic examples in tests. Runtime
secrets belong in environment variables.

`private_reference_templates/` is intentionally git-ignored. A local copy of
`Executive_Summary.pptx` may be used only as a visual and information-hierarchy
reference. Do not quote, redistribute, commit, or reproduce proprietary text,
figures, screenshots, or manual business conclusions from it.

## Git workflow

- `origin` is the user's fork.
- `upstream` is `Noah-wang/PIO_dataVisualization`.
- Do not push to `upstream` unless the user explicitly requests it and has the
  necessary authority.
- Use a focused feature branch for application changes unless the user
  explicitly requests a direct `main` documentation update.
- Stage explicit files only, preserve unrelated user changes, and run relevant
  backend tests plus the frontend build before publishing implementation work.

## Current phase

The read-only Forecast API exists in the forecasting repository. The next
phase is a read-only architecture audit of this website repository, followed by
a server-side proxy and one Executive Overview end-to-end slice. Do not begin
the wider dashboard rewrite until the audit scope is approved.
