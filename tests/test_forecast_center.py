from __future__ import annotations

import unittest
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from pio_platform.forecast_center import (
    build_forecast_center,
    build_part_planning_records,
)
from pio_platform.sop_workbook import build_sop_workbook_bytes


class ForecastCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        months = pd.date_range("2023-01-01", periods=43, freq="MS")
        rows = []
        for index, month in enumerate(months):
            partial = 0.55 if month == months[-1] else 1.0
            rows.extend(
                [
                    {
                        "month": month.strftime("%Y-%m"),
                        "brand": "H",
                        "entityKey": "H::ELANTRA",
                        "modelName": "Elantra",
                        "plc": "Floor Mat",
                        "partNumber": "H-MAT",
                        "partDescription": "Carpet Floor Mat",
                        "lifecycleStatus": "Active",
                        "installationQuantity": (100 + index) * partial,
                        "pioRevenue": (100 + index) * 80 * partial,
                    },
                    {
                        "month": month.strftime("%Y-%m"),
                        "brand": "H",
                        "entityKey": "H::ELANTRA",
                        "modelName": "Elantra",
                        "plc": "Cargo Tray",
                        "partNumber": "H-TRAY",
                        "partDescription": "Cargo Tray",
                        "lifecycleStatus": "Active",
                        "installationQuantity": (40 + index / 2) * partial,
                        "pioRevenue": (40 + index / 2) * 110 * partial,
                    },
                    {
                        "month": month.strftime("%Y-%m"),
                        "brand": "K",
                        "entityKey": "K::SPORTAGE",
                        "modelName": "Sportage",
                        "plc": "Floor Mat",
                        "partNumber": "K-MAT",
                        "partDescription": "Carpet Floor Mat",
                        "lifecycleStatus": "Active",
                        "installationQuantity": (70 + index / 3) * partial,
                        "pioRevenue": (70 + index / 3) * 75 * partial,
                    },
                ]
            )
        self.facts = pd.DataFrame(rows)
        self.working_days = pd.DataFrame(
            {
                "month": months.strftime("%Y-%m"),
                "workingDays": [20 + (index % 3) for index in range(len(months))],
            }
        )
        self.wholesale = pd.DataFrame(
            {
                "month": list(months.strftime("%Y-%m")) * 3,
                "brand": ["HMA"] * len(months) + ["GMA"] * len(months) + ["KUS"] * len(months),
                "modelName": ["Elantra"] * len(months) + ["GV70"] * len(months) + ["Sportage"] * len(months),
                "modelKey": ["ELANTRA"] * len(months) + ["GV70"] * len(months) + ["SPORTAGE"] * len(months),
                "wholesaleUnits": [200 + index for index in range(len(months))]
                + [50 + index for index in range(len(months))]
                + [150 + index for index in range(len(months))],
            }
        )

    def test_revenue_nowcast_and_hierarchy_reconcile(self) -> None:
        payload = build_forecast_center(
            self.facts,
            self.working_days,
            self.wholesale,
            metric="revenue",
            level="model_plc",
            horizon=3,
            latest_sales_month_is_complete=False,
            latest_sales_date=pd.Timestamp("2026-07-22"),
            include_all_records=True,
        )
        self.assertEqual(payload["summary"]["nowcastMonths"], ["2026-07"])
        self.assertEqual(payload["summary"]["pureForecastMonths"], ["2026-08", "2026-09"])
        self.assertEqual(payload["summary"]["reconciliation"]["status"], "PASS")
        self.assertLessEqual(len(payload["topAccessories"]), 10)
        self.assertTrue(all(record["plc"] in {"Floor Mat", "Cargo Tray"} for record in payload["records"]))
        self.assertEqual({record["brand"] for record in payload["brandRecords"]}, {"H", "K"})

    def test_wholesale_consolidates_hma_and_gma(self) -> None:
        payload = build_forecast_center(
            self.facts,
            self.working_days,
            self.wholesale,
            metric="wholesale_quantity",
            level="model",
            horizon=2,
            latest_sales_month_is_complete=False,
            latest_sales_date=pd.Timestamp("2026-07-22"),
        )
        self.assertEqual({record["brand"] for record in payload["brandRecords"]}, {"H", "K"})
        self.assertEqual(payload["summary"]["reconciliation"]["status"], "PASS")
        self.assertEqual(payload["summary"]["forecastMonths"][0], "2026-07")
        self.assertEqual(payload["summary"]["nowcastMonths"], ["2026-07"])

    def test_exact_parts_allocate_to_plc_parent(self) -> None:
        payload = build_forecast_center(
            self.facts,
            self.working_days,
            self.wholesale,
            metric="quantity",
            level="model_plc",
            horizon=2,
            latest_sales_month_is_complete=False,
            latest_sales_date=pd.Timestamp("2026-07-22"),
            include_all_records=True,
        )
        part_records = build_part_planning_records(
            self.facts,
            payload["modelPlcRecords"],
            metric="quantity",
            latest_complete_month=payload["summary"]["latestCompleteMonth"],
        )
        self.assertGreater(len(part_records), 0)
        parent = {
            (record["brand"], record["entityKey"], record["plc"], item["month"]): item["value"]
            for record in payload["modelPlcRecords"]
            for item in record["forecast"]
        }
        children: dict[tuple[str, str, str, str], float] = {}
        for record in part_records:
            key = (record["brand"], record["entityKey"], record["plc"], record["month"])
            children[key] = children.get(key, 0.0) + record["value"]
        for key, value in parent.items():
            self.assertAlmostEqual(children[key], value, places=6)

    def test_sop_workbook_has_governed_sheets_and_formulas(self) -> None:
        payloads = {}
        for metric in ["revenue", "quantity", "wholesale_quantity"]:
            payloads[metric] = build_forecast_center(
                self.facts,
                self.working_days,
                self.wholesale,
                metric=metric,
                level="brand",
                horizon=2,
                latest_sales_month_is_complete=False,
                latest_sales_date=pd.Timestamp("2026-07-22"),
                include_all_records=True,
            )
        part_quantity = build_part_planning_records(
            self.facts,
            payloads["quantity"]["modelPlcRecords"],
            metric="quantity",
            latest_complete_month=payloads["quantity"]["summary"]["latestCompleteMonth"],
        )
        part_revenue = build_part_planning_records(
            self.facts,
            payloads["revenue"]["modelPlcRecords"],
            metric="revenue",
            latest_complete_month=payloads["revenue"]["summary"]["latestCompleteMonth"],
        )
        output = build_sop_workbook_bytes(
            source_filename="source.xlsx",
            revenue=payloads["revenue"],
            quantity=payloads["quantity"],
            wholesale=payloads["wholesale_quantity"],
            part_quantity=part_quantity,
            part_revenue=part_revenue,
            working_days=self.working_days.to_dict("records"),
        )
        workbook = load_workbook(BytesIO(output), data_only=False)
        self.assertEqual(
            workbook.sheetnames,
            [
                "Executive_Summary",
                "Revenue_Forecast",
                "Quantity_Forecast",
                "Part_Planning",
                "Wholesale_Drivers",
                "Model_Performance",
                "QA_Assumptions",
            ],
        )
        self.assertTrue(str(workbook["QA_Assumptions"]["B5"].value).startswith("="))
        self.assertTrue(str(workbook["Part_Planning"]["O6"].value).startswith("="))


if __name__ == "__main__":
    unittest.main()
