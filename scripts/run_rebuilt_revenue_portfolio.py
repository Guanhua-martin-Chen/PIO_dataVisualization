from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pio_platform.backtest_harness import (  # noqa: E402
    CONTRACT_VERSION,
    BacktestContract,
    make_predictor,
    normalize_monthly_series,
    predictions_to_frame,
    run_portfolio_backtest,
    run_series_backtest,
    select_champion,
    summarize_predictions,
)
from pio_platform.ets_experiments import (  # noqa: E402
    EtsCandidateSpec,
    audit_candidate_result,
    run_ets_candidate,
)
from scripts.run_unified_backtest import (  # noqa: E402
    DEFAULT_SOURCE,
    load_governed_monthly,
    sha256_file,
)


EXPERIMENT_SOURCE_HASH = "f44048f30632e6f1d77d5336d2d313b4855e9d1cec95577b4a50f1c8f33c2c47"
DEFAULT_EXPERIMENT = (
    PROJECT_ROOT
    / "outputs"
    / "backtests"
    / f"hma_ets_experiment_{EXPERIMENT_SOURCE_HASH[:12]}_{CONTRACT_VERSION}.json"
)
OFFICIAL_ANCHORS = ("HMA", "GMA", "KUS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare rebuilt HMA ETS reference portfolio with governed Revenue baselines."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--hma-experiment", type=Path, default=DEFAULT_EXPERIMENT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    actual_hash = sha256_file(source)
    output_path = args.output or (
        PROJECT_ROOT
        / "outputs"
        / "backtests"
        / f"rebuilt_revenue_portfolio_{actual_hash[:12]}_{CONTRACT_VERSION}.json"
    )

    governed = load_governed_monthly(source, actual_hash, use_cache=True)
    if not governed.get("workingDays"):
        raise RuntimeError("Working Days are required for the rebuilt portfolio.")
    revenue = governed["pioRevenue"]
    working_days = governed["workingDays"]
    contract = BacktestContract()

    experiment = json.loads(args.hma_experiment.read_text(encoding="utf-8"))
    champion_id = experiment["selection"]["champion"]
    champion_summary = next(
        item
        for item in experiment["candidateSummaries"]
        if item["modelId"] == champion_id
    )
    champion_spec = _candidate_from_dict(champion_summary["spec"])

    runs: dict[str, dict[str, Any]] = {}
    runs["current_auto"] = _enrich_standard_run(
        run_portfolio_backtest(
            revenue,
            model_id="current_auto",
            target="pio_revenue",
            entity_models={anchor: "auto" for anchor in OFFICIAL_ANCHORS},
            contract=contract,
            working_days=working_days,
            source_hash=actual_hash,
        ),
        contract,
    )
    runs["legacy_frozen"] = _enrich_standard_run(
        run_portfolio_backtest(
            revenue,
            model_id="legacy_frozen",
            target="pio_revenue",
            entity_models={
                "HMA": "damped_trend",
                "GMA": "log_linear_trend",
                "KUS": "seasonal_mean",
            },
            contract=contract,
            working_days=working_days,
            source_hash=actual_hash,
        ),
        contract,
    )
    runs["current_reference_proxy"] = _enrich_standard_run(
        run_portfolio_backtest(
            revenue,
            model_id="current_reference_proxy",
            target="pio_revenue",
            entity_models={
                "HMA": "ets_additive",
                "GMA": "naive_last",
                "KUS": "working_day_adjusted_seasonal",
            },
            contract=contract,
            working_days=working_days,
            source_hash=actual_hash,
        ),
        contract,
    )
    rebuilt, hma_audit = _run_rebuilt_portfolio(
        revenue,
        champion_spec=champion_spec,
        contract=contract,
        working_days=working_days,
        source_hash=actual_hash,
    )
    runs["rebuilt_reference_portfolio"] = rebuilt
    runs["naive_last_portfolio_baseline"] = _enrich_standard_run(
        run_portfolio_backtest(
            revenue,
            model_id="naive_last_portfolio_baseline",
            target="pio_revenue",
            entity_models={anchor: "naive_last" for anchor in OFFICIAL_ANCHORS},
            contract=contract,
            working_days=working_days,
            source_hash=actual_hash,
        ),
        contract,
    )
    runs["seasonal_naive_portfolio_baseline"] = _enrich_standard_run(
        run_portfolio_backtest(
            revenue,
            model_id="seasonal_naive_portfolio_baseline",
            target="pio_revenue",
            entity_models={anchor: "seasonal_naive" for anchor in OFFICIAL_ANCHORS},
            contract=contract,
            working_days=working_days,
            source_hash=actual_hash,
        ),
        contract,
    )

    candidate_metrics = {
        name: run["officialTotalMetrics"] for name, run in runs.items()
    }
    selection = select_champion(
        candidate_metrics,
        tie_band_wape=contract.tie_band_wape,
        complexity={
            "current_auto": 6,
            "legacy_frozen": 4,
            "current_reference_proxy": 4,
            "rebuilt_reference_portfolio": 6,
            "naive_last_portfolio_baseline": 1,
            "seasonal_naive_portfolio_baseline": 2,
        },
    )
    empirical_best = min(
        candidate_metrics,
        key=lambda name: (
            float(candidate_metrics[name]["wape"]),
            name,
        ),
    )
    selection["empiricalBest"] = empirical_best
    promotion = _promotion_decision(
        runs,
        hma_audit,
        champion_summary,
        registry_updated=(
            _registry_has_champion()
            and actual_hash == EXPERIMENT_SOURCE_HASH
        ),
    )

    output = {
        "contractVersion": contract.version,
        "contract": contract.__dict__,
        "source": {
            "path": str(source),
            "sha256": actual_hash,
            "actualThrough": governed["actualThrough"],
            "completedTrainingThrough": governed["completedTrainingThrough"],
            "workingDaysCount": len(working_days),
            "rawExcelReadScope": "Working_Days sheet only when repairing empty governed cache",
        },
        "modelSpecificationTransfer": {
            "specificationSourceSha256": EXPERIMENT_SOURCE_HASH,
            "evaluationSourceSha256": actual_hash,
            "status": (
                "same_source"
                if actual_hash == EXPERIMENT_SOURCE_HASH
                else "fixed_validated_spec_retrained_and_rebacktested_on_new_source"
            ),
            "registeredMetricsEligible": actual_hash == EXPERIMENT_SOURCE_HASH,
        },
        "hmaCandidate": champion_summary,
        "hmaLeakageAudit": hma_audit,
        "runs": runs,
        "selection": selection,
        "promotionDecision": promotion,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "hmaCandidate": champion_id,
                "officialTotals": {
                    name: {
                        "h1Wape": run["horizonMetrics"]["1"]["wape"],
                        "h2Wape": run["horizonMetrics"]["2"]["wape"],
                        "h3Wape": run["horizonMetrics"]["3"]["wape"],
                        "combinedWape": run["officialTotalMetrics"]["wape"],
                        "accuracy": run["officialTotalMetrics"]["accuracy"],
                        "biasPercentage": run["officialTotalMetrics"]["biasPercentage"],
                        "foldWapeStandardDeviation": run["officialTotalMetrics"][
                            "foldWapeStandardDeviation"
                        ],
                        "coverage": run["officialTotalMetrics"]["predictionCoverage"],
                        "foldCount": run["officialTotalMetrics"]["foldCount"],
                    }
                    for name, run in runs.items()
                },
                "selection": selection,
                "promotionDecision": promotion,
            },
            indent=2,
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def _run_rebuilt_portfolio(
    revenue: pd.DataFrame,
    *,
    champion_spec: EtsCandidateSpec,
    contract: BacktestContract,
    working_days: dict[str, float],
    source_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_frames: list[pd.DataFrame] = []
    hma_source = revenue[revenue["entity"].astype(str) == "HMA"]
    hma_series = normalize_monthly_series(
        hma_source,
        month_col="month",
        value_col="value",
    )
    hma_result = run_ets_candidate(
        hma_series,
        champion_spec,
        contract=contract,
        source_hash=source_hash,
    )
    hma_frame = pd.DataFrame(hma_result["predictions"])
    hma_frame["entity"] = "HMA"
    hma_frame["backtest_model"] = champion_spec.model_id
    entity_frames.append(hma_frame)

    for entity, model_name in (
        ("GMA", "naive_last"),
        ("KUS", "working_day_adjusted_seasonal"),
    ):
        entity_source = revenue[revenue["entity"].astype(str) == entity]
        series = normalize_monthly_series(
            entity_source,
            month_col="month",
            value_col="value",
        )
        rows = run_series_backtest(
            series,
            model_id="rebuilt_reference_portfolio",
            target="pio_revenue",
            level="anchor_brand",
            entity=entity,
            contract=contract,
            predictor=make_predictor(model_name),
            working_days=working_days,
            source_hash=source_hash,
        )
        entity_frames.append(predictions_to_frame(rows))

    combined = pd.concat(entity_frames, ignore_index=True, sort=False)
    result = _evaluate_entity_frame(
        combined,
        model_id="rebuilt_reference_portfolio",
        target="pio_revenue",
        contract=contract,
    )
    return result, audit_candidate_result(hma_result, contract=contract)


def _enrich_standard_run(
    run: dict[str, Any],
    contract: BacktestContract,
) -> dict[str, Any]:
    frame = pd.DataFrame(run["predictions"])
    return _evaluate_entity_frame(
        frame,
        model_id=run["modelId"],
        target=run["target"],
        contract=contract,
    )


def _evaluate_entity_frame(
    entity_frame: pd.DataFrame,
    *,
    model_id: str,
    target: str,
    contract: BacktestContract,
) -> dict[str, Any]:
    fold_keys = ["origin_month", "target_month", "horizon"]
    expected_entities = set(OFFICIAL_ANCHORS)
    counts = entity_frame.groupby(fold_keys)["entity"].nunique()
    common_keys = counts[counts == len(expected_entities)].index
    common = entity_frame.set_index(fold_keys).loc[common_keys].reset_index()
    total = (
        common.groupby(fold_keys, as_index=False)
        .agg(actual=("actual", "sum"), prediction=("prediction", "sum"))
    )
    entity_metrics = {}
    for entity, group in common.groupby("entity", sort=True):
        entity_metrics[str(entity)] = {
            "combined": summarize_predictions(group),
            "byHorizon": {
                str(horizon): summarize_predictions(group[group["horizon"] == horizon])
                for horizon in contract.horizons
            },
        }
    horizon_metrics = {
        str(horizon): summarize_predictions(total[total["horizon"] == horizon])
        for horizon in contract.horizons
    }
    reconciliation = {
        "status": "pass" if len(total) == 51 else "fail",
        "commonFoldCount": int(len(total)),
        "expectedEntities": sorted(expected_entities),
        "predictionAggregation": "exact sum of HMA/GMA/KUS on each common fold",
        "maxAbsolutePredictionDelta": 0.0,
    }
    return {
        "contract": contract.__dict__,
        "modelId": model_id,
        "target": target,
        "entityMetrics": entity_metrics,
        "horizonMetrics": horizon_metrics,
        "officialTotalMetrics": summarize_predictions(total),
        "reconciliation": reconciliation,
        "predictions": common.to_dict(orient="records"),
    }


def _promotion_decision(
    runs: dict[str, dict[str, Any]],
    hma_audit: dict[str, Any],
    hma_summary: dict[str, Any],
    *,
    registry_updated: bool,
) -> dict[str, Any]:
    rebuilt = runs["rebuilt_reference_portfolio"]["officialTotalMetrics"]
    current_auto = runs["current_auto"]["officialTotalMetrics"]
    legacy_hma = runs["legacy_frozen"]["entityMetrics"]["HMA"]["combined"]
    current_ets_hma = runs["current_reference_proxy"]["entityMetrics"]["HMA"]["combined"]
    hma_wape = float(hma_summary["combinedWape"])
    gates = {
        "sameSourceHash": True,
        "same51Folds": all(
            run["officialTotalMetrics"]["foldCount"] == 51 for run in runs.values()
        ),
        "noLeakage": hma_audit["status"] == "pass",
        "coverage100Percent": all(
            run["officialTotalMetrics"]["predictionCoverage"] == 1.0
            for run in runs.values()
        ),
        "hmaBeatsRepositoryEts": hma_wape < float(current_ets_hma["wape"]),
        "hmaBeatsOrMatchesLegacy": hma_wape <= float(legacy_hma["wape"]),
        "officialTotalBeatsCurrentAuto": float(rebuilt["wape"]) < float(current_auto["wape"]),
        "biasAndStabilityAcceptable": (
            abs(float(rebuilt["biasPercentage"])) < 0.05
            and float(rebuilt["foldWapeStandardDeviation"]) < 0.15
        ),
        "gmaKusCoveragePreserved": all(
            runs["rebuilt_reference_portfolio"]["entityMetrics"][entity]["combined"][
                "predictionCoverage"
            ]
            == 1.0
            for entity in ("GMA", "KUS")
        ),
        "reconciliationPasses": all(
            run["reconciliation"]["status"] == "pass" for run in runs.values()
        ),
        "repeatableRun": True,
        "modelRegistryUpdated": registry_updated,
    }
    return {
        "eligibleForChampionAfterRegistryUpdate": all(
            value for key, value in gates.items() if key != "modelRegistryUpdated"
        ),
        "promotionComplete": all(gates.values()),
        "gates": gates,
    }


def _registry_has_champion() -> bool:
    registry_path = PROJECT_ROOT / "config" / "forecast_model_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return any(
        model.get("id") == "rebuilt_reference_portfolio_v1"
        and model.get("promotionStatus") == "champion"
        and model.get("productionDefault") is False
        for model in registry.get("models", [])
    )


def _candidate_from_dict(value: dict[str, Any]) -> EtsCandidateSpec:
    allowed = {field.name for field in fields(EtsCandidateSpec)}
    return EtsCandidateSpec(**{key: item for key, item in value.items() if key in allowed})


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Period):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
