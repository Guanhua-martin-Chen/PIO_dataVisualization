from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pio_platform.backtest_harness import BacktestContract, select_champion  # noqa: E402
from pio_platform.ml_challengers import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    ELASTIC_NET_RESIDUAL_ID,
    TREE_META_SELECTOR_ID,
    save_ml_challenger_artifacts,
    train_ml_challengers,
)
from scripts.run_unified_backtest import (  # noqa: E402
    DEFAULT_SOURCE,
    load_governed_monthly,
    sha256_file,
)


REFERENCE_PORTFOLIO_WAPE = 0.06893887801948267
REFERENCE_PORTFOLIO_BIAS = 0.010737313740393228
REFERENCE_PORTFOLIO_STABILITY = 0.056316697141294746


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pretrain the two leakage-safe PR E Revenue challengers as CPU JSON artifacts."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--audit-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    governed = load_governed_monthly(source, source_hash, use_cache=True)
    contract = BacktestContract()
    artifacts = train_ml_challengers(
        governed["pioRevenue"],
        governed["workingDays"],
        source_hash=source_hash,
        training_cutoff=governed["completedTrainingThrough"],
        contract=contract,
    )
    candidates = {
        "rebuilt_reference_portfolio_v1": {
            "wape": REFERENCE_PORTFOLIO_WAPE,
            "biasPercentage": REFERENCE_PORTFOLIO_BIAS,
            "foldWapeStandardDeviation": REFERENCE_PORTFOLIO_STABILITY,
            "predictionCoverage": 1.0,
            "foldCount": 51,
        },
        **{
            model_id: artifact["evaluation"]["officialTotalMetrics"]
            for model_id, artifact in artifacts.items()
        },
    }
    selection = select_champion(
        candidates,
        tie_band_wape=contract.tie_band_wape,
        complexity={
            "rebuilt_reference_portfolio_v1": 4,
            TREE_META_SELECTOR_ID: 6,
            ELASTIC_NET_RESIDUAL_ID: 7,
        },
    )
    challenger_wapes = [
        float(artifact["evaluation"]["officialTotalMetrics"]["wape"])
        for artifact in artifacts.values()
    ]
    if all(
        challenger_wape >= REFERENCE_PORTFOLIO_WAPE
        for challenger_wape in challenger_wapes
    ):
        selection = {
            **selection,
            "champion": "rebuilt_reference_portfolio_v1",
            "reason": (
                "The validated reference portfolio has the lowest Official Total "
                "WAPE. The 0.005 simplicity band cannot promote a more complex "
                "challenger whose WAPE is worse."
            ),
        }
    for artifact in artifacts.values():
        artifact["comparison"] = {
            "referencePortfolioWape": REFERENCE_PORTFOLIO_WAPE,
            "sameSourceAndContract": True,
            "selection": selection,
        }
        artifact["promotionDecision"] = {
            "status": "not_promoted",
            "championAfterCommonFoldComparison": selection["champion"],
            "reason": (
                "Both ML methods remain explicit challengers. The website default "
                "and validated reference portfolio are unchanged."
            ),
        }
    audit_output = args.audit_output or (
        PROJECT_ROOT
        / "outputs"
        / "backtests"
        / f"ml_challengers_{source_hash[:12]}_{contract.version}.json"
    )
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(
        json.dumps(artifacts, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    written = save_ml_challenger_artifacts(
        artifacts,
        output_dir=args.output_dir.resolve(),
    )
    summary = {
        "source": str(source),
        "sourceHash": source_hash,
        "trainingCutoff": governed["completedTrainingThrough"],
        "artifacts": [str(path.resolve()) for path in written],
        "localFoldAudit": str(audit_output.resolve()),
        "metrics": {
            model_id: {
                "combined": artifact["evaluation"]["officialTotalMetrics"],
                "byHorizon": artifact["evaluation"]["horizonMetrics"],
                "foldAudit": artifact["evaluation"]["foldAudit"],
            }
            for model_id, artifact in artifacts.items()
        },
        "selection": selection,
        "gpuRequired": False,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
