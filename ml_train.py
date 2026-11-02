#!/usr/bin/env python3
"""Deterministic, standard-library logistic regression baseline for ML dataset v1.

Chronological holdout with a 24h purge gap. Each horizon is trained separately.
Features are OPEN-time only. Model is research/shadow output, never an allocator.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

HORIZONS = (1, 2, 4, 8, 12, 24)
NUMERIC = ("price_change_24h_pct", "quote_volume_24h")
CATEGORICAL = ("strategy", "side", "symbol", "regime", "cluster", "provider")


def parse_time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("entry timestamp must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def load_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError("blank dataset row at line %d" % number)
            row = json.loads(line)
            if row.get("dataset_version") != "ml-dataset-v1":
                raise ValueError("unsupported dataset version")
            if row.get("features_asof") != row.get("entry_at"):
                raise ValueError("feature timestamp is not entry-frozen")
            rows.append(row)
    return rows


def metrics(probabilities, labels):
    eps = 1e-12
    n = len(labels)
    if not n:
        return None
    clipped = [min(1-eps, max(eps, p)) for p in probabilities]
    return {
        "n": n,
        "prevalence": sum(labels) / n,
        "brier": sum((p-y)**2 for p, y in zip(probabilities, labels)) / n,
        "log_loss": -sum(y*math.log(p)+(1-y)*math.log(1-p)
                         for p, y in zip(clipped, labels)) / n,
        "accuracy_at_0_5": sum((p >= 0.5) == bool(y)
                               for p, y in zip(probabilities, labels)) / n,
    }


def encode_fit(train):
    """Fit imputation/scaling and one-hot vocabulary on training rows only."""
    numeric_stats = {}
    categories = {}
    for key in NUMERIC:
        values = [float(r["features"][key]) for r in train
                  if isinstance(r["features"].get(key), (int, float))
                  and math.isfinite(float(r["features"][key]))]
        mean = sum(values)/len(values) if values else 0.0
        variance = sum((v-mean)**2 for v in values)/len(values) if values else 0.0
        scale = math.sqrt(variance) or 1.0
        numeric_stats[key] = (mean, scale)
    for key in CATEGORICAL:
        categories[key] = sorted({str(r["features"].get(key) or "__MISSING__")
                                  for r in train})
    columns = ["intercept"]
    columns += [key for key in NUMERIC]
    columns += [key + "__missing" for key in NUMERIC]
    for key in CATEGORICAL:
        columns += [key + "=" + value for value in categories[key]]
        columns += [key + "=__UNKNOWN__"]
    return {"numeric": numeric_stats, "categories": categories, "columns": columns}


def encode(row, schema):
    features = row["features"]
    vector = [1.0]
    for key in NUMERIC:
        value = features.get(key)
        missing = not isinstance(value, (int, float)) or not math.isfinite(float(value))
        mean, scale = schema["numeric"][key]
        vector.append(0.0 if missing else (float(value)-mean)/scale)
        vector.append(1.0 if missing else 0.0)
    for key in CATEGORICAL:
        value = str(features.get(key) or "__MISSING__")
        known = schema["categories"][key]
        vector.extend(1.0 if value == item else 0.0 for item in known)
        vector.append(1.0 if value not in known else 0.0)
    return vector


def sigmoid(value):
    if value >= 0:
        z = math.exp(-min(value, 700))
        return 1.0/(1.0+z)
    z = math.exp(max(value, -700))
    return z/(1.0+z)


def fit_logistic(matrix, labels, learning_rate=0.05, epochs=1200, l2=0.01):
    """Full-batch gradient descent with fixed, predeclared hyperparameters."""
    width = len(matrix[0])
    weights = [0.0] * width
    n = len(labels)
    for _ in range(epochs):
        gradient = [0.0] * width
        for row, target in zip(matrix, labels):
            error = sigmoid(sum(w*x for w, x in zip(weights, row))) - target
            for j, value in enumerate(row):
                gradient[j] += error * value
        for j in range(width):
            gradient[j] = gradient[j]/n + (l2*weights[j] if j else 0.0)
            weights[j] -= learning_rate * gradient[j]
    return weights


def predict(matrix, weights):
    return [sigmoid(sum(w*x for w, x in zip(weights, row))) for row in matrix]


def split_chronologically(rows, purge_hours=24):
    """60% train, 20% validation, 20% test; purge 24h at each boundary."""
    ordered = sorted(rows, key=lambda r: (parse_time(r["entry_at"]), r["sample_id"]))
    n = len(ordered)
    train_end = int(n * 0.60)
    valid_end = int(n * 0.80)
    if train_end == 0 or valid_end <= train_end or valid_end >= n:
        return None
    valid_start_time = parse_time(ordered[train_end]["entry_at"]) + dt.timedelta(hours=purge_hours)
    test_start_time = parse_time(ordered[valid_end]["entry_at"]) + dt.timedelta(hours=purge_hours)
    train = ordered[:train_end]
    validation = [r for r in ordered[train_end:valid_end]
                  if parse_time(r["entry_at"]) >= valid_start_time]
    test = [r for r in ordered[valid_end:]
            if parse_time(r["entry_at"]) >= test_start_time]
    return train, validation, test


def train_horizon(rows, horizon):
    cohort = [r for r in rows if r["features"].get("horizon_hours") == horizon]
    split = split_chronologically(cohort)
    if split is None:
        return {"horizon_hours": horizon, "status": "INSUFFICIENT_DATA",
                "n_total": len(cohort), "reason": "not enough chronological rows"}
    train, validation, test = split
    if len(train) < 50 or len(validation) < 20 or len(test) < 20:
        return {"horizon_hours": horizon, "status": "INSUFFICIENT_DATA",
                "n_total": len(cohort), "n_train": len(train),
                "n_validation": len(validation), "n_test": len(test),
                "reason": "minimum sample threshold not met"}
    y_train = [int(r["labels"]["net_profit"]) for r in train]
    if len(set(y_train)) < 2:
        return {"horizon_hours": horizon, "status": "INSUFFICIENT_DATA",
                "n_total": len(cohort), "reason": "training labels contain one class"}
    schema = encode_fit(train)
    weights = fit_logistic([encode(r, schema) for r in train], y_train)
    y_valid = [int(r["labels"]["net_profit"]) for r in validation]
    y_test = [int(r["labels"]["net_profit"]) for r in test]
    p_valid = predict([encode(r, schema) for r in validation], weights)
    p_test = predict([encode(r, schema) for r in test], weights)
    # A no-skill baseline uses training prevalence; no threshold is optimized.
    prevalence = sum(y_train)/len(y_train)
    base_valid = [prevalence] * len(y_valid)
    base_test = [prevalence] * len(y_test)
    return {
        "horizon_hours": horizon, "status": "TRAINED_SHADOW_BASELINE",
        "n_total": len(cohort), "n_train": len(train),
        "n_validation": len(validation), "n_test": len(test),
        "purge_gap_hours": 24,
        "feature_columns": schema["columns"],
        "training_prevalence": prevalence,
        "validation": {"model": metrics(p_valid, y_valid),
                       "no_skill": metrics(base_valid, y_valid)},
        "test": {"model": metrics(p_test, y_test),
                 "no_skill": metrics(base_test, y_test)},
        "model": {"type": "logistic_regression", "optimizer": "full_batch_gradient_descent",
                  "epochs": 1200, "learning_rate": 0.05, "l2": 0.01,
                  "weights": [round(w, 12) for w in weights]},
        "promotion": "PROHIBITED_SHADOW_ONLY",
    }


def run(rows):
    results = [train_horizon(rows, horizon) for horizon in HORIZONS]
    return {
        "model_version": "logistic-baseline-v1",
        "method": "chronological_60_20_20_with_24h_boundary_purge",
        "target": "net_profit_after_recorded_fees",
        "feature_policy": "OPEN_TIME_ONLY",
        "hyperparameters_predeclared": True,
        "results": results,
        "trained_horizons": sum(r["status"] == "TRAINED_SHADOW_BASELINE" for r in results),
        "promotion": "PROHIBITED_SHADOW_ONLY",
        "warning": "Predictive metrics are not trading edge; no strategy selection or orders.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="artifacts/ml_dataset_v1.jsonl")
    parser.add_argument("--output", default="artifacts/ml_logistic_baseline_v1.json")
    args = parser.parse_args(argv)
    rows = load_rows(args.dataset)
    report = run(rows)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "results"}, indent=2))
    for result in report["results"]:
        print(json.dumps({k:v for k,v in result.items() if k != "model"}, sort_keys=True))


if __name__ == "__main__":
    main()
