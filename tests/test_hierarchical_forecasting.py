from __future__ import annotations

import unittest

import pandas as pd

from pio_platform.hierarchical_forecasting import build_hierarchical_forecast


class HierarchicalForecastTests(unittest.TestCase):
    def setUp(self) -> None:
        months = pd.date_range("2023-01-01", periods=36, freq="MS")
        rows = []
        for index, month in enumerate(months):
            seasonal = 20 if month.month in {3, 4, 5} else 0
            rows.extend(
                [
                    {
                        "month": month.strftime("%Y-%m"), "brand": "H", "entityKey": "H::ELANTRA",
                        "modelName": "Elantra", "partNumber": "P1", "partDescription": "Mat",
                        "lifecycleStatus": "Active", "installationQuantity": 100 + index + seasonal,
                    },
                    {
                        "month": month.strftime("%Y-%m"), "brand": "H", "entityKey": "H::ELANTRA N",
                        "modelName": "Elantra N", "partNumber": "P2", "partDescription": "Lock",
                        "lifecycleStatus": "Active", "installationQuantity": 30 + seasonal / 2,
                    },
                    {
                        "month": month.strftime("%Y-%m"), "brand": "H", "entityKey": "H::ELANTRA N",
                        "modelName": "Elantra N", "partNumber": "LOW", "partDescription": "Rare",
                        "lifecycleStatus": "Active", "installationQuantity": 1 if index < 3 else 0,
                    },
                ]
            )
        self.facts = pd.DataFrame(rows)
        self.working_days = pd.DataFrame(
            {
                "month": pd.date_range("2023-01-01", periods=48, freq="MS").strftime("%Y-%m"),
                "workingDays": [20 + (index % 3) for index in range(48)],
            }
        )

    def test_brand_model_and_accessory_levels_produce_accuracy(self) -> None:
        for level in ["brand", "model", "model_accessory"]:
            payload = build_hierarchical_forecast(
                self.facts,
                self.working_days,
                level=level,
                horizon=3,
                min_monthly_volume=5,
            )
            self.assertGreater(payload["summary"]["seriesCount"], 0)
            self.assertIsNotNone(payload["summary"]["weightedWape"])
            self.assertIsNotNone(payload["summary"]["accuracyPct"])
            self.assertEqual(len(payload["records"][0]["forecast"]), 3)
            self.assertGreater(payload["records"][0]["backtestPoints"], 0)
            self.assertIn("not used for model selection", payload["summary"]["accuracyDefinition"])

        accessory = build_hierarchical_forecast(
            self.facts,
            self.working_days,
            level="model_accessory",
            horizon=3,
            min_monthly_volume=5,
        )
        self.assertGreaterEqual(accessory["summary"]["excludedLowVolumeSeries"], 1)
        self.assertNotIn("LOW", {item["partNumber"] for item in accessory["records"]})

    def test_tariff_scenario_is_applied_after_model_selection(self) -> None:
        baseline = build_hierarchical_forecast(
            self.facts, self.working_days, level="brand", horizon=1, tariff_impact_pct=0
        )
        reduced = build_hierarchical_forecast(
            self.facts, self.working_days, level="brand", horizon=1, tariff_impact_pct=-10
        )
        self.assertAlmostEqual(reduced["records"][0]["nextForecast"], baseline["records"][0]["nextForecast"] * 0.9, places=6)

    def test_user_can_force_a_statistical_model(self) -> None:
        payload = build_hierarchical_forecast(
            self.facts,
            self.working_days,
            level="brand",
            horizon=2,
            model_strategy="naive_last",
        )
        self.assertEqual(payload["summary"]["factors"]["modelStrategy"], "naive_last")
        self.assertTrue(all(record["selectedModel"] == "naive_last" for record in payload["records"]))
        self.assertTrue(all("User forced" in record["selectionNote"] for record in payload["records"]))

    def test_forced_driver_returns_learned_coefficients(self) -> None:
        payload = build_hierarchical_forecast(
            self.facts,
            self.working_days,
            level="brand",
            horizon=2,
            model_strategy="driver_adjusted_regression",
        )
        record = payload["records"][0]
        self.assertEqual(record["selectedModel"], "driver_adjusted_regression")
        self.assertIn("trendPerMonth", record["learnedCoefficients"])
        self.assertIn("workingDaysPerDayEffect", record["learnedCoefficients"])
        self.assertIn("seasonalAmplitude", record["learnedCoefficients"])

    def test_unknown_model_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_hierarchical_forecast(
                self.facts,
                self.working_days,
                level="brand",
                model_strategy="random_model",
            )

    def test_model_accessory_rejects_a_shared_forced_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "automatic per-series"):
            build_hierarchical_forecast(
                self.facts,
                self.working_days,
                level="model_accessory",
                model_strategy="naive_last",
            )

    def test_complete_latest_month_is_kept_in_training(self) -> None:
        payload = build_hierarchical_forecast(
            self.facts,
            self.working_days,
            level="brand",
            horizon=1,
            latest_month_is_complete=True,
        )
        self.assertEqual(payload["summary"]["latestCompleteMonth"], "2025-12")

    def test_low_volume_latest_month_is_excluded_even_with_month_end_date(self) -> None:
        partial = self.facts.copy()
        partial.loc[partial["month"] == "2025-12", "installationQuantity"] = 0.1
        payload = build_hierarchical_forecast(
            partial,
            self.working_days,
            level="brand",
            horizon=1,
            latest_month_is_complete=True,
        )
        self.assertEqual(payload["summary"]["latestCompleteMonth"], "2025-11")
        self.assertTrue(payload["summary"]["latestMonthExcluded"])
        self.assertEqual(payload["summary"]["latestMonthCompletenessThreshold"], 0.90)


if __name__ == "__main__":
    unittest.main()
