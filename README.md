# PIO Demand Intelligence Platform

UCLA Master of Engineering Data Science capstone project with Hyundai Mobis / Mobis Parts America.

This public repository is the **Dashboard and operator layer** for the governed PIO forecasting system. It displays one immutable Approved Run from the private forecasting repository, provides the protected monthly Update Forecast workflow, and keeps exploratory data tools separate from Official Forecast outputs.

## What this repository does

The application has two deliberately separate areas.

### Official Forecast

All Official values come from one approved Forecast API run.

Main views include:

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

The website does **not** select production models, retrain the Official Forecast in the browser, or generate a competing Sponsor workbook.

### Data Workspace

The existing exploratory workspace remains available for:

- workbook inspection;
- EDA;
- paginated data tables;
- filters;
- pivot tables;
- CSV exports;
- data-quality diagnostics.

Data Workspace activity does not replace the Approved Run.

## System architecture

```text
Mobis users (Windows or Mac browser)
            |
      internal network
            |
            v
Dashboard / Next.js :3000
            |
            v
Website FastAPI proxy :8000
            |
            v
Governed Forecast API :8100
            |
            v
Forecast pipeline / QA / Approved Run / Sponsor XLSX
```

The private forecasting repository is the system of record:

`Guanhua-martin-Chen/pio-accessories-forecasting-optimization`

The browser never receives the governed Forecast API key.

## Recommended capstone deployment

The simplest handoff is a **single-host internal deployment**.

- One Mobis host machine runs the three services.
- Dashboard users can access the site from Windows or macOS through a modern browser.
- A Windows host with desktop Microsoft Excel is recommended for the full Update Forecast release workflow because the final Sponsor workbook formula-cache refresh uses Excel automation.
- A public domain, cloud server, or paid hosting service is not required for the capstone handoff.
- Mobis IT may later migrate the services into its own enterprise infrastructure.

For temporary external demos, a tunnel such as ngrok may be used. It is not the recommended permanent deployment.

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the complete local/internal-host startup guide.

## First-time setup

### 1. Clone this repository

Because this repository is public, read-only clone access does not require a GitHub invitation.

```powershell
git clone https://github.com/Guanhua-martin-Chen/PIO_dataVisualization.git
cd PIO_dataVisualization
```

Write access is only needed if Mobis intends to maintain changes in this repository.

### 2. Create the website Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Install the frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

### 4. Configure the Forecast API connection

The website backend needs the private Forecast API URL and the same API key configured on the forecasting host service.

```powershell
$env:GOVERNED_FORECAST_API_URL = "http://127.0.0.1:8100"
$env:GOVERNED_FORECAST_API_KEY = "<same-value-as-FORECAST_API_KEY>"
```

These are runtime settings. Real credentials must not be committed to GitHub.

Changing the key later does not require a code change. The Forecast API's `FORECAST_API_KEY` and this repository's `GOVERNED_FORECAST_API_KEY` must simply be updated to the same new value before the services are restarted.

## Start the three services

### Terminal 1 — Forecast backend

From the private forecasting repository:

```powershell
.\.venv\Scripts\Activate.ps1
$env:FORECAST_API_KEY = "<private-api-key>"
$env:FORECAST_UPDATE_TOKEN = "<different-operator-password>"
python -m uvicorn src.forecast_api.app:app --host 127.0.0.1 --port 8100
```

### Terminal 2 — Website backend

From this repository:

```powershell
.\.venv\Scripts\Activate.ps1
$env:GOVERNED_FORECAST_API_URL = "http://127.0.0.1:8100"
$env:GOVERNED_FORECAST_API_KEY = "<same-private-api-key>"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Terminal 3 — Dashboard frontend

From `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

If the host is intentionally exposed on the Mobis internal network, other authorized users may open the host's internal address from their own browsers.

## Monthly Update Forecast workflow

The normal operator workflow is browser-based:

```text
Upload 4 source workbooks
  -> Validate
  -> Run governed pipeline
  -> Review QA and Draft
  -> Approve
  -> Dashboard + Sponsor XLSX update together
```

