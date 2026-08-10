# Dashboard Implementation Tips

## Purpose

Use this document when refining the Official Forecast dashboard. It translates
the governed Forecast API contract and the seven-sheet Sponsor workbook into
practical UI guidance. It is not a new data contract and does not authorize the
website to calculate a second version of the forecast.

The Official Forecast pages and server-side API proxy already exist. Improve
them incrementally; do not rebuild the website framework or move forecasting
logic into this repository.

## 1. Preserve the product split

Keep two visibly separate areas:

- **Official Forecast**: read-only results from one approved Forecast API run.
- **Data Workspace**: exploratory upload, Raw Data EDA, tables, pivots, and CSV
  export.

An upload to Data Workspace must never update the Official Forecast label,
approved run, registry, or Sponsor workbook. Legacy website forecasting tools
may remain available only under `Legacy / Experimental` and `Not Official
Forecast` labels.

## 2. Use the workbook as an information hierarchy, not a web layout

The seven-sheet workbook is a strong audit and offline-delivery artifact, but
its wide tables should not be copied directly into the website.

| Workbook sheet | Best web treatment |
|---|---|
| `Executive_Summary` | Large decision KPIs, short automated BLUF, three-brand contribution, compact run status |
| `Revenue_Forecast` | Current-month bridge, six-month revenue trend with uncertainty, brand table, PNVW cross-check status |
| `Quantity_Forecast` | Total quantity bridge, brand/model detail, reconciliation review badges |
| `Part_Planning` | Filtered PLC rankings and drilldown; never render the full planning table on the landing page |
| `Wholesale_Drivers` | Plan-versus-fallback disclosure and a separate Kia Fleet panel |
| `Model_Performance` | Selected-method cards, H1/H2/H3 evidence, expandable candidate detail |
| `QA_Assumptions` | Release-health summary, expandable checks, definitions, assumptions, and limitations |

The workbook contains thousands of PLC planning records and dense governance
text. The web advantage should be progressive disclosure: summary first,
details only after the user selects a month, brand, model, or PLC.

## 3. Executive Overview: answer the decision in under one minute

Above the fold, prioritize:

1. current-month `actual` or `nowcast` landing;
2. pre-month forecast and dollar/percent movement;
3. expected low/base/high range, when supplied by the API;
4. next-month revenue and quantity forecast;
5. actual-data cutoff and period status;
6. H1 WAPE and confidence;
7. HMA, GMA, and KUS contribution.

Recommended layout:

- one dominant landing card;
- three or four smaller supporting KPI cards;
- one short BLUF block;
- one compact brand contribution chart;
- one slim approved-run strip;
- methodology and detailed metadata below the fold.

Do not turn every metadata field into a KPI. Run ID, registry version, schema,
source commit, generated time, and published time should remain accessible but
visually secondary.

The automated BLUF may describe facts such as direction, magnitude, largest
brand contribution, range, cutoff, and confidence. It must not invent causes.
Factory shutdowns, supply issues, launches, and management explanations belong
in a separately labeled `Business Note`.

## 4. Revenue view

Use three layers:

### Current-month landing

Show pre-month forecast, MTD actual when available, MTD-based projection,
current nowcast, interval, and change. A partial month must say `Nowcast as of
<cutoff>`; never label it final actual.

### Forecast trend

Use one line for the official total and a light confidence band. Allow HMA,
GMA, and KUS to be toggled on or shown as small multiples. Visually distinguish
Months 1-3 as `Primary` and Months 4-6 as `Exploratory`.

The independently modeled total is a benchmark only. If shown, use a dashed
line named `Independent benchmark`; never present it as another official total
or rescale brands to it.

### PNVW cross-check

Treat PNVW variance as an informational cross-check, not a calculation error
and not a replacement forecast. Show the API-supplied status and explanation.
Do not let a reference PNVW overwrite official revenue.

## 5. Quantity view

Lead with total accessory quantity and the reconciliation bridge:

`raw model signal -> regular total anchor -> reconciliation -> Kia Fleet -> final total`

Keep formulas in an expandable explanation. The default view should show the
business result, reconciliation status, and any review flag.

At model level, clearly label quantity as **accessory units**, not vehicles.
Display `accessory_units_per_wholesale_vehicle` as `units / Wholesale vehicle`,
not as a percentage, attach rate, penetration, or installed-vehicle rate. The
value may legitimately exceed 1.

