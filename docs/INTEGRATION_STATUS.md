# Forecast API and Dashboard Integration Status

Last updated: 2026-08-16

## Repository setup

- Website repository: `Guanhua-martin-Chen/PIO_dataVisualization`
- `origin`: the user's fork
- `upstream`: `Noah-wang/PIO_dataVisualization`
- Integration baseline: `b3cbfec`
- Current implementation branch: `codex/governed-forecast-proxy`

## Governed forecasting backend

- Repository: `Guanhua-martin-Chen/pio-accessories-forecasting-optimization`
- Read-only approved-run Forecast API merged into `main`
- API history-extension commit: `4c91ebb`
- API schema version: `1.2.0`
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
- API-ranked Top Movers;
- QA;
- Sponsor workbook download.

Validated before this handoff:

- API-focused tests passed;
- full forecasting-repository tests passed;
- live Uvicorn smoke test passed;
- API-key rejection/acceptance behavior passed;
- downloaded Sponsor workbook hash matched the approved artifact.

## Website architecture disposition

The website-owned Forecast Center, model comparison, output generation, upload,
EDA, and export implementation remains available only inside the separate Data
Workspace. Forecast-generation surfaces are labeled `Legacy / Experimental`
and `Not Official Forecast`; they are not linked as Official Forecast outputs.

The Official Forecast area is read-only and consumes only the approved Forecast
API. It does not select models, forecast at exact `PIS_PNO`, recalculate official
totals, or generate a competing Sponsor workbook.

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

## Implemented in the current branch

- explicit website proxy routes under `/api/official-forecast/v1`;
- server-only Forecast API URL, key, timeout, and schema configuration;
- response-contract and schema-version validation with safe error mapping;
- fixed allowlist for the approved read-only API endpoints;
- exact Sponsor workbook streaming without exposing the governed API key;
- Official Executive Overview as the default website page;
- current landing, pre-month comparison, next-month plan, H1 WAPE, brand
  contribution, run metadata, release QA, and rules-based BLUF display;
- previous-completed-month Actual Revenue and API-published current-Nowcast
  versus previous-Actual comparison;
- a dynamic six-point Revenue window with the latest three Actual months,
  current Nowcast, and next two approved Forecast months;
- latest-three-completed-month regular non-Fleet PNVW by HMA, GMA, and KUS;
- visible `actual`/`nowcast`/`forecast` status from the API output;
- Data Workspace moved to `/data-workspace` and explicitly labeled as
  exploratory;
- loading, unavailable, unauthorized, no-approved-run, unsupported-schema,
  stale-window, and successful approved-run states;
- no fallback from a failed Official request to the website's internal
  forecast engine;
- five-item Official Forecast navigation: Overview, Forecasts, Drivers & PLC,
  Governance & QA, and Output Center, with focused second-level navigation;
- Forecasts contains only Revenue and Quantity; the redundant Brand Breakdown
  view redirects to Revenue because its charts and records already live on
  their metric-specific pages;
- reusable KPI, run-status, period-badge, empty-state, and ECharts components,
  with each Official area implemented as an independent view component;
- Brand-first Executive Overview with current Total, next-month Total, HMA,
  GMA, and KUS in one KPI row, and a directly labeled grouped Brand Revenue
  chart overlaid by the API-published Total line;
- a compact grouped-bar regular non-Fleet PNVW chart with a common zero-based
  axis, direct value labels, and published numerator/denominator tooltip detail;
  no annual composition is shown without a governed BP or Plan benchmark;
- a compact title area without a duplicate BLUF block, plus an Overview
  movement panel that merges the API's separately ranked direction lists into
  the five largest published absolute Revenue changes overall, without a
  direction quota, percentage ranking, recomputation, or padding;
- API-backed total, brand, model, Brand + PLC, and Brand + Model + PLC views;
- Fleet quantity displayed as a separate governed component and never added a
  second time by the website;
- registry, model-performance, reconciliation, coverage, and release-check
  evidence supplied directly by the API;
- API-ranked Top Movers, preserved without website-side calculation, sorting,
  padding, thresholds, or classifications;
- one-at-a-time tabbed previews for the seven API JSON outputs in Output Center,
  plus the exact approved Sponsor workbook download through the server-side
  proxy;
- website-owned forecast tools and generated files visibly isolated under
  `Legacy / Experimental` and `Not Official Forecast` labels.

Validated on 2026-08-07:

