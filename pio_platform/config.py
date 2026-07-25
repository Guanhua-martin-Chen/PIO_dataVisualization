from __future__ import annotations

from dataclasses import dataclass


ROLE_PATTERNS = {
    "date": [
        "date",
        "yyyymm",
        "invoice dt",
        "ivc dt",
        "month",
        "period",
        "deliminated date",
        "delimited date",
    ],
    "brand": ["brand", "cmp knd", "company kind", "make"],
    "model": ["model", "seri", "series", "vehicle model"],
    "model_year": ["model year", "mdl yy", "year"],
    "part_number": ["part number", "part no", "pno", "sku", "item"],
    "part_description": ["part description", "description", "desc"],
    "plc": ["plc", "product list catalog"],
    "installation_quantity": [
        "inst qt",
        "installation quantity",
        "install qty",
        "quantity",
        "qty",
        "units",
        "volume",
    ],
    "revenue": [
        "revenue",
        "sales revenue",
        "sales",
        "amount",
        "price",
        "cfm pri",
        "value",
    ],
}

PRIMARY_FILTER_ROLES = [
    "date",
    "brand",
    "model",
    "model_year",
    "part_number",
    "part_description",
    "plc",
]

FUTURE_MODULES = [
    ("Explorer", "Live now", "Excel upload, profiling, filters, KPI cards, charts, exports"),
    ("Forecast Center", "Next", "Demand forecast, WAPE, MAE, bias, confidence intervals"),
    ("Penetration Analysis", "Next", "PIO installation quantity versus vehicle wholesale volume"),
    ("Inventory Simulator", "Later", "Reorder logic from forecast, stock, safety stock, and lead time"),
    ("AI Analyst", "Later", "Natural-language analysis over trusted metrics and forecast tools"),
]


@dataclass(frozen=True)
class ThemePreset:
    name: str
    page_bg: str
    card_bg: str
    card_alt_bg: str
    text: str
    muted_text: str
    border: str
    grid: str
    accent: str
    chart_bg: str
    sidebar_bg: str
    sidebar_surface: str
    sidebar_text: str


THEME_PRESETS = {
    "Blueprint": ThemePreset(
        name="Blueprint",
        page_bg="#f4f7fb",
        card_bg="#ffffff",
        card_alt_bg="#f8fbff",
        text="#101820",
        muted_text="#5b6b7d",
        border="#d7e0ea",
        grid="#e7edf5",
        accent="#0f62fe",
        chart_bg="#ffffff",
        sidebar_bg="#08111f",
        sidebar_surface="#0f1b2d",
        sidebar_text="#f5f8ff",
    ),
    "Steel": ThemePreset(
        name="Steel",
        page_bg="#eef2f5",
        card_bg="#ffffff",
        card_alt_bg="#f7f9fb",
        text="#16202b",
        muted_text="#62707f",
        border="#d4dce5",
        grid="#e1e8f0",
        accent="#1455d9",
        chart_bg="#ffffff",
        sidebar_bg="#111827",
        sidebar_surface="#1b2434",
        sidebar_text="#eff4ff",
    ),
    "Night Shift": ThemePreset(
        name="Night Shift",
        page_bg="#050a12",
        card_bg="#0f1826",
        card_alt_bg="#142033",
        text="#edf3ff",
        muted_text="#91a3bf",
        border="#203149",
        grid="#22314b",
        accent="#7db2ff",
        chart_bg="#0f1826",
        sidebar_bg="#02050b",
        sidebar_surface="#09111d",
        sidebar_text="#f4f8ff",
    ),
}
