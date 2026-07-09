# PIO Demand Intelligence Platform Kickoff Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the current workbook visualization app into a credible automotive parts planning product that progresses from data visibility to anomaly reasoning, demand forecasting, and finally a tool-driven AI analyst.

**Architecture:** Keep the product layered. First, stabilize the data workspace around reliable Excel ingestion, filtering, and server-side aggregation. Next, add analytics modules that compute anomaly and forecast outputs from trusted tables. Only after those tools are stable should the AI layer orchestrate them for natural-language analysis.

**Tech Stack:** FastAPI, Pandas, Uvicorn, Next.js, React, Ant Design, TypeScript, ECharts

---

## 1. Product Direction

### North Star

Build a high-end SaaS-style planning workspace for automotive PIO teams where a business user can:

1. Upload workbook exports.
2. Inspect and organize the data.
3. Understand what changed and why.
4. Forecast future sales demand.
5. Ask an AI analyst questions that are grounded in trusted tools.

### Product Stages

**V1: Data Workspace**
- Upload workbook and switch sheets.
- View data table, pivot table, and baseline visuals.
- Filter by date, brand, model, model year, part, and keyword.
- Export filtered slices.

**V2: Analysis and Anomaly**
- Explain notable up/down changes in part sales.
- Surface top abnormal parts or models.
- Show evidence behind each anomaly instead of just flags.

**V3: Forecast Center**
- Predict next month and next year demand.
- Expose MAE, Bias, WAPE, model choice, and confidence band.
- Compare forecast vs actual for backtesting.

**V4: AI Analyst**
- Accept natural-language questions.
- Call trusted tools for KPI, pivot, anomaly, and forecast outputs.
- Return answers with evidence and cited numbers instead of invented claims.

---

## 2. Recommended Starting Scope

Do **not** start with the AI agent. Start with the data and analytics spine.

### What to finish first

1. Make the current V1 workspace feel reliable.
2. Lock the business metric definitions.
3. Decide the primary forecasting grain.
4. Ship one anomaly workflow end-to-end.
5. Ship one forecast workflow end-to-end.

### What to postpone

- Memory
- RAG
- Autonomous planning agents
- Inventory simulation
- Penetration analysis against wholesale data

These are valuable later, but they depend on clean metric definitions and reliable analytical tools first.

---

## 3. Data Contract To Lock Now

Before adding more features, define the business columns and fallback logic clearly.

### Core fields

- `YYYYMM`: preferred monthly bucket when present
- `PIS_MST_IVC_DT`: transaction date fallback
- `Model`: vehicle model
- `PIS_PNO`: part number
- `Part Description`: part description
- `SumOfPIS_INST_QT`: installation quantity
- `SumOfPIS_CRP_CFM_PRI`: sales revenue

### Canonical business definitions

- **Sales quantity:** `SumOfPIS_INST_QT`
- **Sales revenue:** `SumOfPIS_CRP_CFM_PRI`
- **Demand grain recommendation for V3:** `part_number + month`
- **Secondary analysis grain:** `model + month`, then `part_number + model + month`

### Why this matters

If you do not lock the metric definitions now, anomaly and forecast results will drift across pages, and the future agent will give inconsistent answers.

---

## 4. Current Codebase Roles

Use the current codebase as the execution map.

### Backend

- `backend/app/main.py`
  - Upload API
  - Workbook status
  - Sheet fetch
  - Forecast API
  - Anomaly API
  - Pivot API
  - Export API

### Data / Analytics

- `pio_platform/data_loader.py`
  - Excel parsing
  - Header detection
  - Bundle construction

- `pio_platform/profiling.py`
  - KPI computation
  - Overview summaries
  - Auto insights

- `pio_platform/pivot.py`
  - Pivot logic
  - Wide-matrix handling
  - Filter-aware aggregation

- `pio_platform/forecasting.py`
  - Forecast model selection
  - Backtest diagnostics
  - Narrative generation
  - Anomaly reasoning

### Frontend

- `frontend/src/app/page.tsx`
  - Upload landing page

- `frontend/src/app/workspace/[id]/page.tsx`
  - Main workspace tabs
  - Filter controls
  - Forecast and anomaly views
  - Pivot and table rendering

- `frontend/src/app/globals.css`
  - Visual system
  - Layout polish

---

## 5. Two-Week Execution Plan

### Task 1: Stabilize the V1 workspace

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/workspace/[id]/page.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `backend/app/main.py`
- Modify: `pio_platform/pivot.py`

**Outcome:**
- Upload, worksheet switch, filters, pivot, and exports all behave consistently.
- The UI reads like a professional workspace, not a prototype.

