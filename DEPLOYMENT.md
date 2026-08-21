# Mobis Reference Deployment and Monthly Operation Guide

## Recommended deployment

The capstone reference deployment is intentionally simple:

```text
Mobis users (Windows or Mac browser)
            |
      internal network
            |
            v
One Mobis host machine
  Dashboard / Next.js        :3000
  Website FastAPI proxy      :8000
  Governed Forecast API      :8100
  Forecast pipeline
  Microsoft Excel
```

A public domain, paid cloud server, Docker cluster, or other public hosting purchase is **not required** for the capstone handoff.

A **Windows host with desktop Microsoft Excel is recommended** for the complete governed Update Forecast workflow because the final Sponsor workbook formula-cache refresh uses Excel automation. Client users may open the Dashboard from Windows or macOS using a modern browser.

Mobis IT may later deploy the same two repositories into a managed internal server, VM, cloud platform, or enterprise identity environment.

## Two repositories

### Forecasting system of record — private

`Guanhua-martin-Chen/pio-accessories-forecasting-optimization`

Contains:

- source validation;
- forecasting pipeline;
- model / business-rule registries;
- QA and reconciliation;
- Draft / Approve workflow;
- immutable Approved Runs;
- Forecast API;
- Sponsor XLSX.

Designated Mobis technical owners need collaborator access to clone this private repository.

### Dashboard — public

`Guanhua-martin-Chen/PIO_dataVisualization`

Contains:

- Official Forecast Dashboard;
- Website FastAPI proxy;
- Update Forecast UI;
- Output Center;
- exploratory Data Workspace.

Read-only clone access does not require a GitHub invitation.

## First-time installation

### Forecasting repository

```powershell
cd pio-accessories-forecasting-optimization
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-update.txt
```

### Dashboard repository

```powershell
cd PIO_dataVisualization
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then install and build the frontend:

```powershell
cd frontend
npm install
npm run build
```

`npm run dev` is for development. The shared internal reference deployment should run the built frontend with `npm run start`.

## Configure the two deployment credentials

Choose two different private values on the host machine.

### Credential 1 — Forecast API key

Forecast backend:

```powershell
$env:FORECAST_API_KEY = "<private-api-key>"
```

Website backend:

```powershell
$env:GOVERNED_FORECAST_API_KEY = "<same-private-api-key>"
```

These two values **must match**.

### Credential 2 — Update Forecast operator password

Forecast backend:

```powershell
$env:FORECAST_UPDATE_TOKEN = "<different-operator-password>"
```

The operator enters this value on the Dashboard's **Update Forecast** page.

Both credentials may be changed later without modifying source code. Update the environment variables and restart the affected services. Changing credentials on a Mobis installation does not change another local installation.

For the Mobis installation, use host-specific credentials rather than reusing student/demo values. Mobis may choose the values directly, or initial values may be shared separately through a private handoff channel and rotated later.

Never commit real credentials to GitHub.

## Start the system

Open three terminals on the host machine.

### Terminal 1 — Governed Forecast API

From the forecasting repository:

```powershell
.\.venv\Scripts\Activate.ps1
$env:FORECAST_API_KEY = "<private-api-key>"
$env:FORECAST_UPDATE_TOKEN = "<different-operator-password>"
python -m uvicorn src.forecast_api.app:app --host 127.0.0.1 --port 8100
```

### Terminal 2 — Website FastAPI proxy

From the Dashboard repository:

```powershell
.\.venv\Scripts\Activate.ps1
$env:GOVERNED_FORECAST_API_URL = "http://127.0.0.1:8100"
$env:GOVERNED_FORECAST_API_KEY = "<same-private-api-key>"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Terminal 3 — Dashboard frontend

From `PIO_dataVisualization/frontend`:

```powershell
npm run start -- --hostname 0.0.0.0 --port 3000
```

Open on the host machine:

```text
http://127.0.0.1:3000
```

Authorized users on the same approved internal network may open:

```text
http://<host-internal-ip>:3000
```

Only the Dashboard needs to be exposed to authorized internal users. The Website backend and Forecast API can remain bound to loopback (`127.0.0.1`) on the same host.

If the host firewall blocks port 3000, Mobis IT must allow the Dashboard port on the approved internal network before other client devices can connect.

## Monthly Update Forecast

Normal operator workflow:

1. Open the Dashboard.
2. Go to **Update Forecast**.
3. Enter the `FORECAST_UPDATE_TOKEN` operator password.
4. Upload one workbook for each role:
   - CapStone / PIO
   - HMA plan
   - GMA plan
   - Kia plan
5. Click **Upload and validate**.
6. Resolve any workbook validation failures.
7. Run the governed pipeline.
8. Wait for QA and Draft generation.
9. Review cutoff, forecast window, registry version, reconciliation, and release QA.
10. Approve only a passing Draft.
11. The Approved Run, Dashboard, and Sponsor XLSX update together.

Validation, pipeline, or QA failures leave the previous Approved Run live.

## Dashboard pages used after approval

Recommended review flow:

```text
Executive Overview
  -> Brand Performance
  -> Model & PLC Planning
  -> Top Movers
  -> Governance & QA
  -> Output Center
```

The **Output Center** downloads the exact Sponsor workbook from the current Approved Run.

## Temporary external demo

ngrok may be used for a temporary presentation or reviewer demo after all three services are running.

Example:

```powershell
ngrok http 3000
```

Share only the generated HTTPS Dashboard URL.

Do not put API keys or the operator password in the URL.

The tunnel stops when ngrok or the host machine stops. Treat it as a temporary demo mechanism, **not permanent hosting**.

## Troubleshooting

### Dashboard says the Forecast service is unauthorized

Confirm:

```text
FORECAST_API_KEY
=
GOVERNED_FORECAST_API_KEY
```

Then restart the Forecast API and Website backend.

### Update Forecast says the operator access code is invalid

Confirm the value entered in the browser matches `FORECAST_UPDATE_TOKEN` on the Forecast backend, then restart the Forecast API if the environment variable was changed.

### Dashboard cannot reach the Forecast API

Confirm:

```text
GOVERNED_FORECAST_API_URL=http://127.0.0.1:8100
```

and confirm the :8100 service is running.

### Another device cannot open the Dashboard

Confirm the frontend is running with `--hostname 0.0.0.0`, use the host's internal IP rather than `127.0.0.1`, and confirm the host firewall permits port 3000 on the approved internal network.

### Sponsor workbook formula-cache release fails

The validated reference workflow expects a Windows host with desktop Microsoft Excel. Ensure Excel is installed and the workbook is not left open by another process.

### `npm run build` behaves unexpectedly while `npm run dev` is running

Stop the development server first. If necessary, remove `frontend/.next` and run the build again.

## Validation commands

Website proxy:

```powershell
python -m pytest -q tests/test_governed_forecast_proxy.py
```

Frontend:

```powershell
cd frontend
npm run test:official-forecast
npm run build
```

GitHub Actions repeats the website proxy test, Official Forecast frontend tests, and production build for every push and pull request. It does not deploy the application or use deployment credentials.

Forecasting repository:

```powershell
python -m pytest -q tests --basetemp=.tmp_pytest -p no:cacheprovider
```

## Handoff boundary

This capstone delivers a deployable reference application and governed forecast workflow. Mobis does not need to purchase public hosting to use the reference deployment.

Long-term decisions such as:

- enterprise hosting;
- auto-start services;
- SSO / role-based access;
- corporate secret management;
- HTTPS / internal DNS;
- backups;
- monitoring;
- retention;

may be implemented later according to Mobis IT standards.
