"""Pure-Python logistic-regression baseline for PAPER-only model research.

The fitted model is a diagnostic shadow artifact. It never changes the
registered strategy sampler, paper wallet, or live execution (which is absent).
"""
import hashlib
import json
import math
import random


def _sigmoid(value):
    value = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _dot(weights, row):
    return sum(w*x for w, x in zip(weights, row))


def _standardize(rows, names, means=None, scales=None):
    matrix = [[float(row["features"][name]) for name in names] for row in rows]
    if means is None:
        means = [sum(x[j] for x in matrix)/len(matrix) for j in range(len(names))]
    if scales is None:
        scales = []
        for j, mean in enumerate(means):
            variance = sum((x[j]-mean)**2 for x in matrix)/len(matrix)
            scales.append(math.sqrt(variance) or 1.0)
    transformed = [[(x[j]-means[j])/scales[j] for j in range(len(names))]
                   for x in matrix]
    return transformed, means, scales


def _auc(labels, probabilities):
    positives = sum(labels)
    negatives = len(labels)-positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(probabilities, labels), key=lambda item:item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index+1)+end)/2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (rank_sum - positives*(positives+1)/2.0)/(positives*negatives)


def metrics(rows, probabilities, baseline_probability):
    labels = [int(row["label"]) for row in rows]
    if not rows:
        raise ValueError("INSUFFICIENT_DATA: empty evaluation rows")
    brier = sum((p-y)**2 for p,y in zip(probabilities,labels))/len(labels)
    eps = 1e-12
    logloss = -sum(y*math.log(max(eps,p)) +
                   (1-y)*math.log(max(eps,1-p))
                   for p,y in zip(probabilities,labels))/len(labels)
    baseline_brier = sum((baseline_probability-y)**2 for y in labels)/len(labels)
    return {
        "n": len(rows),
        "positive_rate": round(sum(labels)/len(labels), 6),
        "brier_score": round(brier, 8),
        "constant_base_rate_brier": round(baseline_brier, 8),
        "brier_skill_vs_constant": round(1-brier/baseline_brier, 8)
            if baseline_brier > 0 else None,
        "log_loss": round(logloss, 8),
        "accuracy_at_0_5": round(sum((p >= 0.5) == bool(y)
                                      for p,y in zip(probabilities,labels))/len(labels), 6),
        "roc_auc": round(_auc(labels, probabilities), 8)
            if _auc(labels, probabilities) is not None else None,
    }


def fit(train_rows, validation_rows, feature_names, *, max_epochs=30,
        batch_size=256, learning_rate=0.05, l2=0.001, patience=5, seed=17):
    """Fit standardized logistic regression with deterministic mini-batch GD."""
    if len(train_rows) < 30 or len(validation_rows) < 10:
        raise ValueError("INSUFFICIENT_DATA: logistic baseline sample too small")
    if not feature_names or max_epochs < 1 or batch_size < 1 or learning_rate <= 0:
        raise ValueError("MODEL_CONFIG_INVALID")
    train_labels = [int(row["label"]) for row in train_rows]
    validation_labels = [int(row["label"]) for row in validation_rows]
    if set(train_labels) != {0,1}:
        raise ValueError("INSUFFICIENT_DATA: training requires both classes")
    if set(validation_labels) != {0,1}:
        raise ValueError("INSUFFICIENT_DATA: validation requires both classes")

    x_train, means, scales = _standardize(train_rows, feature_names)
    x_validation, _, _ = _standardize(validation_rows, feature_names, means, scales)
    prevalence = sum(train_labels)/len(train_labels)
    bias = math.log(prevalence/(1-prevalence))
    weights = [0.0] * len(feature_names)
    best_weights, best_bias = list(weights), bias
    best_score = float("inf")
    best_epoch = 0
    stale_epochs = 0
    rng = random.Random(seed)
    order = list(range(len(train_rows)))

    for epoch in range(1, max_epochs+1):
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = order[start:start+batch_size]
            grad = [0.0] * len(feature_names)
            grad_bias = 0.0
            for index in batch:
                probability = _sigmoid(bias + _dot(weights, x_train[index]))
                error = probability - train_labels[index]
                grad_bias += error
                row = x_train[index]
                for j, value in enumerate(row):
                    grad[j] += error * value
            scale = 1.0/len(batch)
            bias -= learning_rate * grad_bias * scale
            for j in range(len(weights)):
                weights[j] -= learning_rate * (grad[j]*scale + l2*weights[j])

        probabilities = [_sigmoid(bias + _dot(weights,row))
                         for row in x_validation]
        score = sum((p-y)**2 for p,y in zip(probabilities,validation_labels))/len(validation_labels)
        if score < best_score - 1e-10:
            best_score = score
            best_weights, best_bias = list(weights), bias
            best_epoch = epoch
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    final_probabilities = [_sigmoid(best_bias + _dot(best_weights,row))
                           for row in x_validation]
    evaluation = metrics(validation_rows, final_probabilities, prevalence)
    model_body = {
        "schema": "paper-logistic-regression-v1",
        "feature_names": list(feature_names),
        "means": [round(x,12) for x in means],
        "scales": [round(x,12) for x in scales],
        "weights": [round(x,12) for x in best_weights],
        "bias": round(best_bias,12),
        "training_rows": len(train_rows),
        "training_positive_rate": round(prevalence,8),
        "best_epoch": best_epoch,
        "epochs_requested": max_epochs,
        "optimizer": "mini-batch gradient descent",
        "learning_rate": learning_rate,
        "l2": l2,
        "seed": seed,
    }
    model_id = hashlib.sha256(json.dumps(
        model_body,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode("utf-8")).hexdigest()
    return {
        "model": model_body,
        "model_id": model_id,
        "validation": evaluation,
        "validation_status": (
            "IMPROVES_BRIER_OVER_CONSTANT_BASE_RATE"
            if evaluation["brier_skill_vs_constant"] is not None and
               evaluation["brier_skill_vs_constant"] > 0
            else "NO_IMPROVEMENT_OVER_CONSTANT_BASE_RATE"
        ),
        "validation_predictions": [
            {"record_id":row["record_id"],"probability_positive_net_R":round(p,8)}
            for row,p in zip(validation_rows,final_probabilities)
        ],
        "shadow_only": True,
        "automatic_allocation_change": False,
        "live_orders": False,
        "not_an_alpha_proof": True,
    }


def predict(model, features):
    """Predict from an explicitly versioned model; no order/allocator action."""
    names = model["feature_names"]
    if any(name not in features for name in names):
        raise ValueError("FEATURE_INVALID: prediction schema mismatch")
    row = [(float(features[name])-mean)/scale
           for name,mean,scale in zip(names,model["means"],model["scales"])]
    if not all(math.isfinite(value) for value in row):
        raise ValueError("FEATURE_INVALID: nonfinite prediction input")
    return _sigmoid(model["bias"] + _dot(model["weights"],row))
