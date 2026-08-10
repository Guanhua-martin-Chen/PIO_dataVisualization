# Local Delivery and Demo Guide

## Architecture

The system keeps the web repository and governed forecasting repository
independent:

```text
Browser :3000
  -> Website FastAPI proxy :8000
     -> Governed Forecast API :8100
        -> immutable approved runs and exact Sponsor XLSX
        -> protected Update Forecast orchestration
```

The browser never calls the governed API directly and never receives its API
key. The website does not fit models, parse the Sponsor workbook, or calculate
Official totals, Expected Range, or Top Movers.

## Prerequisites

- Python and Node.js versions supported by the two repositories
- the private governed forecasting repository with its ignored runtime data
- four current source-role workbooks for an update
- secrets copied from `.env.example` into a local `.env` or shell environment

## Start the three local services

From the forecasting repository:

```powershell
python -m pip install -r requirements-update.txt
$env:FORECAST_API_KEY = "replace-with-a-local-api-key"
$env:FORECAST_UPDATE_TOKEN = "replace-with-a-random-operator-token"
python -m uvicorn src.forecast_api.app:app --host 127.0.0.1 --port 8100
```

From this repository:

```powershell
$env:GOVERNED_FORECAST_API_URL = "http://127.0.0.1:8100"
$env:GOVERNED_FORECAST_API_KEY = "replace-with-the-same-api-key"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

From `frontend/`:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The operator enters the access code configured in
`FORECAST_UPDATE_TOKEN` on the protected Update Forecast page. It is remembered
only for that browser tab/session and forwarded through the website proxy.

## Monthly update

1. Upload one workbook for each required role. Filenames may change.
2. Pass the governed sheet, field, source-role, and month validation.
3. Run the existing pipeline asynchronously. The current Approved Run remains
   visible throughout processing.
4. Review QA, reconciliation, cutoff, and Draft Run summary.
5. Approve only a passing Draft. Approval publishes one immutable run, switches
   `latest`, and updates the Dashboard and Sponsor XLSX together.

Required workbook structures are owned by the forecasting repository and are
validated there. The public website deliberately does not duplicate those
parsers or schemas.

## Temporary demo link

Create a free ngrok account, install the Windows agent from the
[official ngrok download page](https://ngrok.com/download/windows), and add the
account authtoken once:

```powershell
ngrok config add-authtoken "<YOUR_AUTHTOKEN>"
```

After all three local services are healthy, expose only the Next.js port:

```powershell
ngrok http 3000
```

Share the generated HTTPS URL. The link works only while this computer, all
three services, and ngrok remain running. Treat it as a demo, not permanent
hosting. Never put API keys or the operator token in the URL or repository.

## Handoff

Deliver both repository URLs plus their fixed release tags and documentation.
Mobis can deploy the two services in its own approved environment. Permanent
hosting, enterprise identity, and infrastructure integration are deployment
decisions outside this student-capstone reference implementation.
