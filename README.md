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

V1 专注于第一个核心业务需求：**从 Excel 工作簿中提取、清洗、分类数据，并在进入异常检测和销量预测模块之前，提供一个可靠的数据全貌视图。**

平台已在包含约 **199,000 行**销售记录的真实数据集上完成测试，所有表格浏览均采用服务端分页，不会将完整数据集加载进浏览器。

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
│   └── i18n.py              # 多语言支持
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
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/pivot` | 服务端透视聚合（rows / cols / measure / agg + 过滤条件） |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/export.csv` | 导出当前过滤切片为 CSV |

---

## 路线图

- [ ] **异常检测**：识别销量异常月份，定位问题零件/车型
- [ ] **驱动力分析**：解释按零件/车型/月份维度的涨跌原因
- [ ] **需求预测**：生成下月/下年销量预测
- [ ] **渗透率分析**：结合整车批发数据计算零件装配渗透率
- [ ] **库存建议**：基于预测输出库存补货推荐

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

V1 is built around a single core business need: **extract, clean, and classify data from Excel workbooks, and surface a reliable dataset overview before the anomaly-detection and forecasting modules come online.**

The platform has been tested against a real-world dataset of approximately **199,000 sales rows**. All table browsing is server-side paginated — the full dataset is never loaded into the browser.

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
│   └── i18n.py              # Internationalization support
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

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/workbooks/upload` | Upload an Excel file; returns the full workspace payload |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}` | Fetch paginated sheet data with filter and sort support |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}?include_eda_dashboard=true` | Fetch the workspace payload with the optional EDA dashboard diagnostics |
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

V1 is the data-preparation and field-classification foundation. Planned modules:

- [ ] **Anomaly Detection** — identify abnormal sales months and pinpoint problem parts / models
- [ ] **Driver Analysis** — explain rises and declines across part / model / month dimensions
- [ ] **Forecast Center** — generate next-month and next-year demand forecasts
- [ ] **Penetration Analysis** — calculate part fitment penetration against vehicle wholesale data
- [ ] **Inventory Recommendations** — produce replenishment suggestions from forecast output

---

## EDA & Visual Charts Update / EDA 与可视化图表更新

### EDA Dashboard / 探索性数据分析

- **Data quality diagnostics / 数据质量诊断**: checks missing key fields, negative revenue, negative installation quantity, zero installation quantity, and unit-price p01 / p99 outliers.
- **Part number vs description discrepancies / 零件号与描述差异检查**: checks whether one `PIS_PNO` maps to multiple `Part Description` values. Case-only or spacing-only differences are shown as format warnings, not true description mismatches.
- **Top brand revenue / 品牌收入排行**: groups by `PIS_CMP_KND` and sums `SumOfPIS_CRP_CFM_PRI`.
- **Wholesale relationship check / Wholesale 关联检查**: links `PIO_Sales_Data.PIS_SERI` to `Vehicle_Wholesale_Data.Model Code`, then lists unmatched `PIS_SERI` samples with source Excel row numbers.
- **PNVW definition / PNVW 计算口径**: `PNVW = SumOfPIS_CRP_CFM_PRI / wholesale units`. The numerator uses dollar revenue from `SumOfPIS_CRP_CFM_PRI`, not installation quantity from `SumOfPIS_INST_QT`.

### Visual Charts Additions / 可视化图表补充

- Existing charts remain in Visual Charts: `Monthly installation quantity`, `Monthly revenue`, `Top vehicle models by revenue`, and `Top parts by revenue`.
- Added `Wholesale monthly trend`: monthly wholesale units aggregated from the wholesale worksheet.
- Added `PNVW monthly trend`: monthly `SumOfPIS_CRP_CFM_PRI / wholesale units`.
- Wholesale and PNVW trend charts use complete months only. For example, if PIO sales data includes an incomplete June, these trend charts stop at May.

### Calculation Notes / 计算说明

- `Monthly installation quantity` = month-level sum of `SumOfPIS_INST_QT`.
- `Monthly revenue` = month-level sum of `SumOfPIS_CRP_CFM_PRI`.
- `Top parts by revenue` = group by part description or part number, then sum `SumOfPIS_CRP_CFM_PRI`.
- `Top vehicle models by revenue` = group by `Model`, then sum `SumOfPIS_CRP_CFM_PRI`.
- `Wholesale monthly trend` = group matched wholesale rows by month, then sum wholesale units.
- `PNVW monthly trend` = monthly `SumOfPIS_CRP_CFM_PRI` divided by monthly wholesale units.

---

## License

MIT
