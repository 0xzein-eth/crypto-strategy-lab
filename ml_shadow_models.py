"""Deterministic PAPER-only Gradient Boosting and MLP shadow classifiers.

Both models predict positive post-cost fixed-horizon research R. They are
diagnostic artifacts only: no strategy selection, allocation, wallet, or
execution integration exists here.
"""
import hashlib
import json
import math
import random

import ml_baseline


def _validated_matrix(rows, feature_names):
    if not rows or not feature_names:
        raise ValueError("INSUFFICIENT_DATA: empty rows or feature schema")
    matrix, labels = [], []
    for row in rows:
        features = row.get("features")
        if not isinstance(features, dict):
            raise ValueError("FEATURE_INVALID: missing feature mapping")
        values = []
        for name in feature_names:
            value = features.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("FEATURE_INVALID: " + name)
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("FEATURE_INVALID: nonfinite " + name)
            values.append(value)
        label = row.get("label")
        if label not in (0, 1, False, True):
            raise ValueError("LABEL_INVALID")
        matrix.append(values)
        labels.append(int(label))
    return matrix, labels


def _standardize(train, other):
    means = [sum(row[j] for row in train) / len(train)
             for j in range(len(train[0]))]
    scales = []
    for j, mean in enumerate(means):
        variance = sum((row[j] - mean) ** 2 for row in train) / len(train)
        scales.append(math.sqrt(variance) or 1.0)
    def transform(rows):
        return [[(value - means[j]) / scales[j]
                 for j, value in enumerate(row)] for row in rows]
    return transform(train), transform(other), means, scales


def _probability(value):
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _model_id(body):
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _finish(model, validation_rows, probabilities, prevalence, status):
    evaluation = ml_baseline.metrics(validation_rows, probabilities, prevalence)
    return {
        "model": model,
        "model_id": _model_id(model),
        "validation": evaluation,
        "validation_status": (
            "IMPROVES_BRIER_OVER_CONSTANT_BASE_RATE"
            if evaluation["brier_skill_vs_constant"] is not None
            and evaluation["brier_skill_vs_constant"] > 0
            else "NO_IMPROVEMENT_OVER_CONSTANT_BASE_RATE"
        ),
        "validation_predictions": [
            {"record_id": row["record_id"],
             "probability_positive_net_R": round(p, 8)}
            for row, p in zip(validation_rows, probabilities)
        ],
        "shadow_only": True,
        "automatic_allocation_change": False,
        "live_orders": False,
        "not_an_alpha_proof": True,
        "fit_status": status,
    }


