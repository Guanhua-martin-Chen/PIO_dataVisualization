# Forecast API and Dashboard Integration Status

Last updated: 2026-08-04

## Repository setup

- Website repository: `Guanhua-martin-Chen/PIO_dataVisualization`
- `origin`: the user's fork
- `upstream`: `Noah-wang/PIO_dataVisualization`
- Current website baseline: `b3cbfec`
- Current branch at handoff: `main`

## Governed forecasting backend

- Repository: `Guanhua-martin-Chen/pio-accessories-forecasting-optimization`
- Read-only approved-run Forecast API merged into `main`
- API merge commit: `f1f3133`
- API schema version: `1.0.0`
- Approved-run bundles and Sponsor workbooks remain private and git-ignored
- The API serves sanitized JSON plus the exact hash-verified seven-sheet
  Sponsor workbook from the same approved run

Implemented API surfaces:

- health;
- latest approved run metadata;
- executive summary;
- revenue;
- quantity;
- PLC planning;
- Wholesale drivers;
- model performance;
- watchlist contract;
- QA;
- Sponsor workbook download.

Validated before this handoff:

- API-focused tests passed;
- full forecasting-repository tests passed;
- live Uvicorn smoke test passed;
- API-key rejection/acceptance behavior passed;
- downloaded Sponsor workbook hash matched the approved artifact.

## Current website observation

The upstream website has changed materially and already contains a substantial
internal “governed Forecast Center,” Output Center, model comparison, upload,
EDA, and export implementation. The latest code must be audited directly.

Current README/code references indicate possible conflicts with the official
Forecast API contract, including internal model selection, exact `PIS_PNO`
planning, generic `-1 -> 0` treatment, website-owned forecast generation, and a
separate SOP workbook. Treat these as audit findings to verify, not as a license
to delete code without dependency analysis.

## Local-only visual reference

If present, use:

`private_reference_templates/Executive_Summary.pptx`

The directory is ignored by Git because the fork is public. The presentation
is for local visual and information-hierarchy reference only. Do not commit,
redistribute, quote proprietary content, or copy manual conclusions.

The current PowerPoint contains an embedded chart structure that may not import
cleanly through every programmatic PPTX parser. Use a read-only PowerPoint view
when necessary; do not rewrite or resave the source merely to make a tool accept
it.

## Not yet implemented

- website server-side Forecast API proxy;
- governed API environment configuration in this repository;
- Official Executive Overview sourced from the API;
- API-backed brand, model, PLC, methodology, QA, and workbook-download pages;
- legacy/experimental separation in final navigation;
- cross-system integration tests;
- protected upload -> run -> QA -> approval orchestration;
- private Sponsor deployment.

## Immediate next task

Perform a read-only architecture audit. Do not modify application code yet.

The audit should deliver:

1. Current request/data flow for upload, EDA, Forecast Center, Output Center,
   and exports.
2. A file-level map of internal forecasting/model-selection behavior.
3. Reusable UI/backend components.
4. Conflicts with `docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md` and the current
   Forecast API contract.
5. Proposed proxy routes, environment variables, response adapters, frontend
   types, and endpoint-to-page mapping.
6. Exact files proposed for the first Executive Overview end-to-end slice.
7. Privacy, public-repository, performance, and deployment risks.
8. Relevant backend tests and frontend build commands.

Wait for user confirmation after presenting the audit and before editing
application files.

## Opening prompt for a new Codex task

```text
Read AGENTS.md, README.md, docs/GOVERNED_FORECAST_DASHBOARD_SPEC.md, and
docs/INTEGRATION_STATUS.md completely. Also read the current Forecast API
contract from the sibling forecasting repository. Run git status -sb,
git log -5 --oneline, and git remote -v.

Perform only the read-only architecture audit described in INTEGRATION_STATUS.
Use the current code as evidence, identify what can be retained and what
conflicts with the Official Forecast API boundary, and list the exact proposed
files and implementation phases. Do not modify files until I confirm the audit.
```
