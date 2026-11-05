#!/usr/bin/env python3
"""Rolling walk-forward shadow predictions using only already-matured labels.

This is a historical walk-forward simulation, not an immutable live prediction
ledger. A weekly model snapshot predicts that week's OPEN rows using only
same-horizon rows whose public exit observation had matured before week start.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import ml_features
import ml_train

NUMERIC = tuple(dict.fromkeys(
    ml_train.NUMERIC + tuple(k for group in ml_features.FEATURE_GROUPS.values()
                             for k in group)))
MODEL_VERSION = "walkforward-logistic-shadow-v1"
MAX_TRAIN_ROWS = 1500
EPOCHS = 120
LEARNING_RATE = 0.03
L2 = 0.01


def week_start(value):
    parsed = ml_train.parse_time(value)
    monday = parsed.date() - dt.timedelta(days=parsed.weekday())
    return dt.datetime.combine(monday, dt.time.min, tzinfo=dt.timezone.utc)


def matured_training_rows(rows, horizon, cutoff):
    cutoff = ml_train.parse_time(cutoff)
    selected = []
    for row in rows:
        if row["features"].get("horizon_hours") != horizon:
            continue
        try:
            entry = ml_train.parse_time(row["entry_at"])
            exit_observed = ml_train.parse_time(row["labels"]["exit_observed_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if entry < cutoff and exit_observed < cutoff:
            selected.append(row)
    return sorted(selected, key=lambda r: (r["entry_at"], r["sample_id"]))


def run(rows):
    predictions = []
    skipped = []
    for horizon in ml_train.HORIZONS:
        cohort = [r for r in rows if r["features"].get("horizon_hours") == horizon]
        weeks = sorted({week_start(r["entry_at"]) for r in cohort})
        for cutoff in weeks:
            batch = [r for r in cohort if week_start(r["entry_at"]) == cutoff]
            train = matured_training_rows(cohort, horizon, cutoff)[-MAX_TRAIN_ROWS:]
            labels = [int(r["labels"]["net_profit"]) for r in train]
            if len(train) < 50 or len(set(labels)) < 2:
                skipped.append({"horizon_hours": horizon, "week_start": cutoff.isoformat(),
                                "train_n": len(train), "prediction_n": len(batch),
                                "reason": "insufficient matured training cohort"})
                continue
            schema = ml_train.encode_fit(train, NUMERIC)
            matrix = [ml_train.encode(r, schema, NUMERIC) for r in train]
            weights = ml_train.fit_logistic(matrix, labels, learning_rate=LEARNING_RATE,
                                            epochs=EPOCHS, l2=L2)
            probabilities = ml_train.predict(
                [ml_train.encode(r, schema, NUMERIC) for r in batch], weights)
            for row, probability in zip(batch, probabilities):
                predictions.append({
                    "sample_id": row["sample_id"],
                    "horizon_hours": horizon,
                    "entry_at": row["entry_at"],
                    "prediction_timestamp": row["entry_at"],
                    "evaluate_at": row["evaluate_at"],
                    "training_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
                    "training_sample_n": len(train),
                    "model_version": MODEL_VERSION,
                    "probability_net_profit": round(probability, 10),
                    "label_net_profit": int(row["labels"]["net_profit"]),
                    "net_pnl_usd": row["labels"]["net_pnl_usd"],
                    "normalized_R": row["labels"]["normalized_R"],
                    "strategy": row["features"].get("strategy"),
                    "side": row["features"].get("side"),
                    "regime": row["features"].get("regime"),
                    "historical_walkforward_simulation": True,
                })
    predictions.sort(key=lambda r: (r["entry_at"], r["horizon_hours"], r["sample_id"]))
    return {
        "version": MODEL_VERSION,
        "method": "weekly_rolling_walkforward; train labels exit_observed_at strictly before prediction-week start",
        "feature_policy": "OPEN_TIME_ONLY",
        "numeric_features": list(NUMERIC),
        "hyperparameters": {"epochs": EPOCHS, "learning_rate": LEARNING_RATE, "l2": L2, "max_matured_training_rows": MAX_TRAIN_ROWS},
        "prediction_count": len(predictions),
        "skipped_batches": skipped,
        "predictions": predictions,
        "promotion": "PROHIBITED_SHADOW_ONLY",
        "warning": "Retrospective simulation only. These are not live predictions frozen into the canonical OPEN ledger.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="/tmp/ml_dataset_features_v1.jsonl")
    parser.add_argument("--output", default="/tmp/ml_walkforward_predictions_v1.json")
    args = parser.parse_args(argv)
    rows = ml_train.load_rows(args.dataset)
    report = run(rows)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "predictions"}, indent=2))


if __name__ == "__main__":
    main()