def fit_gradient_boosting(train_rows, validation_rows, feature_names, *,
                          rounds=24, learning_rate=0.05,
                          max_thresholds=12, min_leaf=12):
    """Fit shallow logistic-gradient boosting using deterministic decision stumps."""
    if len(train_rows) < 60 or len(validation_rows) < 20:
        raise ValueError("INSUFFICIENT_DATA: gradient boosting sample too small")
    if rounds < 1 or learning_rate <= 0 or max_thresholds < 2 or min_leaf < 2:
        raise ValueError("MODEL_CONFIG_INVALID")
    x_train_raw, y_train = _validated_matrix(train_rows, feature_names)
    x_valid_raw, y_valid = _validated_matrix(validation_rows, feature_names)
    if set(y_train) != {0, 1} or set(y_valid) != {0, 1}:
        raise ValueError("INSUFFICIENT_DATA: both classes required")
    x_train, x_valid, means, scales = _standardize(x_train_raw, x_valid_raw)
    prevalence = sum(y_train) / len(y_train)
    base_logit = math.log(prevalence / (1.0 - prevalence))
    scores = [base_logit] * len(y_train)
    stumps = []

    # Candidate thresholds and sorted row indices are derived once from
    # training data only. Prefix sums make each candidate split O(1) per
    # feature after one O(n) pass, avoiding O(features*thresholds*n) scans
    # inside every boosting round on the full research cohort.
    candidates = []
    sorted_indices = []
    for j in range(len(feature_names)):
        order = sorted(range(len(x_train)), key=lambda i: x_train[i][j])
        sorted_indices.append(order)
        ordered = [x_train[i][j] for i in order]
        thresholds = []
        for q in range(1, max_thresholds + 1):
            index = min(len(ordered) - 1,
                        int(q * len(ordered) / (max_thresholds + 1)))
            if index + 1 < len(ordered):
                threshold = (ordered[index] + ordered[index + 1]) / 2.0
                split_at = index + 1
                if ordered[index] == ordered[index + 1]:
                    # Quantile may land inside a repeated-value run. Match
                    # the original <= threshold partition by moving to the
                    # first value strictly above that repeated value.
                    while (split_at < len(ordered) and
                           ordered[split_at] <= threshold):
                        split_at += 1
                if not thresholds or threshold != thresholds[-1][0]:
                    thresholds.append((threshold, split_at))
        candidates.append(thresholds)

    for _ in range(rounds):
        probabilities = [_probability(score) for score in scores]
        residuals = [label - p for label, p in zip(y_train, probabilities)]
        total_sq = sum(value * value for value in residuals)
        best = None
        best_loss = float("inf")
        for j, thresholds in enumerate(candidates):
            if not thresholds:
                continue
            prefix_sum = [0.0]
            prefix_sq = [0.0]
            running_sum = running_sq = 0.0
            for row_index in sorted_indices[j]:
                value = residuals[row_index]
                running_sum += value
                running_sq += value * value
                prefix_sum.append(running_sum)
                prefix_sq.append(running_sq)
            total_sum = prefix_sum[-1]
            for threshold, split_at in thresholds:
                left_n = split_at
                right_n = len(residuals) - split_at
                if left_n < min_leaf or right_n < min_leaf:
                    continue
                left_sum = prefix_sum[split_at]
                right_sum = total_sum - left_sum
                left_sq = prefix_sq[split_at]
                right_sq = total_sq - left_sq
                loss = (left_sq - left_sum * left_sum / left_n +
                        right_sq - right_sum * right_sum / right_n)
                if loss < best_loss:
                    best_loss = loss
                    best = (j, threshold, left_sum / left_n,
                            right_sum / right_n)
        if best is None:
            break
        j, threshold, left_value, right_value = best
        stump = {"feature_index": j, "threshold": round(threshold, 12),
                 "left_value": round(left_value, 12),
                 "right_value": round(right_value, 12)}
        stumps.append(stump)
        for i, row in enumerate(x_train):
            scores[i] += learning_rate * (
                left_value if row[j] <= threshold else right_value)

    if not stumps:
        raise ValueError("INSUFFICIENT_DATA: no valid boosting split")
    valid_scores = [base_logit] * len(x_valid)
    for stump in stumps:
        j = stump["feature_index"]
        for i, row in enumerate(x_valid):
            valid_scores[i] += learning_rate * (
                stump["left_value"] if row[j] <= stump["threshold"]
                else stump["right_value"])
    probabilities = [_probability(score) for score in valid_scores]
    model = {
        "schema": "paper-gradient-boosting-stumps-v1",
        "feature_names": list(feature_names),
        "means": [round(v, 12) for v in means],
        "scales": [round(v, 12) for v in scales],
        "base_logit": round(base_logit, 12),
        "learning_rate": learning_rate,
        "rounds_requested": rounds,
        "rounds_fitted": len(stumps),
        "max_thresholds_per_feature": max_thresholds,
        "min_leaf": min_leaf,
        "stumps": stumps,
        "training_rows": len(train_rows),
        "training_positive_rate": round(prevalence, 8),
    }
    return _finish(model, validation_rows, probabilities, prevalence, "FITTED")


def predict_gradient_boosting(model, features):
    names = model["feature_names"]
    if any(name not in features for name in names):
        raise ValueError("FEATURE_INVALID: prediction schema mismatch")
    values = []
    for name, mean, scale in zip(names, model["means"], model["scales"]):
        value = float(features[name])
        if not math.isfinite(value):
            raise ValueError("FEATURE_INVALID: nonfinite prediction input")
        values.append((value - mean) / scale)
    score = model["base_logit"]
    for stump in model["stumps"]:
        j = stump["feature_index"]
        score += model["learning_rate"] * (
            stump["left_value"] if values[j] <= stump["threshold"]
            else stump["right_value"])
    return _probability(score)


