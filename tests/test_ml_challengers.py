from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from pio_platform.backtest_harness import BacktestContract, expected_fold_counts
from pio_platform.ml_challengers import (
    ELASTIC_NET_RESIDUAL_ID,
    TREE_META_SELECTOR_ID,
    clear_ml_artifact_cache,
    forecast_with_ml_challenger,
    load_ml_challenger_artifact,
    save_ml_challenger_artifacts,
    train_ml_challengers,
)


class MlChallengerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_hash = "a" * 64
        months = pd.period_range("2023-01", periods=15, freq="M")
        rows: list[dict[str, object]] = []
        for entity_index, entity in enumerate(("HMA", "GMA", "KUS")):
            scale = 1_000_000.0 + entity_index * 200_000.0
            for index, month in enumerate(months):
                value = (
                    scale
                    + index * 15_000.0
                    + 120_000.0 * np.sin(2.0 * np.pi * index / 12.0)
                )
                rows.append(
                    {
                        "month": str(month),
                        "entity": entity,
                        "value": max(float(value), 0.0),
                    }
                )
        cls.revenue = pd.DataFrame(rows)
        cls.working_days = {
            str(month): float(20 + (month.month % 3)) for month in months
        }
        for month in pd.period_range("2024-04", periods=6, freq="M"):
            cls.working_days[str(month)] = float(20 + (month.month % 3))
        cls.contract = BacktestContract(minimum_training_months=12)
        with patch(
            "pio_platform.ml_challengers._reference_anchor_prediction",
            side_effect=lambda history, **kwargs: float(history[-1]),
        ), patch(
            "pio_platform.ml_challengers.forecast_history",
            side_effect=lambda history, horizon, method: [float(history[-1])] * horizon,
        ):
            cls.artifacts = train_ml_challengers(
                cls.revenue,
                cls.working_days,
                source_hash=cls.source_hash,
                training_cutoff="2024-03",
                contract=cls.contract,
            )

    def test_both_challengers_keep_complete_common_folds(self) -> None:
        expected = expected_fold_counts(15, self.contract)
        for model_id in (TREE_META_SELECTOR_ID, ELASTIC_NET_RESIDUAL_ID):
            artifact = self.artifacts[model_id]
            audit = artifact["evaluation"]["foldAudit"]
            self.assertEqual(audit["status"], "pass")
            self.assertEqual(audit["observedHorizonCounts"], expected)
            self.assertEqual(audit["missingPredictionCount"], 0)
            self.assertEqual(audit["coverage"], 1.0)
            self.assertFalse(artifact["runtime"]["gpuRequired"])
            self.assertFalse(artifact["productionDefault"])

    def test_nested_predictions_never_skip_an_outer_row(self) -> None:
        rows = self.artifacts[TREE_META_SELECTOR_ID]["evaluation"]["predictions"]
        self.assertEqual(len(rows), 3 * expected_fold_counts(15, self.contract)["combined"])
        for row in rows:
            self.assertLess(row["origin_month"], row["target_month"])
            self.assertIsNotNone(row["prediction"])
            self.assertGreaterEqual(float(row["prediction"]), 0.0)

    def test_compact_artifact_loads_only_for_exact_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_ml_challenger_artifacts(
                self.artifacts,
                output_dir=output_dir,
            )
            tree_payload = json.loads(
                (output_dir / f"{TREE_META_SELECTOR_ID}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn("predictions", tree_payload["evaluation"])
            self.assertEqual(
                len(tree_payload["evaluation"]["calibrationRows"]),
                3 * expected_fold_counts(15, self.contract)["combined"],
            )
            loaded = load_ml_challenger_artifact(
                TREE_META_SELECTOR_ID,
                self.source_hash,
                artifact_dir=output_dir,
            )
            self.assertEqual(loaded["modelId"], TREE_META_SELECTOR_ID)
            clear_ml_artifact_cache()
            with self.assertRaisesRegex(ValueError, "different source"):
                load_ml_challenger_artifact(
                    TREE_META_SELECTOR_ID,
                    "b" * 64,
                    artifact_dir=output_dir,
                )

    def test_pretrained_inference_is_nonnegative_and_cpu_only(self) -> None:
        gma = self.revenue[self.revenue["entity"] == "GMA"].set_index("month")[
            "value"
        ]
        gma.index = pd.PeriodIndex(gma.index, freq="M")
        for model_id in (TREE_META_SELECTOR_ID, ELASTIC_NET_RESIDUAL_ID):
            result = forecast_with_ml_challenger(
                self.artifacts[model_id],
                gma,
                entity="GMA",
                horizon=3,
                working_days=self.working_days,
            )
            self.assertEqual(result["model"], model_id)
            self.assertEqual(len(result["forecast"]), 3)
            self.assertTrue(all(value >= 0.0 for value in result["forecast"]))
            self.assertEqual(
                result["coefficients"]["runtime"]["accelerator"],
                "cpu",
            )


if __name__ == "__main__":
    unittest.main()