- 12 focused proxy/configuration/contract/download tests passed;
- 75 backend tests passed; one pre-existing test remains blocked because
  `docs/forecasting/MODEL_REGISTRY.md` is absent;
- all 7 Official Forecast view-model tests passed;
- Next.js production build passed;
- a real local approved run passed API -> website proxy -> Executive Overview
  smoke testing with matching run IDs, schema `1.2.0`, six ordered
  Actual/Nowcast/Forecast trend points, nine regular PNVW Actual records, and
  twelve API-published cumulative Revenue points;
- desktop, 820-pixel, and 390-pixel responsive browser checks passed with no
  page-level horizontal overflow or console errors;
- all seven additional Official Forecast views loaded successfully from the
  same approved run, and the Official Output Center exposed one API-proxied
  Sponsor-workbook download;
- revenue, quantity, PLC planning, Wholesale drivers, model performance, QA,
  and Top Movers proxy responses matched the same run and schema;
- the workbook downloaded through the website proxy matched the approved
  artifact SHA-256 hash.

Brand-first Overview refinement validated on 2026-08-09:

- all 9 Official Forecast view-model tests passed, including preservation of
  API-published Total Revenue without browser-side Brand summation, fixed
  HMA/GMA/KUS order, PNVW supporting values, and no-sort/no-pad Overview mover
  selection;
- all 12 focused proxy/configuration/contract/download tests passed;
- the Next.js production build passed type checking and static generation;
- the current approved schema `1.2.0` run rendered with styled assets after a
  clean development-server restart, with current Total/next Total/HMA/GMA/KUS
  in one KPI row, direct Brand and Total Revenue labels, Expected Range kept in
  the KPI/tooltip rather than plotted, a zero-based PNVW grouped-bar chart, and
  five API-ranked movers with published percentages;
- the 1280 x 720 Overview measured 1221 pixels tall with no page-level
  horizontal overflow, and all five primary navigation pages loaded without an
  error; Revenue, Quantity, PLC, Governance, and Output tabs rendered only one
  detailed table at a time where applicable.

Current approved-output limitations shown honestly by the UI:

- the Expected Range summary uses only API-published total bounds; if either
  bound is absent, the UI states that the range is unavailable and does not
  infer an interval;
- the Executive Summary does not currently supply a current-nowcast Kia Fleet
  revenue split, so that field is not calculated or inferred by the website;
- Top Movers compares adjacent forecast months within one approved run; it is
  not a same-target forecast revision, actual/nowcast change, alert, anomaly,
  materiality classification, or causal explanation.

## Forecast Update workflow implemented locally

The protected student-capstone orchestration is now implemented across the two
independent repositories:

- one operator token protects all update routes; enterprise identity remains a
  deployment extension;
- four governed source roles are uploaded through the website's server-side
  proxy and validated by the existing forecasting-repository readers;
- the current production pipeline runs in an isolated, git-ignored job
  workspace and continues to consume frozen governance artifacts;
- validation, job progress, QA/reconciliation, Draft review, and explicit
  approval are visible on `/official-forecast/update`;
- validation, pipeline, QA, and publication failures leave the previous
  approved run unchanged;
- only approval invokes the immutable approved-run publisher, switching the
  Forecast API, Dashboard, and exact Sponsor workbook together;
- synthetic end-to-end tests cover authorization, upload, validation, queued
  execution, QA failure, pipeline failure, Draft isolation, and approval;
- the Official Forecast API key remains server-side, and runtime uploads,
  approved bundles, company workbooks, and secrets remain outside Git.

Validated on 2026-08-10:

- 125 forecasting-repository tests passed, including the new workflow plus
  existing API contract, privacy, reconciliation, publisher, and Kia Fleet
  regression coverage;
- 13 website proxy tests and 14 Official Forecast view-model tests passed;
- TypeScript checking and the Next.js production build passed; Next.js also
  completed its configured lint/type validation stage;
- live local requests returned `401` without the update token and `200` through
  both the website proxy and governed API with the token;
- all five Official Forecast areas plus Update Forecast loaded at desktop size
  without page-level horizontal overflow;
- Overview and Update Forecast loaded at a 390-pixel viewport without
  page-level horizontal overflow.

## Remaining delivery work

- run the first operator acceptance update with a new real monthly source set
  when that governed data becomes available;
- create the final B release commits/tags and upstream pull request after visual
  confirmation;
- create a temporary ngrok demo link for reviewers;
- let Mobis choose permanent hosting, enterprise identity, infrastructure, and
  retention controls in its own environment.
