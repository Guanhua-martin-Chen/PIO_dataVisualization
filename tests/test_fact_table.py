from __future__ import annotations

import unittest

import pandas as pd

from pio_platform.fact_table import (
    build_monthly_fact_table,
    build_wholesale_long,
    build_working_days_long,
    summarize_monthly_facts,
)


class MonthlyFactTableTests(unittest.TestCase):
    def test_wide_wholesale_blocks_receive_real_years_and_zero_sentinels(self) -> None:
        wholesale = pd.DataFrame(
            {
                "Brand": ["HMA", None],
                "Model": ["Elantra", "Elantra N"],
                "Model Code": [4, 4],
                "Jan": [100, 20],
                "Feb": [-1, 10],
                "Jan (2)": [120, 25],
                "Feb (2)": [130, 30],
            }
        )

        result = build_wholesale_long(wholesale, "Vehicle_Wholesale_Data", latest_sales_year=2026)

        self.assertEqual(sorted(result["month"].unique()), ["2025-01", "2025-02", "2026-01", "2026-02"])
        elantra_feb = result[(result["modelKey"] == "ELANTRA") & (result["month"] == "2025-02")]
        self.assertEqual(float(elantra_feb.iloc[0]["wholesaleUnits"]), 0.0)

    def test_wholesale_excludes_total_and_fleet_sections(self) -> None:
        wholesale = pd.DataFrame(
            {
                "Brand": ["HMA", None, None, "GMA", "▣ Fleet H/G/K Wholesale", "HMA", None],
                "Model": ["Elantra", "HMA Total", "Tucson", "G70", None, "Elantra", "Tucson"],
                "Jan": [100, 500, 200, 50, None, 999, 999],
            }
        )

        result = build_wholesale_long(wholesale, "2026 Vehicle Wholesale")

        self.assertEqual(set(result["modelName"]), {"Elantra", "Tucson", "G70"})
        self.assertEqual(float(result["wholesaleUnits"].sum()), 350.0)

    def test_fact_grain_combines_sales_wholesale_and_working_days(self) -> None:
        sales = pd.DataFrame(
            {
                "Brand": ["H", "H", "H"],
                "Model": ["Elantra", "Elantra", "Elantra N"],
                "Code": [4, 4, 4],
                "Part": ["P1", "P1", "P2"],
                "Description": ["Mat", "Mat", "Lock"],
                "PLC": ["Floor Mat", "Floor Mat", "Wheel Lock"],
                "Qty": [10, 5, 4],
                "Revenue": [100, 50, 80],
            }
        )
        dates = pd.Series(pd.to_datetime(["2025-01-03", "2025-01-20", "2025-01-11"]))
        wholesale = pd.DataFrame(
            {
                "month": ["2025-01", "2025-01"],
                "modelKey": ["ELANTRA", "ELANTRA N"],
                "wholesaleUnits": [100, 20],
            }
        )
        working_days = build_working_days_long(pd.DataFrame({"Month": [202501], "# of Working Days": [20]}))

        facts = build_monthly_fact_table(
            sales,
            dates,
            brand_col="Brand",
            model_col="Model",
            model_code_col="Code",
            part_number_col="Part",
            part_description_col="Description",
            plc_col="PLC",
            qty_col="Qty",
            revenue_col="Revenue",
            wholesale_long=wholesale,
            working_days_long=working_days,
        )
        summary = summarize_monthly_facts(facts)

        self.assertEqual(len(facts), 2)
        elantra = facts[facts["modelName"] == "Elantra"].iloc[0]
        self.assertEqual(float(elantra["installationQuantity"]), 15.0)
        self.assertEqual(float(elantra["pnvw"]), 1.5)
        self.assertEqual(float(elantra["accessoryUnitsPerVehicle"]), 0.15)
        self.assertEqual(elantra["anchorBrand"], "HMA")
        self.assertEqual(float(elantra["quantityPerWorkingDay"]), 0.75)
        self.assertEqual(elantra["plc"], "Floor Mat")
        self.assertEqual(summary["plcCount"], 2)
        self.assertEqual(summary["grain"], "month x brand x model entity x PLC x part number")
        self.assertEqual(summary["workingDaysCoveragePct"], 100.0)

    def test_hma_gma_kus_mapping_uses_exact_model_names_and_keeps_ioniq_variants_separate(self) -> None:
        sales = pd.DataFrame(
            {
                "Brand": ["H", "H", "H", "H"],
                "Model": ["Ioniq 5", "Ioniq 6", "GV60", "Sportage"],
                "Part": ["P1", "P2", "P3", "P4"],
                "Description": ["Mat", "Mat", "Mat", "Mat"],
                "PLC": ["Floor Mat"] * 4,
                "Qty": [10, 12, 8, 14],
                "Revenue": [100, 120, 160, 140],
            }
        )
        dates = pd.Series(pd.to_datetime(["2026-01-15"] * 4))
        wholesale = pd.DataFrame(
            {
                "month": ["2026-01"] * 4,
                "brand": ["HMA", "HMA", "GMA", "KUS"],
                "anchorBrand": ["HMA", "HMA", "GMA", "KUS"],
                "modelName": ["Ioniq 5", "Ioniq 6", "GV60 EV", "Sportage"],
                "modelKey": ["IONIQ 5", "IONIQ 6", "GV60 EV", "SPORTAGE"],
                "wholesaleUnits": [100, 120, 80, 140],
            }
        )

        facts = build_monthly_fact_table(
            sales,
            dates,
            brand_col="Brand",
            model_col="Model",
            model_code_col=None,
            part_number_col="Part",
            part_description_col="Description",
            plc_col="PLC",
            qty_col="Qty",
            revenue_col="Revenue",
            wholesale_long=wholesale,
        )

        anchors = dict(zip(facts["modelName"], facts["anchorBrand"], strict=False))
        self.assertEqual(anchors["Ioniq 5"], "HMA")
        self.assertEqual(anchors["Ioniq 6"], "HMA")
        self.assertEqual(anchors["GV60"], "GMA")
        self.assertEqual(anchors["Sportage"], "KUS")
        self.assertEqual(facts[facts["modelName"].str.startswith("Ioniq")]["entityKey"].nunique(), 2)


if __name__ == "__main__":
    unittest.main()
