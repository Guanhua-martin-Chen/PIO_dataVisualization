from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pio_platform.backtest_harness import (  # noqa: E402
    CONTRACT_VERSION,
    BacktestContract,
)
from pio_platform.ets_experiments import (  # noqa: E402
    EtsCandidateSpec,
    audit_candidate_result,
    build_candidate_grid,
    compact_candidate_summary,
    repository_baselines,
    run_ets_candidate,
    select_ets_champion,
)


SOURCE_HASH = "f44048f30632e6f1d77d5336d2d313b4855e9d1cec95577b4a50f1c8f33c2c47"
DEFAULT_CACHE = (
    PROJECT_ROOT
    / "outputs"
    / "backtest_cache"
    / f"governed_monthly_{SOURCE_HASH}_{CONTRACT_VERSION}.pkl"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "outputs"
    / "backtests"
    / f"hma_ets_experiment_{SOURCE_HASH[:12]}_{CONTRACT_VERSION}.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run leakage-safe HMA Revenue ETS candidates on the governed 51-fold contract."
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--include-winsorized", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload, metadata = load_cache(args.cache)
    revenue = payload["pioRevenue"]
    hma = (
        revenue[revenue["entity"].astype(str) == "HMA"]
        .sort_values("month")
        .set_index("month")["value"]
        .astype(float)
    )
    if len(hma) != 42:
        raise RuntimeError(f"Expected 42 completed HMA months, found {len(hma)}.")

    preprocessing_modes = ["raw", "anomaly_softened"]
    if args.include_winsorized:
        preprocessing_modes.append("robust_winsorized")
    candidates = repository_baselines() + build_candidate_grid(
        preprocessing_modes=preprocessing_modes
    )
    if args.smoke:
        candidates = repository_baselines() + [
            candidate
            for candidate in candidates
            if candidate.implementation == "statsmodels_holtwinters"
            and candidate.initialization_method == "estimated"
            and not candidate.remove_bias
            and candidate.transform == "raw"
            and candidate.training_window == "expanding"
            and candidate.preprocessing == "raw"
        ]

    contract = BacktestContract()
    started = time.perf_counter()
    results = run_candidates(
        hma,
        candidates,
        contract=contract,
        source_hash=metadata["sourceHash"],
        workers=max(int(args.workers), 1),
    )
    audits = {
        result["modelId"]: audit_candidate_result(result, contract=contract)
        for result in results
    }
    failed_audits = [
        model_id for model_id, audit in audits.items() if audit["status"] != "pass"
    ]
    if failed_audits:
        raise RuntimeError(f"Leakage/fold audit failed for: {failed_audits[:5]}")

    selection = select_ets_champion(results, tie_band_wape=contract.tie_band_wape)
    summaries = [compact_candidate_summary(result) for result in results]
    summaries.sort(
        key=lambda item: (
            float("inf") if item["combinedWape"] is None else item["combinedWape"],
            item["modelId"],
        )
    )
    output = {
        "contractVersion": contract.version,
        "contract": contract.__dict__,
        "source": {
            "sha256": metadata["sourceHash"],
            "cachePath": str(args.cache.resolve()),
            "cacheContractVersion": metadata["contractVersion"],
            "actualThrough": payload.get("actualThrough"),
            "completedTrainingThrough": payload.get("completedTrainingThrough"),
            "rawExcelRead": False,
        },
        "experiment": {
            "target": "pio_revenue",
            "entity": "HMA",
            "observedMonths": len(hma),
            "candidateCount": len(results),
            "preprocessingModes": preprocessing_modes,
            "trueMultiStepForecast": True,
            "runtimeSeconds": float(time.perf_counter() - started),
        },
        "selection": selection,
        "topCandidates": summaries[:25],
        "candidateSummaries": summaries,
        "audits": audits,
        "candidates": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "candidateCount": len(results),
                "selection": selection,
                "topFive": summaries[:5],
                "runtimeSeconds": output["experiment"]["runtimeSeconds"],
            },
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        ),
        flush=True,
    )
    return 0


def load_cache(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    with path.resolve().open("rb") as handle:
        cached = pickle.load(handle)
    source_hash = str(cached.get("sourceHash") or "")
    contract_version = str(cached.get("contractVersion") or "")
    if source_hash != SOURCE_HASH:
        raise RuntimeError(f"Cache source hash mismatch: {source_hash}")
    if contract_version != CONTRACT_VERSION:
        raise RuntimeError(f"Cache contract mismatch: {contract_version}")
    payload = cached.get("payload")
    if not isinstance(payload, dict) or "pioRevenue" not in payload:
        raise RuntimeError("Cache payload does not contain governed pioRevenue.")
    return payload, {
        "sourceHash": source_hash,
        "contractVersion": contract_version,
    }


def run_candidates(
    series: pd.Series,
    candidates: list[EtsCandidateSpec],
    *,
    contract: BacktestContract,
    source_hash: str,
    workers: int,
) -> list[dict[str, Any]]:
    if workers == 1:
        results: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates, start=1):
            results.append(
                run_ets_candidate(
                    series,
                    candidate,
                    contract=contract,
                    source_hash=source_hash,
                )
            )
            if index == 1 or index % 25 == 0 or index == len(candidates):
                print(f"completed {index}/{len(candidates)} candidates", flush=True)
        return results

    results = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_ets_candidate,
                series,
                candidate,
                contract=contract,
                source_hash=source_hash,
            ): candidate.model_id
            for candidate in candidates
        }
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index == 1 or index % 25 == 0 or index == len(candidates):
                print(f"completed {index}/{len(candidates)} candidates", flush=True)
    results.sort(key=lambda item: item["modelId"])
    return results


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