**Checklist:**
1. Verify top filters control every downstream view.
2. Ensure pivot measure fallback stays synchronized with UI state.
3. Ensure workbook history and reload flow feel stable after server restart.
4. Reduce visual clutter and keep tabs grouped by business workflow.
5. Confirm the deployed app matches the local build.

### Task 2: Lock the metric and grain definitions

**Files:**
- Create: `docs/plans/2026-06-30-pio-demand-intelligence-kickoff.md`
- Modify: `README.md`
- Modify: `pio_platform/config.py`
- Modify: `pio_platform/data_loader.py`

**Outcome:**
- Everyone uses the same definitions for quantity, revenue, part, date, and forecast grain.

**Checklist:**
1. Document primary and fallback fields.
2. Document preferred monthly aggregation logic.
3. Add clear role-mapping notes in the repo docs.
4. Tighten auto-role detection where current files are ambiguous.

### Task 3: Ship V2 anomaly workflow

**Files:**
- Modify: `pio_platform/forecasting.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/app/workspace/[id]/page.tsx`

**Outcome:**
- A user can pick a part or segment and see where the sales pattern changed, with evidence.

**Minimum feature set:**
1. Detect unusually large month-over-month or year-over-year change.
2. Show contributing models or related segment changes.
3. Label possible reasons:
   - market growth/decline
   - model mix shift
   - low-base distortion
   - missing data / incomplete month risk
4. Expose a watchlist of parts needing review.

### Task 4: Ship V3 forecast workflow

**Files:**
- Modify: `pio_platform/forecasting.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/app/workspace/[id]/page.tsx`

**Outcome:**
- A planner can pick a part and view forecast, backtest quality, and confidence range.

**Minimum feature set:**
1. Select forecast target by part.
2. Show actual vs fitted history.
3. Show next-period forecast and confidence band.
4. Show model diagnostics:
   - MAE
   - Bias
   - WAPE
5. Add simple interpretation:
   - stable
   - seasonal
   - volatile
   - low confidence

### Task 5: Design the AI Analyst layer without overbuilding it

**Files:**
- Create later: `docs/plans/2026-06-30-ai-analyst-architecture.md`
- Future modify: `backend/app/agent.py`
- Future modify: `backend/app/tools.py`
- Future modify: `frontend/src/app/workspace/[id]/page.tsx`

**Outcome:**
- The agent becomes a thin orchestration layer over trusted analytical tools.

**Rules for V4:**
1. The agent must not compute business numbers from scratch in free text.
2. Every answer must come from tool calls.
3. Every answer should expose evidence:
   - filters used
   - metric used
   - time range used
   - output table or score used

---

## 6. Agent Architecture Recommendation

### Recommended approach

Use a **tool-driven analyst agent**, not a fully autonomous general agent.

### Tool groups

**Data tools**
- list sheets
- inspect schema
- fetch filtered table
- build pivot

**Analysis tools**
- calculate KPI
- run anomaly center
- explain latest change
- build watchlist

**Forecast tools**
- prepare history
- select best model
- produce forecast
- return diagnostics

### Future memory and RAG

Add memory and RAG only when you have stable reference material such as:

- metric glossary
- planning SOP
- business interpretation rules
- prior analyst notes
- inventory policy docs

Until then, memory and RAG will create complexity before they create value.

---

## 7. First Week Priority Order

If you are starting today, do these in order:

1. Run the live app with the real workbook and note the top 5 workflow pain points.
2. Confirm the business field definitions and primary forecast grain.
3. Finish V1 interaction polish so the data workspace is trustworthy.
4. Pick one anomaly story:
   - “Why did part X drop in May/June?”
5. Make that one story work end-to-end in the UI.

This gives you a real business narrative before you touch agent orchestration.

---

## 8. Success Criteria

### V1 success

- Business users can upload and inspect workbook data without engineering help.
- Filters, pivot, visuals, and exports match each other.
- The app feels stable enough to use in a real meeting.

### V2 success

- A user can identify abnormal movement and see a plausible explanation with evidence.

### V3 success

- A user can forecast at least one planning grain and understand forecast reliability.

### V4 success

- A user can ask a natural-language question and get a grounded answer with traceable numbers.

---

## 9. Immediate Next Actions

### Today

1. Open the deployed app: `https://pio.43-160-247-21.sslip.io`
2. Upload the workbook and walk the full flow.
3. Write down:
   - top 5 broken or weak experiences
   - final metric definitions
   - the first anomaly question you want the product to answer

### After that

Choose one of these as the next build target:

1. **V1 hardening first**: best if the current workspace still feels rough
2. **V2 anomaly first**: best if the workspace is already good enough and you want business value fast
3. **V3 forecast first**: best if your immediate need is planning accuracy over explanation

My recommendation is **V1 hardening first, then V2 anomaly, then V3 forecast, then V4 AI analyst**.
