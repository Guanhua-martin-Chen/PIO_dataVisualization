from __future__ import annotations

import pandas as pd

from pio_platform.backtest_harness import BacktestContract, select_champion
from pio_platform.ets_experiments import (
    EtsCandidateSpec,
    VALIDATED_REFERENCE_PORTFOLIO,
    audit_candidate_result,
    build_candidate_grid,
    run_ets_candidate,
)
from scripts.run_unified_backtest import month_number, working_days_map


def test_candidate_grid_covers_requested_dimensions() -> None:
    candidates = build_candidate_grid(
        preprocessing_modes=("raw", "anomaly_softened", "robust_winsorized")
    )
    assert len(candidates) == 1080
    assert {item.transform for item in candidates} == {"raw", "log1p", "boxcox"}
    assert {item.training_window for item in candidates} == {
        "expanding",
        "rolling_24",
        "rolling_30",
        "rolling_36",
    }
    assert {item.initialization_method for item in candidates} == {
        "estimated",
        "heuristic",
        "legacy-heuristic",
    }
    assert {item.preprocessing for item in candidates} == {
        "raw",
        "anomaly_softened",
        "robust_winsorized",
    }


def test_candidate_uses_common_folds_and_true_h_step_forecast() -> None:
    months = pd.period_range("2023-01", periods=42, freq="M")
    values = pd.Series(
        [100.0 + 2.0 * index + (index % 12) * 0.5 for index in range(42)],
        index=months,
    )
    spec = EtsCandidateSpec(
        model_id="test_holt",
        implementation="statsmodels_holtwinters",
        trend="additive",
        damped_trend=True,
        seasonality=None,
        initialization_method="estimated",
        smoothing_parameter_selection="optimized_sse",
        transform="log1p",
        training_window="rolling_24",
        preprocessing="anomaly_softened",
        optimized=True,
        remove_bias=False,
    )
    result = run_ets_candidate(
        values,
        spec,
        contract=BacktestContract(),
        source_hash="test-hash",
    )
    audit = audit_candidate_result(result)

    assert audit["status"] == "pass"
    assert audit["horizonCounts"] == {"1": 18, "2": 17, "3": 16, "combined": 51}
    assert result["failedFoldCount"] == 0
    assert result["combinedMetrics"]["predictionCoverage"] == 1.0
    assert all(row["training_end"] == row["origin_month"] for row in result["predictions"])
    assert all(row["model_training_months"] <= 24 for row in result["predictions"])
    assert any(
        diagnostic["parameters"].get("smoothing_level") is not None
        for diagnostic in result["originDiagnostics"]
    )


def test_working_days_parser_accepts_yyyymm_month_column() -> None:
    frame = pd.DataFrame(
        {
            "YYYY": ["2023", "2023", "2023"],
            "Month": [202301, 202302, 202303],
            "# of Working Days": [20, 19, 23],
        }
    )

    assert month_number(202301) == 1
    assert working_days_map(frame) == {
        "2023-01": 20.0,
        "2023-02": 19.0,
        "2023-03": 23.0,
    }


def test_champion_tie_break_prefers_coverage_before_complexity() -> None:
    candidates = {
        "partial_simple": {
            "wape": 0.10,
            "biasPercentage": 0.01,
            "foldWapeStandardDeviation": 0.05,
            "predictionCoverage": 0.90,
            "foldCount": 45,
        },
        "complete_complex": {
            "wape": 0.10,
            "biasPercentage": 0.01,
            "foldWapeStandardDeviation": 0.05,
            "predictionCoverage": 1.0,
            "foldCount": 51,
        },
    }

    decision = select_champion(
        candidates,
        complexity={"partial_simple": 1, "complete_complex": 9},
    )

    assert decision["champion"] == "complete_complex"


def test_validated_reference_constant_matches_model_registry() -> None:
    import json
    from pathlib import Path

    registry = json.loads(
        Path("config/forecast_model_registry.json").read_text(encoding="utf-8")
    )
    model = next(
        item
        for item in registry["models"]
        if item["id"] == "rebuilt_reference_portfolio_v1"
    )

    assert model["reportedEvidence"]["officialTotalWape"] == (
        VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["wape"]
    )
    assert model["reportedEvidence"]["officialTotalAccuracy"] == (
        VALIDATED_REFERENCE_PORTFOLIO["officialTotal"]["accuracy"]
    )
    assert model["reportedEvidence"]["foldCount"] == (
        VALIDATED_REFERENCE_PORTFOLIO["foldCount"]
    )


def test_registry_json_and_markdown_share_governed_scope_numbers() -> None:
    import json
    from pathlib import Path

    registry = json.loads(
        Path("config/forecast_model_registry.json").read_text(encoding="utf-8")
    )
    markdown = Path("docs/forecasting/MODEL_REGISTRY.md").read_text(encoding="utf-8")
    scope_id = "governed_h123_24m_h1_18_h2_17_h3_16_official_total_51"
    scope = registry["evaluationScopes"][scope_id]

    assert registry["schemaVersion"] == "1.2.0"
    assert registry["asOf"] == "2026-07-29"
    assert registry["evaluationContract"]["primaryHorizon"] == 1
    assert registry["evaluationContract"]["tieBandWape"] == 0.005
    assert scope["foldCounts"] == {"1": 18, "2": 17, "3": 16, "combined": 51}
    assert scope_id in markdown
    assert "18/17/16" in markdown
    assert "51 Official Total common-origin rows" in markdown
    assert (
        registry["latestUnifiedRun"]["officialTotalResults"][
            "referenceQuantityTotalEtsProxy"
        ]["evidenceStatus"]
        == "invalid_superseded"
    )