Required source roles:

1. CapStone / PIO source workbook
2. HMA plan workbook
3. GMA plan workbook
4. Kia plan workbook

The operator enters the password configured in the forecasting service's `FORECAST_UPDATE_TOKEN`.

A validation, pipeline, or QA failure leaves the previous Approved Run unchanged.

Approval is the only step that switches the Dashboard and Sponsor workbook to the new immutable run.

## Official Forecast behavior

### Executive Overview

Shows current landing / nowcast, next-month outlook, brand contribution, cutoff, approved-run metadata, and performance context.

### Model & PLC Planning

Uses one month selector across completed Actual and planning months.

- completed months are labeled `Actual`;
- the current planning month is labeled `Original Forecast` at lower-level Model/PLC grain;
- later months are labeled `Forecast`;
- Kia Fleet is never manufactured into a vehicle-model allocation when a governed model allocation is unavailable;
- completed Actual detail remains observed all-in PIO actual and does not claim a row-level Fleet/dealer split.

### Top Movers

The page supports three comparison types:

- completed Actual -> completed Actual;
- latest completed Actual -> current-month Original Forecast bridge;
- adjacent Forecast-month movement.

Forecast-to-Forecast rankings come from the governed `/top-movers` API. Completed-Actual and Actual-to-Plan comparisons are calculated only from approved governed Historical Reporting and PLC Planning records from the same run.

The Actual-to-Plan bridge compares all-in Brand + PLC values. Regular and Kia Fleet planning components are combined first because completed Actual does not assert a row-level Fleet/dealer split.

### Output Center

Provides the exact Sponsor XLSX from the current Approved Run through the website proxy. The website does not create another Official workbook.

## Security and configuration

The two deployment credentials have different purposes:

- `FORECAST_API_KEY`: service-to-service access to approved Forecast API data;
- `FORECAST_UPDATE_TOKEN`: operator access for Upload / Run / Approve.

The website uses:

- `GOVERNED_FORECAST_API_URL`
- `GOVERNED_FORECAST_API_KEY`

`GOVERNED_FORECAST_API_KEY` must match the forecasting backend's `FORECAST_API_KEY`.

Real values belong only in runtime environment variables or private local configuration. They must never appear in source code, URLs, screenshots, or Git commits.

## Validation

Focused website proxy tests:

```powershell
python -m pytest -q tests/test_governed_forecast_proxy.py
```

Official Forecast frontend tests:

```powershell
cd frontend
npm run test:official-forecast
```

Production build:

```powershell
npm run build
```

## Repository boundaries

This public repository must not contain:

- company raw Excel files;
- processed proprietary data;
- approved-run bundles;
- Sponsor workbooks;
- real API keys or operator tokens;
- `.env` files containing secrets;
- private sponsor presentations or screenshots.

The `.gitignore` intentionally excludes local secrets, runtime data, build outputs, and private reference material.

## Project documentation

- [`DEPLOYMENT.md`](DEPLOYMENT.md): single-host internal deployment, startup, monthly operation, and demo guidance;
- [`docs/INTEGRATION_STATUS.md`](docs/INTEGRATION_STATUS.md): current implemented system status and validation summary;
- [`docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md`](docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md): product and governance specification;
- [`docs/DASHBOARD_IMPLEMENTATION_TIPS.md`](docs/DASHBOARD_IMPLEMENTATION_TIPS.md): implementation guidance for future refinements;
- [`AGENTS.md`](AGENTS.md): repository boundaries and safety rules.

## Capstone handoff

Recommended handoff package:

1. this public Dashboard repository;
2. the private forecasting repository shared with designated Mobis technical owners;
3. a fixed capstone release tag on both repositories;
4. the current validated Sponsor workbook through an approved private channel;
5. this deployment and monthly-operation documentation.

No public hosting purchase is required for the reference handoff. Long-term enterprise hosting, identity, backups, monitoring, and retention remain Mobis IT deployment decisions.