Review badges are informational. `Review` or `High Review` does not mean the
forecast failed, and the UI must not alter the API value in response.

## 6. PLC Planning view

Default to `Brand + PLC`. Make `Brand + Model + PLC` a secondary drilldown
because it is more detailed and less certain.

Recommended controls:

- forecast month;
- Primary versus Exploratory horizon badge;
- brand;
- planning level;
- normalized model, enabled only for the model drilldown;
- regular versus Kia Fleet component;
- search by PLC;
- sort by revenue, quantity, or absolute change when a valid comparison exists.

Recommended visual order:

1. total reconciled PLC revenue and quantity for the current filters;
2. top PLC revenue or quantity horizontal bars;
3. growing/declining movers only when governed comparison fields exist;
4. paginated detail table;
5. confidence, method, and reconciliation explanation.

Important controls:

- Do not combine `Brand + PLC` and `Brand + Model + PLC` rows in one total;
  they are two views of the same hierarchy.
- Do not expose exact `PIS_PNO` or Part Description as an Official Forecast
  level.
- `PLC units per Wholesale vehicle` is an average accessory-unit count and may
  exceed 1. Never format it as a percentage.
- PLC revenue is a reconciled allocation of official brand revenue, not an
  independently selected lower-level revenue forecast.
- Load PLC data only on the PLC page, memoize filter results, and paginate the
  table. If future server-side filtering is needed, change the versioned API
  contract deliberately rather than inventing an ungoverned endpoint.

## 7. Kia Fleet presentation

Keep `kia_fleet_cfm_adjustment` visually separate from `regular` at every
relevant level. A small outlined Fleet callout, separate table row, or separate
stack segment is preferable to silently folding it into regular values.

Rules:

- add the Fleet component exactly once;
- do not show regular PNVW on Fleet rows;
- use Fleet-specific units/revenue-per-Fleet-vehicle fields when supplied;
- do not use `HBF14AC000`, Part Description, or text similarity as a Fleet
  identifier;
- show lower confidence and limited-history context without implying the rule
  is invalid.

## 8. Wholesale Drivers view

The purpose is disclosure, not a second forecast page. Show:

- Wholesale used by the official forecast;
- sponsor-plan value;
- internal fallback value;
- source/status such as Sponsor Plan, Internal Fallback, or Unavailable;
- fallback model count or affected models;
- Kia Fleet vehicle volume in its own section.

Use clear source badges. An explicit sponsor zero is different from missing or
unavailable data and must remain zero. Do not reinterpret negative or missing
source values in the browser.

## 9. Model Performance and Governance

The default view should show:

- one frozen selected revenue method for each brand;
- H1, H2, H3, and combined WAPE with fold counts and coverage;
- quantity anchor and allocation approach;
- confidence hierarchy;
- approved-run and release-QA status.

H1 is the primary next-month metric. H2-H3 are stability guardrails. Keep full
candidate leaderboards, formulas, and selection rationale inside expandable
sections or a separate detail table.

The official total is the exact sum of the three governed brand forecasts.
Keep the independent aggregate benchmark clearly separated.

## 10. Top Movers behavior

Use `/api/v1/top-movers` directly. Preserve the comparison and mover order
returned by the Forecast API; do not recalculate or sort movers in React.
Display at most the rows returned by each `upside` and `downside` array and do
not add zero-change rows to reach five.

Show dollar change as the ranking result and percentage change only as context.
When comparison revenue is nonpositive, display the API's unavailable
percentage state. Do not add `Strength`, `Watch`, `Alert`, anomaly, severity,
or materiality labels: schema 1.1.0 applies no thresholds or classifications.
Explain that this is adjacent forecast-month movement rather than a same-target
revision, actual/nowcast change, or causal driver analysis. Keep the separate
Kia Fleet component distinct and count it once.

## 11. Visual language

- Use navy/blue for hierarchy and neutral information.
- Reserve green for validated/pass states, amber for review, and red for real
  exceptions or material divergence.
- Do not use color alone; pair it with text, icon, or pattern.
- Forecast moving upward is not automatically good, and downward is not
  automatically bad. Prefer `Above pre-month` and `Below pre-month` wording.
