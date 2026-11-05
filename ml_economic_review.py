#!/usr/bin/env python3
"""Evaluate walk-forward shadow predictions against after-fee outcomes."""
import argparse
import json
from pathlib import Path
import ml_train


def summarize(rows):
    if not rows:
        return {"n": 0, "win_rate": None, "brier": None, "mean_net_pnl_usd": None,
                "expectancy_R": None, "profit_factor": None, "max_drawdown_R": None}
    n = len(rows)
    pnl = [float(r["net_pnl_usd"]) for r in rows]
    gains = sum(x for x in pnl if x > 0)
    losses = -sum(x for x in pnl if x < 0)
    equity = peak = drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "n": n,
        "win_rate": sum(int(r["label_net_profit"]) for r in rows) / n,
        "mean_predicted_probability": sum(float(r["probability_net_profit"]) for r in rows) / n,
        "brier": sum((float(r["probability_net_profit"]) - int(r["label_net_profit"])) ** 2
                     for r in rows) / n,
        "net_pnl_usd": round(sum(pnl), 6),
        "mean_net_pnl_usd": round(sum(pnl) / n, 6),
        "expectancy_R": round(sum(float(r["normalized_R"]) for r in rows) / n, 8),
        "net_R": round(sum(float(r["normalized_R"]) for r in rows), 8),
        "profit_factor": round(gains / losses, 8) if losses else None,
        "max_drawdown_R": round(drawdown / 10000.0, 8),
    }


def bucket(probability):
    if probability < 0.40:
        return "<0.40"
    if probability < 0.50:
        return "0.40-0.50"
    if probability < 0.60:
        return "0.50-0.60"
    return ">=0.60"


def evaluate(predictions):
    ordered = sorted(predictions, key=lambda r: (r["entry_at"], r["horizon_hours"], r["sample_id"]))
    groups = {}
    horizons = sorted({int(r["horizon_hours"]) for r in ordered})
    for horizon in horizons:
        cohort = [r for r in ordered if int(r["horizon_hours"]) == horizon]
        groups[str(horizon)] = {
            "all_predictions": summarize(cohort),
            "probability_buckets": {
                name: summarize([r for r in cohort
                                 if bucket(float(r["probability_net_profit"])) == name])
                for name in ("<0.40", "0.40-0.50", "0.50-0.60", ">=0.60")
            },
        }
    return {
        "version": "walkforward-economic-review-v1",
        "prediction_count": len(ordered),
        "overall": summarize(ordered),
        "by_horizon": groups,
        "method_note": "Outcomes use recorded net P&L after simulated fees and normalized R. Buckets are predeclared descriptive calibration groups, not optimized trade filters.",
        "capital_note": "Overlapping research observations are not a funded portfolio; drawdown is a diagnostic over the ordered sample, not account equity.",
        "promotion": "PROHIBITED_SHADOW_ONLY",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", default="/tmp/ml_walkforward_predictions_v1.json")
    parser.add_argument("--output", default="/tmp/ml_walkforward_economic_review_v1.json")
    args = parser.parse_args(argv)
    source = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    report = evaluate(source.get("predictions", []))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"prediction_count": report["prediction_count"],
                      "overall": report["overall"],
                      "promotion": report["promotion"]}, indent=2))


if __name__ == "__main__":
    main()
