from __future__ import annotations

import unittest
from datetime import datetime

import pandas as pd

from pio_platform.data_loader import materialize_dataset, parse_date_series


class DateCleaningTests(unittest.TestCase):
    def test_wide_month_matrix_keeps_first_vehicle_out_of_header(self) -> None:
        raw = pd.DataFrame(
            [
                ["Brand", "2023 Wholesale", None, None, None, None, None, None],
                [None, "Model", "January", "February", "March", "April", "May", "June"],
                ["HMA", "Accent", 13, 12, 0, 0, 0, 0],
                [None, "Elantra", 8122, 9102, 11300, 9201, 11753, 10619],
            ]
        )

        from pio_platform.data_loader import detect_header_config

        header_row, depth = detect_header_config(raw)
        dataset = materialize_dataset(raw, header_row, depth)

        self.assertEqual((header_row, depth), (0, 2))
        self.assertIn("Model", " | ".join(dataset.columns))
        self.assertEqual(dataset.iloc[0].astype(str).tolist()[1], "Accent")

    def test_business_ready_sales_header_uses_fast_first_row_path(self) -> None:
        from pio_platform.data_loader import detect_header_config

        raw = pd.DataFrame(
            [
                ["PIS_MST_IVC_DT", "PIS_CMP_KND", "PIS_SERI", "PIS_PNO", "SumOfPIS_INST_QT", "Model"],
                [20230101, "H", 4, "P1", 10, "Elantra"],
            ]
        )
        self.assertEqual(detect_header_config(raw), (0, 1))

    def test_mixed_excel_dates_are_normalized_without_1970_corruption(self) -> None:
        values = pd.Series(
            [
                datetime(2023, 1, 1),
                "2024-02-03",
                46195,
                202505,
                20250607,
                "2026/06/08",
                "0001-01-01",
                None,
            ],
            dtype="object",
        )

        parsed = parse_date_series(values)

        self.assertEqual(parsed.iloc[0], pd.Timestamp("2023-01-01"))
        self.assertEqual(parsed.iloc[1], pd.Timestamp("2024-02-03"))
        self.assertEqual(parsed.iloc[2], pd.Timestamp("2026-06-22"))
        self.assertEqual(parsed.iloc[3], pd.Timestamp("2025-05-01"))
        self.assertEqual(parsed.iloc[4], pd.Timestamp("2025-06-07"))
        self.assertEqual(parsed.iloc[5], pd.Timestamp("2026-06-08"))
        self.assertTrue(pd.isna(parsed.iloc[6]))
        self.assertTrue(pd.isna(parsed.iloc[7]))
        self.assertNotIn(1970, parsed.dropna().dt.year.tolist())

    def test_minus_one_numeric_sentinel_becomes_zero_at_materialization(self) -> None:
        raw = pd.DataFrame(
            [
                ["Model", "Jan", "SumOfPIS_INST_QT"],
                ["Kona EV", -1, -1],
                ["Elantra", 12, 3],
            ]
        )

        dataset = materialize_dataset(raw, header_row_index=0, header_depth=1)

        self.assertEqual(dataset.loc[0, "Jan"], 0)
        self.assertEqual(dataset.loc[0, "SumOfPIS_INST_QT"], 0)
        self.assertEqual(dataset.loc[1, "Jan"], 12)


if __name__ == "__main__":
    unittest.main()
