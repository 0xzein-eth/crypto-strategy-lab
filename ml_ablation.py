#!/usr/bin/env python3
"""Matched chronological feature ablations for shadow-only ML research.

All feature sets use identical horizon cohorts, chronological boundaries,
24-hour purges, train-only preprocessing and fixed model hyperparameters.
No model is promoted or connected to paper-trade allocation.
"""
import argparse
import json
from pathlib import Path
import ml_features
import ml_train

BASELINE = tuple(ml_train.NUMERIC)
FEATURE_SETS = {
    "baseline": BASELINE,
    **{name: tuple(dict.fromkeys(BASELINE + tuple(keys)))
       for name, keys in ml_features.FEATURE_GROUPS.items()},
    "all_engineered": tuple(dict.fromkeys(
        BASELINE + tuple(key for group in ml_features.FEATURE_GROUPS.values()
                         for key in group))),
}


def run_ablation(rows):
    results = []
    for horizon in ml_train.HORIZONS:
        cohort_n = sum(r["features"].get("horizon_hours") == horizon for r in rows)
        by_set = {}
        for name, fields in FEATURE_SETS.items():
            result = ml_train.train_horizon(rows, horizon, fields)
            by_set[name] = result
        baseline = by_set["baseline"]
        baseline_brier = ((baseline.get("test") or {}).get("model") or {}).get("brier")
        for name, result in by_set.items():
            model_brier = ((result.get("test") or {}).get("model") or {}).get("brier")
            result["feature_set"] = name
            result["numeric_features"] = list(FEATURE_SETS[name])
            result["test_brier_delta_vs_baseline"] = (
                round(model_brier - baseline_brier, 8)
                if model_brier is not None and baseline_brier is not None else None)
            result["matched_cohort_n"] = cohort_n
        results.append({"horizon_hours": horizon, "cohort_n": cohort_n,
                        "feature_sets": by_set})
    return {
        "version": "matched-feature-ablation-v1",
        "method": "same chronological cohort, 60/20/20 split, 24h purge, train-only preprocessing",
        "target": "net_profit_after_recorded_fees",
        "feature_policy": "OPEN_TIME_ONLY",
        "hyperparameters": {"epochs": 1200, "learning_rate": 0.05, "l2": 0.01},
        "promotion": "PROHIBITED_SHADOW_ONLY",
        "results": results,
        "interpretation": "Negative Brier delta is better than baseline; compare test and validation, and require stability across horizons. Predictive improvement is not proof of positive expectancy.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="/tmp/ml_dataset_features_v1.jsonl")
    parser.add_argument("--output", default="/tmp/ml_feature_ablation_v1.json")
    args = parser.parse_args(argv)
    rows = ml_train.load_rows(args.dataset)
    report = run_ablation(rows)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "horizons": len(report["results"]),
                      "feature_sets": list(FEATURE_SETS),
                      "promotion": report["promotion"]}, indent=2))


if __name__ == "__main__":
    main()