- Keep chart titles explicit about metric, unit, month, and period type.
- Use compact values on cards and axes, with exact values in tooltips/tables.
- Currency: compact `$12.3M` on cards, exact dollars in detail.
- Quantity: whole accessory units with thousands separators.
- PNVW: dollars per regular non-Fleet Wholesale vehicle.
- Unit ratios: decimal `units / Wholesale vehicle`, never percent.
- WAPE, Bias percentage, MoM, and YoY: percent with consistent precision.
- Use horizontal bars for long PLC/model names and diverging bars for signed
  changes.
- Keep visible tables narrow; move lower-priority columns into an expandable
  row or details drawer before relying on horizontal scroll.

## 12. Interaction, responsiveness, and accessibility

- Persist month and brand selections across Official Forecast pages when
  practical.
- Use URL query parameters for shareable filtered views, but never place
  secrets or proprietary payloads in the URL.
- Use skeletons only while loading; use explicit messages for no approved run,
  timeout, unauthorized, unsupported schema, stale run, empty endpoint, and
  partial data.
- Never fall back to legacy forecast values while retaining the `Official`
  label.
- Keep keyboard focus visible and controls keyboard accessible.
- Provide text equivalents for chart insights and meaningful table headers.
- On smaller screens, stack KPIs and preserve the landing/period/cutoff first;
  technical tables may scroll within their own container.

## 13. Code-organization tips for the current implementation

The Official Forecast feature already separates API access, contracts,
navigation, overview, and section rendering. Preserve that boundary.

Before adding many more charts or filters, split the large section renderer
into focused views such as:

```text
features/official-forecast/
  api.ts
  contract.ts
  components/
    MetaStrip.tsx
    MetricCard.tsx
    PeriodBadge.tsx
    EmptyState.tsx
  views/
    BrandDriversView.tsx
    RevenueView.tsx
    QuantityView.tsx
    PlcPlanningView.tsx
    GovernanceView.tsx
    TopMoversView.tsx
    OutputView.tsx
```

Use small data-to-view-model functions that are easy to test. Formatting and
contract-safe display aggregation are allowed; model fitting, registry choice,
hierarchy reconstruction, Fleet inference, and competing workbook generation
are not.

## 14. Public-repository safety

This repository is public. Do not commit:

- raw or processed company data;
- approved-run bundles or Sponsor workbooks;
- private PowerPoint files or screenshots;
- real API keys, private URLs, or `.env` files;
- copied forecast values or local artifact paths in documentation or tests.

Use synthetic fixtures that preserve the API shape and business semantics.
Keep runtime secrets server-side.

## 15. Practical refinement order

1. Keep the existing API proxy and Official/Data Workspace separation stable.
2. Refine the Executive Overview hierarchy and labels.
3. Add a restrained revenue trend/range chart and quantity bridge.
4. Improve PLC filters, lazy loading, pagination, and confidence cues.
5. Improve Wholesale source disclosure and Fleet separation.
6. Make Governance/QA easier to scan with expandable detail.
7. Keep Top Movers faithful to API ranking and comparison context.
8. Add automated cross-repository reconciliation tests.
9. Finish responsive, keyboard, contrast, security, and deployment-readiness
   checks.

## 16. Acceptance checklist

- [ ] Every Official number belongs to one approved run and one schema version.
- [ ] Actual, nowcast, and forecast labels match `period_type`.
- [ ] Months 1-3 and Months 4-6 have visibly different confidence treatment.
- [ ] Official total equals the API total and governed brand sum.
- [ ] Kia Fleet is separate and added exactly once.
- [ ] Regular PNVW excludes Fleet.
- [ ] Quantity and PLC ratios are labeled as average units, not percentages.
- [ ] Brand + PLC and Brand + Model + PLC are not double-counted.
- [ ] No exact part number or Part Description appears as Official planning.
- [ ] Review flags do not overwrite forecast values.
- [ ] Missing fields display honestly instead of being inferred.
- [ ] The Official workbook download is the API-proxied approved artifact.
- [ ] Data Workspace uploads cannot replace an approved run.
- [ ] Loading, empty, error, stale, and unsupported-schema states are clear.
- [ ] No secrets or proprietary artifacts are committed.
- [ ] Backend tests, frontend build, responsive checks, and accessibility checks
      pass before release.
