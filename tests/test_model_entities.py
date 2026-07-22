from __future__ import annotations

import unittest

import pandas as pd

from pio_platform.model_entities import build_model_entity_map, build_model_lifecycle


class ModelEntityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.df = pd.DataFrame(
            {
                "Brand": ["H", "H", "H", "H", "K", "K", "H", "H"],
                "Model": ["Elantra", "Elantra N", "Accent", "Accent", "Stinger", "Stinger", "Sonata", "Sonata"],
                "Code": [4, 4, "B", "B", "C", "C", 2, 2],
                "Qty": [10, 2, 3, 1, 5, 8, 7, 9],
            }
        )
        self.dates = pd.Series(
            pd.to_datetime(
                [
                    "2026-01-01",
                    "2026-01-01",
                    "2023-01-01",
                    "2023-02-01",
                    "2023-01-01",
                    "2025-07-01",
                    "2025-12-01",
                    "2026-01-01",
                ]
            )
        )

    def test_same_code_does_not_merge_distinct_model_names(self) -> None:
        payload = build_model_entity_map(
            self.df,
            model_col="Model",
            brand_col="Brand",
            model_code_col="Code",
        )
        keys = {item["entityKey"] for item in payload["records"]}

        self.assertIn("H::ELANTRA", keys)
        self.assertIn("H::ELANTRA N", keys)
        self.assertEqual(payload["count"], 5)

    def test_lifecycle_is_computed_from_positive_activity(self) -> None:
        payload = build_model_lifecycle(
            self.df,
            self.dates,
            model_col="Model",
            qty_col="Qty",
            brand_col="Brand",
            model_code_col="Code",
            cutoff_year=2024,
            reintroduction_gap_months=12,
        )
        by_name = {item["modelName"]: item for item in payload["records"]}

        self.assertTrue(by_name["Accent"]["discontinuedThroughCutoff"])
        self.assertEqual(by_name["Accent"]["lastPositiveMonth"], "2023-02")
        self.assertTrue(by_name["Stinger"]["reintroduced"])
        self.assertEqual(by_name["Stinger"]["reintroducedMonth"], "2025-07")
        self.assertEqual(by_name["Sonata"]["statusCode"], "active")


if __name__ == "__main__":
    unittest.main()
