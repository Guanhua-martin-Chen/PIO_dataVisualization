# PIO Demand Intelligence Platform

**中文** | [English](#english-version)

> **汽车零部件需求规划团队的智能工作台** — 从原始 Excel 工作簿导出到结构化规划工作区，一步完成。

---

## 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [本地运行](#本地运行)
- [API 说明](#api-说明)
- [路线图](#路线图)

---

## 项目简介

PIO Demand Intelligence Platform（V1）是一个面向汽车零部件规划团队的 Web 工作台，取代了早期的 Streamlit MVP 原型。

V1 覆盖从 Excel 导入、可信 EDA 到分层预测和企业导出的完整主流程：**先建立可审计的数据与品牌口径，再生成可解释、可对账的 Revenue、PIO Quantity 和 Wholesale Forecast。**

平台已在当前参考工作簿的 **478,125 行 PIO 销售记录**上完成测试，所有表格浏览均采用服务端分页，不会将完整数据集加载进浏览器。

---

## 功能特性

### 📤 Excel 原生导入
- 支持 `.xlsx` 和 `.xls` 格式，无需预先整理源文件
- 自动检测表头行位置，兼容多层合并表头结构
- 多工作表切换，工作簿不落盘

### 📊 Overview（数据概览）
- **KPI 卡片**：总记录数、安装数量、销售金额、零件种类数
- **数据叙述**：自动生成数据集摘要（时间跨度、字段覆盖情况）
- **数据健康报告**：日期字段、数值字段、类别字段及高缺失列统计
- **自动洞察**：时间覆盖、Top 车型/零件收入等关键发现

### 📋 Data Table（数据表格）
- 服务端分页 + 排序，轻松处理 20 万行以上数据
- 多维度过滤：品牌、车型、年款、零件、日期区间、全文检索
- 列可见性控制，自定义工作视图
- 一键导出当前过滤切片为 CSV

### 🗂️ Field Classification（字段分类）
- 自动将字段归入六类业务组：时间、车辆、零件、数量、收入、其他
- 每个字段展示：检测角色、置信度（高/中/低）、类型、缺失率、唯一值数量、示例值

### 📈 Basic Insights（基础洞察）
- 月度安装量趋势折线图
- 月度收入面积图
- Top 10 车型收入排行柱状图
- Top 12 零件排行柱状图

### 🔀 Pivot Table（数据透视表）
- 把品牌 / 车型 / 车型年款 / 零件 / 月份 / 年份拖拽到「行」或「列」
- 度量可切换安装数量、销售金额、记录数；聚合支持求和 / 平均 / 计数
- 服务端聚合，沿用 Data Workspace 的全部过滤条件
- 自动带行 / 列 / 总计，可一键导出当前透视结果为 CSV

### 🔎 EDA Dashboard（探索性数据分析）
- **可信数据范围**：业务 EDA 与 Forecast Center 以 `PIO_Sales_Data` 和 `Vehicle_Wholesale_Data` 为事实来源；`Working_Days` 与 `PLC_Legend` 仅作为日历和分类参考，不把其他辅助工作表混入销量分析
- `Working_Days` 与 `PLC_Legend` 页面会明确显示 `reference sheet — excluded from governed EDA`，不会请求或生成 EDA dashboard
- **数据质量诊断**：检查关键字段缺失、负数量/收入、零安装量、单位收入极端值，以及零件号与描述的一对多差异
- **车型与品牌映射**：优先使用标准化车型名和 dealer-wholesale 精确映射，保留原始 `H` / `K` source code，同时生成独立的 `HMA` / `GMA` / `KUS` forecast anchor
- **生命周期审计**：显示车型首次/最后正销量月份、停产、当年无销量、reintroduced 和新车型证据；Excel 数值型 `-1` sentinel 在进入分析前统一转为 `0`
- **关系与趋势图**：展示月度 PIO Quantity、PIO Revenue、dealer Wholesale、PNVW、Top 车型和 Top 零件；`PNVW = PIO Revenue / dealer wholesale units`

### 🧱 月度事实表与三品牌 Anchor
- 事实表粒度为 `month × anchor brand × model × PLC × PIS_PNO`，覆盖 2023-01 至当前数据 cutoff
- 官方 anchor 为 `HMA`、`GMA`、`KUS`；不会再把 Hyundai 与 Genesis 合并成单一 `H`
- 当前业务口径下，三个 anchor 均使用 dealer / non-fleet wholesale；Fleet 不会加入 PIO Quantity、PIO Revenue 或 PNVW 分母
- 当前参考工作簿的 PIO 与 Wholesale cutoff 同步为 `2026-07-22`

### 📈 Forecast Center（分层预测）
- **统一信息架构**：Forecasting 固定为 `Forecast`、`Exceptions`、`Inventory Planning`、`Output Center`。Forecast 是默认且唯一正式预测入口；旧 Output/Detail/Leaderboard/Series Table/Interpretation/Signals 不再出现在正式路径
- **独立页面职责**：Exceptions 使用治理后的 `PIO_Sales_Data` 与所有兼容 Wholesale 表，当前标为 Experimental；Inventory Planning 独立请求 reconciled PIO Quantity 的 `Model × PLC` 需求预览，不覆盖 Forecast 结果，也不在缺少 PIS_PNO 库存输入时生成正式补货建议
- **PIO Revenue**：直接预测 `SumOfPIS_CRP_CFM_PRI` 的 accessory sales revenue；源数据没有成本或毛利字段，因此这里是收入预测，不是利润预测
- **PIO Quantity**：月度目标为 `SUM(SumOfPIS_INST_QT)`；该字段是 installed accessory quantity，不是 vehicle wholesale
- **Wholesale Quantity**：使用 dealer / non-fleet vehicle wholesale，可查看 `HMA/GMA/KUS → Model`；Wholesale 没有 PLC 维度
- **层级与对账**：Brand 是正式统计 anchor；Model 与 PLC 使用数量信号和 Expected Unit Revenue 分配，并在每个月严格满足 `Σ Model = Brand`、`Σ PLC = Model`
- **Expected Unit Revenue**：PIO revenue / installed accessory quantity。Model/PLC 优先使用最近 3 个完整月，再回退到自身历史或父级最近 6 个月；exact-part planning 明确使用最近 6 个完整月
- **PLC 与零件输出**：页面 PLC 视图显示历史收入最高的 Top 10，完整导出保留全部合格的 `Brand × Model × PLC`；`Part_Planning` 再分配到具体 `PIS_PNO`
- **停产与低销量分流**：当年已观察至少 6 个月后仍无正销量的车型按 inactive 处理并保持零预测；低销量/不足 6 个 active months 的序列不进入常规分配；新车型和当年仍有销量的 reintroduced 车型使用 recent run-rate proxy

### 🧮 模型、Working Days 与准确率
- `Auto` 会让合格的统计 baseline 与 OLS driver regression 比较独立验证 WAPE；`Baseline auto` 只比较统计 baseline；也可强制选择某个合格模型
- Revenue 另提供已验证的 `reference_portfolio`：HMA 使用优化 Holt-Winters、GMA 使用 Last-Month Revenue、KUS 使用 Working-Day-Adjusted Seasonal；它只适用于 Revenue Brand anchor，当前仍保留 `Auto` 为默认
- 候选模型包括 naive、mean、weighted moving average、trailing-12 mean、trend、seasonal naive/mean、additive ETS、Croston SBA；ETS 至少需要 24 个月，季节模型与 OLS 至少需要 18 个月
- Working Days 是工作簿给出的**整月业务工作日暴露量**，不是日期号或自然日数；OLS 将其作为标准化特征，其他 baseline/层级分配使用工作日比例调整
- 2026-07 显示为截至 7 月 22 日的 MTD actual 加剩余月份预测所组成的 full-month nowcast；2026-08 起才是纯 forecast
- 准确率只在 `month × official brand anchor` 上做独立 expanding-window holdout；Model、PLC 和具体零件目前是对账分配，不单独宣称模型准确率

### 📤 Output 与业务校验
- `Output Center` 集中提供当前 Forecast Center 视图 CSV 与 SOP Excel；主页面和预测控制卡不重复放置下载按钮，打开 Output Center 不会重新运行预测
- SOP Excel 包含 `Executive_Summary`、`Revenue_Forecast`、`Quantity_Forecast`、`Part_Planning`、`Wholesale_Drivers`、`Model_Performance` 和 `QA_Assumptions`
- 当前参考工作簿包含 21 个 PLC 且无 PLC 空值；21 类的 Quantity 与 Revenue 汇总分别精确对回全部 PIO Quantity 与 PIO Revenue
- 当前独立品牌 anchor 回测准确率为 Revenue `83.03%`、PIO Quantity `83.84%`、Wholesale Quantity `93.09%`；这些数字不是 Model/PLC 准确率，也未被包装成 95%
- 可运行 `python scripts/validate_anchor_policy.py <workbook.xlsx> --horizon 6` 重建 mapping、cutoff、lifecycle、accuracy 与 reconciliation 检查

---

## 技术栈

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 15.x | React 全栈框架 |
| React | 19.x | UI 框架 |
| Ant Design | 5.x | 企业级 UI 组件库 |
| ECharts + echarts-for-react | 5.x / 3.x | 数据可视化图表 |
| TypeScript | 5.x | 类型安全 |
| dayjs | — | 日期处理 |

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.116+ | 异步 REST API 框架 |
| Uvicorn | 0.35+ | ASGI 服务器 |
| Pandas | 3.x | 数据处理与分析 |
| openpyxl / xlrd | — | Excel 文件解析 |
| python-multipart | — | 文件上传支持 |

---

## 项目结构

```
.
├── backend/
│   └── app/
│       └── main.py          # FastAPI 路由：上传、工作区、分页、导出
│
├── frontend/
│   └── src/
│       └── app/
│           ├── page.tsx     # 主页面：上传区 + 工作区（所有 Tab）
│           ├── globals.css  # 全局样式与设计系统
│           └── layout.tsx   # 根布局
│
├── pio_platform/            # 可复用的核心数据处理库
│   ├── data_loader.py       # Excel 解析、表头检测、字段类型推断、角色识别
│   ├── profiling.py         # 列分析、KPI 计算、自动洞察生成
│   ├── config.py            # 字段角色匹配规则配置
│   ├── filters.py           # 数据过滤逻辑
│   ├── charts.py            # 图表数据构建
│   ├── fact_table.py        # HMA/GMA/KUS 月度事实表与 Wholesale/Working Days 关联
│   ├── model_entities.py    # 车型实体、生命周期与停产/新车型分流
│   ├── hierarchical_forecasting.py # 统计模型、OLS、Working Days、独立回测
│   ├── forecast_center.py   # Brand → Model → PLC 对账预测
│   ├── sop_workbook.py      # Executive Summary 与详细 SOP Excel
│   └── i18n.py              # 多语言支持
│
├── scripts/
│   └── validate_anchor_policy.py # 真实工作簿业务口径验证
│
├── requirements.txt         # Python 依赖
├── .gitignore
└── README.md
```

---

## 本地运行

> 需要：Python 3.11+，Node.js 18+

### 1. 启动后端 API

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端运行后可访问：`http://127.0.0.1:8000/docs`（Swagger 交互文档）

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开浏览器访问：[http://localhost:3000](http://localhost:3000)

### 环境变量（可选）

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

---

## API 说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/workbooks/upload` | 上传 Excel 文件，返回工作区完整数据 |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}` | 获取指定工作表的分页数据（支持过滤、排序） |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/monthly-facts` | 获取 HMA/GMA/KUS 月度事实表与覆盖率摘要 |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/forecast-center` | 获取 Revenue / PIO Quantity / Wholesale 的分层预测 |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/forecast-center/export.xlsx` | 导出 Executive Summary 与完整 Forecast SOP Excel |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/pivot` | 服务端透视聚合（rows / cols / measure / agg + 过滤条件） |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/export.csv` | 导出当前过滤切片为 CSV |

---

## 路线图

- [ ] **品牌准确率改进**：继续诊断 HMA Revenue / PIO Quantity 的结构变化；当前结果不能在没有独立回测证据时宣称 95%
- [ ] **Executive Summary PDF**：增加网站内预览和 PDF 导出；当前已完成的是 Executive Summary + 详细 Forecast Excel
- [ ] **Accessory 生命周期面板**：在 EDA 中单独标出长期停止销售的 `PIS_PNO`；当前 part planning 已通过 recent-6 和低销量门槛避免给长期无销量零件分配
- [ ] **HMA Fleet 情景**：如业务方确认 HMA 需要 wholesale + fleet，再作为显式可审计情景加入；当前正式口径仍为 dealer wholesale
- [ ] **库存建议**：基于对账后的 Quantity Forecast 生成补货与安全库存建议

---
---

# English Version

[中文](#pio-demand-intelligence-platform) | **English**

> **A planning workspace for automotive parts demand teams** — from raw Excel workbook exports to a structured, decision-ready workspace in one step.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Running Locally](#running-locally)
- [API Reference](#api-reference)
- [Roadmap](#roadmap)

---

## Overview

PIO Demand Intelligence Platform (V1) is a web workspace for automotive parts planning teams, replacing an earlier Streamlit MVP prototype.

V1 covers the primary workflow from Excel intake and governed EDA through hierarchical forecasting and enterprise export: **establish an auditable data/anchor policy first, then produce explainable and reconciled Revenue, PIO Quantity, and Wholesale forecasts.**

The platform has been tested against the current reference workbook's **478,125 PIO sales rows**. All table browsing is server-side paginated — the full dataset is never loaded into the browser.

---

## Features

### 📤 Excel-Native Intake
- Accepts `.xlsx` and `.xls` files without reshaping the source file first
- Auto-detects header row position, handles multi-row merged headers
- Multi-sheet switching; workbook bytes are held in memory, never written to disk

### 📊 Overview Tab
- **KPI cards**: Total records, installation quantity, sales revenue, distinct part count
- **Dataset narrative**: Auto-generated summary of time span and field coverage
- **Data health**: Date, numeric, and category field counts; high-missing column alerts
- **Auto insights**: Date coverage, top model/part by revenue, and more

### 📋 Data Table Tab
- Server-side pagination and sorting — handles 200k+ rows comfortably
- Multi-dimension filters: brand, model, model year, part, date range, full-text search
- Column visibility control for a custom working view
- One-click CSV export of the current filtered slice

### 🗂️ Field Classification Tab
- Automatically groups fields into six business categories: Time, Vehicle, Part, Quantity, Revenue, Other
- Per-field display: detected role, confidence (High / Medium / Low), type, missing %, unique count, sample values

### 📈 Basic Insights Tab
- Monthly installation quantity line chart
- Monthly revenue area chart
- Top 10 vehicle models by revenue (bar)
- Top 12 parts by revenue or quantity (bar)

### 🔀 Pivot Table Tab
- Drag brand / model / model year / part / month / year onto Rows or Columns
- Switch the measure between installation quantity, sales revenue, and record count; aggregate by sum / average / count
- Server-side aggregation that honors every Data Workspace filter
- Row, column, and grand totals included; export the current pivot to CSV in one click

### 🔎 EDA Dashboard
- **Governed source scope**: business EDA and Forecast Center use `PIO_Sales_Data` and `Vehicle_Wholesale_Data` as fact sources; `Working_Days` and `PLC_Legend` are calendar/classification references, so unrelated helper sheets are not mixed into sales analysis
- `Working_Days` and `PLC_Legend` show `reference sheet — excluded from governed EDA`; the client does not request or build an EDA dashboard for either reference sheet
- **Data-quality diagnostics**: checks required-field gaps, negative quantity/revenue, zero installation quantity, unit-revenue outliers, and one-to-many part-number/description mappings
- **Model and anchor mapping**: matches normalized model names to dealer wholesale, retains the original `H` / `K` source code, and assigns separate `HMA` / `GMA` / `KUS` forecast anchors
- **Lifecycle evidence**: shows first/last positive months, discontinued, no-current-year activity, reintroduced, and new-model evidence; numeric Excel `-1` sentinels are normalized to `0` before analysis
- **Relationships and trends**: monthly PIO Quantity, PIO Revenue, dealer Wholesale, PNVW, top models, and top parts; `PNVW = PIO Revenue / dealer wholesale units`

### 🧱 Monthly Fact Table and Three-Anchor Policy
- Fact grain is `month × anchor brand × model × PLC × PIS_PNO`, covering January 2023 through the current data cutoff
- Official anchors are `HMA`, `GMA`, and `KUS`; Hyundai and Genesis are no longer collapsed into one `H` forecast anchor
- Under the current business rule, all three anchors use dealer / non-fleet wholesale. Fleet is not added to PIO Quantity, PIO Revenue, or the PNVW denominator
- The current reference workbook has a synchronized PIO and Wholesale cutoff of `2026-07-22`

### 📈 Forecast Center
- **Single information architecture**: Forecasting is ordered as `Forecast`, `Exceptions`, `Inventory Planning`, and `Output Center`. Forecast is the default and only official forecast entry; legacy Output/Detail/Leaderboard/Series Table/Interpretation/Signals are hidden from the official path
- **Separate responsibilities**: Exceptions resolves governed `PIO_Sales_Data` plus every compatible Wholesale sheet and remains Experimental. Inventory Planning makes its own reconciled PIO Quantity `Model × PLC` request, never overwrites Forecast, and does not issue reorder recommendations without governed PIS_PNO inventory inputs
- **PIO Revenue** directly forecasts accessory sales revenue from `SumOfPIS_CRP_CFM_PRI`. The source has no cost or margin field, so this is revenue—not profit
- **PIO Quantity** uses monthly `SUM(SumOfPIS_INST_QT)`, meaning installed accessory units rather than vehicle wholesale
- **Wholesale Quantity** uses dealer / non-fleet vehicle wholesale and supports `HMA/GMA/KUS → Model`; it has no PLC dimension
- **Hierarchy and reconciliation**: Brand is the official statistical anchor. Model and PLC are allocated from quantity signals and Expected Unit Revenue, with monthly controls enforcing `Σ Model = Brand` and `Σ PLC = Model`
- **Expected Unit Revenue** is PIO revenue per installed accessory unit. Model/PLC uses the latest three complete months, then own history, then the parent's recent-six value; exact-part planning explicitly uses six complete months
- **PLC and part output**: the web PLC view shows the top 10 by historical revenue, while the detailed export retains all eligible `Brand × Model × PLC` rows and allocates them to exact `PIS_PNO` rows in `Part_Planning`
- **Lifecycle and volume routing**: after at least six months of the current year are observed, models with no positive current-year volume are inactive and remain zero; low-volume/short-history series are excluded from regular allocation; new and current-year-active reintroduced models use a recent run-rate proxy

### 🧮 Models, Working Days, and Accuracy
- `Auto` compares eligible statistical baselines with OLS driver regression on validation WAPE; `Baseline auto` restricts selection to statistical baselines; an eligible model may also be forced
- Revenue also exposes a validated `reference_portfolio`: optimized Holt-Winters for HMA, Last-Month Revenue for GMA, and Working-Day-Adjusted Seasonal for KUS. It is limited to Revenue Brand anchors, while `Auto` remains the default
- Candidates include naive, mean, weighted moving average, trailing-12 mean, trend, seasonal naive/mean, additive ETS, and Croston SBA. ETS needs at least 24 months; seasonal models and OLS need at least 18 months
- Working Days is the workbook's **full-month business-day exposure**, not the calendar day number. OLS learns it as a standardized feature; other baselines and allocations use working-day ratio adjustments
- July 2026 is a full-month nowcast composed of MTD actual through July 22 plus an estimate for the remaining month. Pure forecast begins in August 2026
- Accuracy is independently backtested only at `month × official brand anchor`. Model, PLC, and exact-part values are reconciled allocations and do not currently claim separate model accuracy

### 📤 Output and Business Controls
- `Output Center` centralizes the current Forecast Center view CSV and SOP Excel. The major header and forecast-control card do not duplicate downloads, and opening Output Center does not rerun a forecast
- The SOP Excel contains `Executive_Summary`, `Revenue_Forecast`, `Quantity_Forecast`, `Part_Planning`, `Wholesale_Drivers`, `Model_Performance`, and `QA_Assumptions`
- The current reference workbook has 21 non-missing PLC categories; their Quantity and Revenue totals reconcile exactly to total PIO Quantity and PIO Revenue
- Current independent brand-anchor accuracy is Revenue `83.03%`, PIO Quantity `83.84%`, and Wholesale Quantity `93.09%`. These are not Model/PLC accuracy scores and are not presented as 95%
- Run `python scripts/validate_anchor_policy.py <workbook.xlsx> --horizon 6` to reproduce mapping, cutoff, lifecycle, accuracy, and reconciliation checks

---

## Tech Stack

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 15.x | React full-stack framework |
| React | 19.x | UI library |
| Ant Design | 5.x | Enterprise component library |
| ECharts + echarts-for-react | 5.x / 3.x | Data visualization |
| TypeScript | 5.x | Type safety |
| dayjs | — | Date handling |

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| FastAPI | 0.116+ | Async REST API framework |
| Uvicorn | 0.35+ | ASGI server |
| Pandas | 3.x | Data processing and analysis |
| openpyxl / xlrd | — | Excel file parsing |
| python-multipart | — | File upload support |

---

## Project Structure

```
.
├── backend/
│   └── app/
│       └── main.py          # FastAPI routes: upload, workspace, pagination, export
│
├── frontend/
│   └── src/
│       └── app/
│           ├── page.tsx     # Main page: upload zone + tabbed workspace
│           ├── globals.css  # Global styles and design system tokens
│           └── layout.tsx   # Root layout
│
├── pio_platform/            # Reusable core data-processing library
│   ├── data_loader.py       # Excel parsing, header detection, type inference, role mapping
│   ├── profiling.py         # Column analysis, KPI computation, auto-insight generation
│   ├── config.py            # Field-role matching rule configuration
│   ├── filters.py           # Data filtering logic
│   ├── charts.py            # Chart payload construction
│   ├── fact_table.py        # HMA/GMA/KUS monthly facts and Wholesale/Working Days joins
│   ├── model_entities.py    # Model entities and lifecycle routing
│   ├── hierarchical_forecasting.py # Statistical models, OLS, Working Days, backtests
│   ├── forecast_center.py   # Reconciled Brand → Model → PLC forecast
│   ├── sop_workbook.py      # Executive Summary and detailed SOP Excel
│   └── i18n.py              # Internationalization support
│
├── scripts/
│   └── validate_anchor_policy.py # Reference-workbook business-policy validation
│
├── requirements.txt         # Python dependencies
├── .gitignore
└── README.md
```

---

## Running Locally

> Requirements: Python 3.11+, Node.js 18+

### 1. Start the Backend API

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start with hot-reload
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running, interactive API docs are available at: `http://127.0.0.1:8000/docs`

### 2. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open your browser at: [http://localhost:3000](http://localhost:3000)

### Environment Variables (Optional)

The frontend defaults to `http://127.0.0.1:8000`. Override via:

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### AI Analyst Environment

The backend can optionally load a local project-root `.env` file for the AI Analyst. Keep real secrets only in `.env` or server environment variables, never in committed source files.

```bash
# .env
PIO_AI_API_KEY=your-private-key
PIO_AI_BASE_URL=https://ai.gateway.lovable.dev
PIO_AI_MODEL=openai/gpt-5-mini
```

If no AI key is configured, the AI Analyst still works in `grounded_tools` mode using trusted anomaly and forecast outputs without external LLM rewriting.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/workbooks/upload` | Upload an Excel file; returns the full workspace payload |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}` | Fetch paginated sheet data with filter and sort support |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}?include_eda_dashboard=true` | Fetch the workspace payload with the optional EDA dashboard diagnostics |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/monthly-facts` | Fetch the HMA/GMA/KUS monthly fact table and coverage summary |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/forecast-center` | Fetch hierarchical Revenue / PIO Quantity / Wholesale forecasts |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/forecast-center/export.xlsx` | Export the Executive Summary and full Forecast SOP Excel |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/pivot` | Server-side pivot aggregation (rows / cols / measure / agg + filters) |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/export.csv` | Export the current filtered slice as CSV |

**Upload response shape:**
```json
{
  "workbook": { "id": "...", "filename": "...", "sheetNames": ["..."] },
  "workspace": {
    "overview":        { "kpis": {}, "summary": [], "health": {}, "autoInsights": [] },
    "table":           { "columns": [], "rows": [], "totalRows": 0 },
    "classification":  {},
    "insights":        {},
    "filterOptions":   {}
  }
}
```

---

## Roadmap

- [ ] **Brand accuracy improvement** — continue diagnosing structural change in HMA Revenue / PIO Quantity; do not claim 95% without independent backtest evidence
- [ ] **Executive Summary PDF** — add in-site preview and PDF export; the current deliverable is Executive Summary plus detailed Forecast Excel
- [ ] **Accessory lifecycle panel** — expose long-inactive `PIS_PNO` rows directly in EDA; current part planning already uses recent-six activity and volume eligibility to prevent allocation to long-inactive parts
- [ ] **HMA Fleet scenario** — add wholesale + fleet only if the business owner confirms it as an explicit, auditable scenario; the official rule remains dealer wholesale
- [ ] **Inventory recommendations** — produce replenishment and safety-stock recommendations from reconciled Quantity Forecasts

---

## License

MIT
