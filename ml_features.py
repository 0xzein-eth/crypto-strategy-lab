#!/usr/bin/env python3
"""OPEN-time feature engineering and availability audit for ML dataset v1.

Derived values use only evidence frozen at entry. Missing inputs remain null;
this module never imputes from outcomes or changes the canonical ledger.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import ml_train

FEATURE_GROUPS = {
    "trend": ("price_vs_sma20_pct", "price_vs_sma50_pct", "price_vs_vwap20_pct"),
    "momentum": ("rsi14_centered", "rsi14_delta", "z20"),
    "volatility": ("atr14_pct", "vol_ratio", "prior20_range_width"),
    "candle": ("wick_imbalance",),
}
CATEGORICAL = {"strategy", "side", "symbol", "regime", "cluster", "provider", "market_type", "horizon_hours"}


def finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _ratio(numerator, denominator):
    if not finite(numerator) or not finite(denominator) or float(denominator) == 0:
        return None
    return float(numerator) / float(denominator)


def derive_open_features(features):
    """Return normalized indicators; all inputs are OPEN-time feature fields."""
    close = features.get("last_close")
    rsi, previous_rsi = features.get("rsi14"), features.get("rsi14prev")
    upper, lower = features.get("upper_wick_ratio"), features.get("lower_wick_ratio")
    sma20, sma50, vwap = features.get("sma20"), features.get("sma50"), features.get("vwap20")
    atr_ratio = _ratio(features.get("atr14"), close)
    return {
        "price_vs_sma20_pct": 100 * (_ratio(close, sma20) - 1) if _ratio(close, sma20) is not None else None,
        "price_vs_sma50_pct": 100 * (_ratio(close, sma50) - 1) if _ratio(close, sma50) is not None else None,
        "price_vs_vwap20_pct": 100 * (_ratio(close, vwap) - 1) if _ratio(close, vwap) is not None else None,
        "rsi14_centered": float(rsi) - 50 if finite(rsi) else None,
        "rsi14_delta": float(rsi) - float(previous_rsi) if finite(rsi) and finite(previous_rsi) else None,
        "atr14_pct": 100 * atr_ratio if atr_ratio is not None else None,
        "z20": features.get("z20") if finite(features.get("z20")) else None,
        "vol_ratio": features.get("vol_ratio") if finite(features.get("vol_ratio")) else None,
        "prior20_range_width": features.get("prior20_range_width") if finite(features.get("prior20_range_width")) else None,
        "wick_imbalance": float(lower) - float(upper) if finite(lower) and finite(upper) else None,
    }


def augment_row(row):
    result = dict(row)
    result["features"] = dict(row["features"])
    result["features"].update(derive_open_features(row["features"]))
    result["derived_features_asof"] = row["features_asof"]
    return result


def audit_availability(rows):
    totals = Counter()
    missing = defaultdict(Counter)
    feature_keys = sorted({k for row in rows for k in row["features"]
                            if k not in CATEGORICAL})
    by_horizon = defaultdict(Counter)
    for row in rows:
        strategy = str(row["features"].get("strategy") or "__MISSING__")
        totals[strategy] += 1
        horizon = str(row["features"].get("horizon_hours"))
        by_horizon[horizon]["rows"] += 1
        for key in feature_keys:
            if row["features"].get(key) is None:
                missing[strategy][key] += 1
                by_horizon[horizon][key + "__missing"] += 1
    strategies = {}
    for strategy, n in sorted(totals.items()):
        feature_report = {}
        for key in feature_keys:
            count = missing[strategy][key]
            feature_report[key] = {"missing": count, "share": round(count / n, 6)}
        strategies[strategy] = {"n": n, "features": feature_report}
    return {
        "version": "ml-feature-availability-v1",
        "rows": len(rows),
        "features_are_open_time_only": True,
        "missing_values_imputed": False,
        "by_strategy": strategies,
        "by_horizon": {h: dict(values) for h, values in sorted(by_horizon.items())},
        "derived_feature_groups": {k: list(v) for k, v in FEATURE_GROUPS.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="artifacts/ml_dataset_v1.jsonl")
    parser.add_argument("--output", default="artifacts/ml_dataset_features_v1.jsonl")
    parser.add_argument("--report", default="artifacts/ml_feature_availability_v1.json")
    args = parser.parse_args()
    rows = ml_train.load_rows(args.dataset)
    augmented = [augment_row(row) for row in rows]
    report = audit_availability(augmented)
    output, report_path = Path(args.output), Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                              for row in augmented), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": report["rows"], "strategy_count": len(report["by_strategy"]),
                      "derived_features": sum(len(v) for v in FEATURE_GROUPS.values()),
                      "features_are_open_time_only": True}, indent=2))


if __name__ == "__main__":
    main()