def fit_mlp(train_rows, validation_rows, feature_names, *,
            hidden_units=16, max_epochs=30, batch_size=128,
            learning_rate=0.01, l2=0.0005, patience=6, seed=29):
    """Fit one-hidden-layer tanh MLP with explicit mini-batch backpropagation."""
    if len(train_rows) < 60 or len(validation_rows) < 20:
        raise ValueError("INSUFFICIENT_DATA: MLP sample too small")
    if (hidden_units < 2 or max_epochs < 1 or batch_size < 1 or
            learning_rate <= 0 or l2 < 0 or patience < 1):
        raise ValueError("MODEL_CONFIG_INVALID")
    x_train_raw, y_train = _validated_matrix(train_rows, feature_names)
    x_valid_raw, y_valid = _validated_matrix(validation_rows, feature_names)
    if set(y_train) != {0, 1} or set(y_valid) != {0, 1}:
        raise ValueError("INSUFFICIENT_DATA: both classes required")
    x_train, x_valid, means, scales = _standardize(x_train_raw, x_valid_raw)
    prevalence = sum(y_train) / len(y_train)
    bias_out = math.log(prevalence / (1.0 - prevalence))
    rng = random.Random(seed)
    n_features = len(feature_names)
    limit_in = math.sqrt(6.0 / (n_features + hidden_units))
    limit_out = math.sqrt(6.0 / (hidden_units + 1))
    w_in = [[rng.uniform(-limit_in, limit_in) for _ in range(n_features)]
            for _ in range(hidden_units)]
    b_hidden = [0.0] * hidden_units
    w_out = [rng.uniform(-limit_out, limit_out) for _ in range(hidden_units)]

    def forward(row):
        hidden = [math.tanh(b_hidden[h] + sum(
            w_in[h][j] * row[j] for j in range(n_features)))
            for h in range(hidden_units)]
        return hidden, _probability(bias_out + sum(
            w_out[h] * hidden[h] for h in range(hidden_units)))

    best = None
    best_score = float("inf")
    best_epoch = 0
    stale = 0
    order = list(range(len(x_train)))
    for epoch in range(1, max_epochs + 1):
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            gw_in = [[0.0] * n_features for _ in range(hidden_units)]
            gb_hidden = [0.0] * hidden_units
            gw_out = [0.0] * hidden_units
            gb_out = 0.0
            for index in batch:
                hidden, probability = forward(x_train[index])
                delta_out = probability - y_train[index]
                gb_out += delta_out
                for h in range(hidden_units):
                    gw_out[h] += delta_out * hidden[h]
                    delta_hidden = (delta_out * w_out[h] *
                                    (1.0 - hidden[h] * hidden[h]))
                    gb_hidden[h] += delta_hidden
                    for j in range(n_features):
                        gw_in[h][j] += delta_hidden * x_train[index][j]
            scale = 1.0 / len(batch)
            bias_out -= learning_rate * gb_out * scale
            for h in range(hidden_units):
                w_out[h] -= learning_rate * (
                    gw_out[h] * scale + l2 * w_out[h])
                b_hidden[h] -= learning_rate * gb_hidden[h] * scale
                for j in range(n_features):
                    w_in[h][j] -= learning_rate * (
                        gw_in[h][j] * scale + l2 * w_in[h][j])

        valid_probabilities = [forward(row)[1] for row in x_valid]
        score = sum((p-y)**2 for p, y in zip(valid_probabilities, y_valid)) / len(y_valid)
        if score < best_score - 1e-10:
            best_score = score
            best = ([list(row) for row in w_in], list(b_hidden),
                    list(w_out), bias_out)
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break

    w_in, b_hidden, w_out, bias_out = best
    probabilities = [forward(row)[1] for row in x_valid]
    model = {
        "schema": "paper-mlp-backprop-v1",
        "feature_names": list(feature_names),
        "means": [round(v, 12) for v in means],
        "scales": [round(v, 12) for v in scales],
        "hidden_units": hidden_units,
        "weights_input": [[round(v, 12) for v in row] for row in w_in],
        "bias_hidden": [round(v, 12) for v in b_hidden],
        "weights_output": [round(v, 12) for v in w_out],
        "bias_output": round(bias_out, 12),
        "optimizer": "mini-batch gradient descent with backpropagation",
        "learning_rate": learning_rate,
        "l2": l2,
        "batch_size": batch_size,
        "seed": seed,
        "best_epoch": best_epoch,
        "epochs_requested": max_epochs,
        "patience": patience,
        "training_rows": len(train_rows),
        "training_positive_rate": round(prevalence, 8),
    }
    return _finish(model, validation_rows, probabilities, prevalence, "FITTED")


def predict_mlp(model, features):
    names = model["feature_names"]
    if any(name not in features for name in names):
        raise ValueError("FEATURE_INVALID: prediction schema mismatch")
    row = []
    for name, mean, scale in zip(names, model["means"], model["scales"]):
        value = float(features[name])
        if not math.isfinite(value):
            raise ValueError("FEATURE_INVALID: nonfinite prediction input")
        row.append((value - mean) / scale)
    hidden = [math.tanh(model["bias_hidden"][h] + sum(
        model["weights_input"][h][j] * row[j] for j in range(len(names))))
        for h in range(model["hidden_units"])]
    return _probability(model["bias_output"] + sum(
        model["weights_output"][h] * hidden[h]
        for h in range(model["hidden_units"])))
