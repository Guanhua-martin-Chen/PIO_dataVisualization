from __future__ import annotations

import pandas as pd

from pio_platform.backtest_harness import (
    BacktestContract,
    audit_fold_coverage,
    calibrate_held_out_intervals,
    expected_fold_counts,
    predictions_to_frame,
    run_series_backtest,
)


def test_42_month_contract_has_18_17_16_and_51_folds() -> None:
    contract = BacktestContract()
    assert contract.tie_band_wape == 0.005
    assert expected_fold_counts(42, contract) == {
        "1": 18,
        "2": 17,
        "3": 16,
        "combined": 51,
    }
    months = pd.period_range("2023-01", periods=42, freq="M")
    series = pd.Series(range(100, 142), index=months, dtype=float)
    frame = predictions_to_frame(
        run_series_backtest(
            series,
            model_id="naive_last",
            target="quantity",
            level="official_total",
            entity="TOTAL",
            contract=contract,
        )
    )
    audit = audit_fold_coverage(
        frame,
        expected_entities={"TOTAL"},
        expected_horizon_counts=expected_fold_counts(42, contract),
    )
    assert audit["status"] == "pass"
    assert audit["observedHorizonCounts"] == {
        "1": 18,
        "2": 17,
        "3": 16,
        "combined": 51,
    }


def test_fold_failure_is_retained_and_blocks_full_coverage() -> None:
    months = pd.period_range("2023-01", periods=27, freq="M")
    series = pd.Series(range(27), index=months, dtype=float)

    def failing_predictor(history, horizon, training_months, target_months, working_days):
        if horizon == 2:
            raise RuntimeError("deliberate fold failure")
        return float(history[-1]), "test"

    frame = predictions_to_frame(
        run_series_backtest(
            series,
            model_id="test",
            target="quantity",
            level="total",
            entity="TOTAL",
            predictor=failing_predictor,
        )
    )
    audit = audit_fold_coverage(
        frame,
        expected_entities={"TOTAL"},
        expected_horizon_counts=expected_fold_counts(27),
    )
    assert len(frame) == expected_fold_counts(27)["combined"]
    assert frame.loc[frame["horizon"] == 2, "prediction"].isna().all()
    assert audit["status"] == "fail"
    assert audit["missingPredictionCount"] > 0


def test_prequential_intervals_are_ordered_and_report_coverage_metadata() -> None:
    calibration = []
    for index, month in enumerate(pd.period_range("2024-01", periods=18, freq="M")):
        calibration.append(
            {
                "origin_month": str(month - 1),
                "target_month": str(month),
                "horizon": 1,
                "actual": 100.0 + index,
                "prediction": 98.0 + index,
            }
        )
    intervals = calibrate_held_out_intervals(
        [{"forecastMonth": "2026-07", "horizon": 1, "point": 120.0}],
        calibration,
        calibration_scope_id="test_scope",
    )
    item = intervals[0]
    assert 0.0 <= item["lower"] <= item["point"] <= item["upper"]
    assert item["nominalCoverage"] == 0.90
    assert item["calibrationResidualCount"] == 18
    assert item["coverageSampleCount"] > 0
    assert item["empiricalCoverage"] is not None
    assert item["calibrationScopeId"] == "test_scope"
    assert item["validationStatus"] == "validated"
