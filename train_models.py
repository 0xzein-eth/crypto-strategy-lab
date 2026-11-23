"""Train leakage-aware PAPER-only diagnostic and shadow models from the verified ledger."""
import argparse
import datetime as dt
import json
from pathlib import Path

import dataset_builder
import ml_baseline
import ml_shadow_models


def _model_record(trained):
    return {
        "model": trained["model"],
        "model_id": trained["model_id"],
        "validation": trained["validation"],
        "validation_status": trained["validation_status"],
        "validation_predictions": trained["validation_predictions"],
        "shadow_only": True,
        "automatic_allocation_change": False,
        "live_orders": False,
        "not_an_alpha_proof": True,
    }


def _comparison(models, validation_rows, training_prevalence):
    """Compare all fitted models against identical validation rows and a train-rate constant."""
    baseline_predictions = [
        {"record_id": row["record_id"],
         "probability_positive_net_R": round(training_prevalence, 8)}
        for row in validation_rows
    ]
    baseline_metrics = ml_baseline.metrics(
        validation_rows, [training_prevalence] * len(validation_rows),
        training_prevalence)
    comparison = {
        "evaluation_rows": len(validation_rows),
        "validation_record_ids_sha256": __import__("hashlib").sha256(
            "\n".join(row["record_id"] for row in validation_rows).encode("utf-8")
        ).hexdigest(),
        "constant_training_prevalence": round(training_prevalence, 8),
        "constant_baseline": {
            "validation": baseline_metrics,
            "validation_predictions": baseline_predictions,
            "role": "NON_LEARNED_REFERENCE",
        },
        "models": {},
        "metric_directions": {
            "brier_score": "lower_is_better",
            "log_loss": "lower_is_better",
            "roc_auc": "higher_is_better",
            "accuracy_at_0_5": "higher_is_better",
        },
        "promotion_decision": "NONE_DIAGNOSTIC_ONLY",
        "historical_validation_previously_inspected": True,
        "validation_is_pristine_holdout": False,
    }
    logistic_metrics = models.get("logistic_regression", {}).get("validation")
    for name, record in models.items():
        metrics = record.get("validation")
        if not metrics:
            comparison["models"][name] = {
                "status": record.get("status", "NOT_FITTED"),
                "reason": record.get("reason"),
            }
            continue
        comparison["models"][name] = {
            "status": "EVALUATED",
            "validation": metrics,
            "delta_brier_vs_constant": round(
                metrics["brier_score"] - baseline_metrics["brier_score"], 8),
            "delta_log_loss_vs_constant": round(
                metrics["log_loss"] - baseline_metrics["log_loss"], 8),
            "delta_brier_vs_logistic": (
                round(metrics["brier_score"] - logistic_metrics["brier_score"], 8)
                if logistic_metrics else None),
            "delta_log_loss_vs_logistic": (
                round(metrics["log_loss"] - logistic_metrics["log_loss"], 8)
                if logistic_metrics else None),
            "delta_roc_auc_vs_logistic": (
                round(metrics["roc_auc"] - logistic_metrics["roc_auc"], 8)
                if logistic_metrics and metrics["roc_auc"] is not None
                and logistic_metrics["roc_auc"] is not None else None),
            "beats_constant_on_brier": (
                metrics["brier_score"] < baseline_metrics["brier_score"]),
            "beats_logistic_on_brier": (
                metrics["brier_score"] < logistic_metrics["brier_score"]
                if logistic_metrics else None),
        }
    return comparison


def run(output=None, max_epochs=30):
    import engine

    records, event_count, ledger_tip, next_id = engine.replay()
    dataset = dataset_builder.build_dataset(records)
    result = {
        "schema": "paper-ml-shadow-research-report-v2",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_ledger_events": event_count,
        "source_ledger_tip_sha256": ledger_tip,
        "source_ledger_next_id": next_id,
        "dataset": {key: value for key, value in dataset.items()
                    if key != "examples"},
        "model_purpose": "predict positive post-cost fixed-horizon research R",
        "models": {},
        "paper_only": True,
        "automatic_allocation_change": False,
        "real_orders": False,
        "live_deployment_allowed": False,
        "historical_validation_previously_inspected": True,
        "independent_future_holdout_completed": False,
        "candidate_promotion": False,
    }
    try:
        split = dataset_builder.chronological_split(dataset)
        result["split"] = {key: value for key, value in split.items()
                           if key not in ("train", "validation")}
        result["training_rows"] = len(split["train"])
        result["validation_rows"] = len(split["validation"])
        result["training_positive_rate"] = (
            sum(int(row["label"]) for row in split["train"]) /
            len(split["train"]))
        trainers = {
            "logistic_regression": lambda: ml_baseline.fit(
                split["train"], split["validation"], dataset["feature_names"],
                max_epochs=max_epochs),
            "gradient_boosting": lambda: ml_shadow_models.fit_gradient_boosting(
                split["train"], split["validation"], dataset["feature_names"]),
            "mlp_backprop": lambda: ml_shadow_models.fit_mlp(
                split["train"], split["validation"], dataset["feature_names"],
                max_epochs=max_epochs),
        }
        failures = {}
        for name, trainer in trainers.items():
            try:
                trained = trainer()
                result["models"][name] = _model_record(trained)
            except (ValueError, ArithmeticError, OverflowError) as exc:
                failures[name] = str(exc)
                result["models"][name] = {
                    "status": "INSUFFICIENT_OR_INVALID_DATA",
                    "reason": str(exc),
                    "shadow_only": True,
                    "automatic_allocation_change": False,
                    "live_orders": False,
                }
        result["model_training_failures"] = failures
        result["comparison"] = _comparison(
            result["models"], split["validation"],
            result["training_positive_rate"])
        logistic = result["models"]["logistic_regression"]
        if "model" in logistic:
            # Preserve the original report fields for existing consumers.
            result["model_family"] = "logistic_regression"
            result["model"] = logistic["model"]
            result["model_id"] = logistic["model_id"]
            result["validation"] = logistic["validation"]
            result["validation_status"] = logistic["validation_status"]
            result["validation_predictions"] = logistic["validation_predictions"]
        trained_count = sum("model" in item for item in result["models"].values())
        result["status"] = (
            "SHADOW_MODELS_TRAINED_DIAGNOSTIC_ONLY"
            if trained_count else "INSUFFICIENT_OR_INVALID_DATA")
        result["trained_model_count"] = trained_count
        result["independent_future_holdout_completed"] = False
        result["candidate_promotion"] = False
    except ValueError as exc:
        result["status"] = "INSUFFICIENT_OR_INVALID_DATA"
        result["reason"] = str(exc)
        result["independent_future_holdout_completed"] = False
        result["candidate_promotion"] = False

    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True,
                                   allow_nan=False) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="research_results/ml_shadow_report.json")
    parser.add_argument("--max-epochs", type=int, default=30)
    args = parser.parse_args()
    result = run(args.output, args.max_epochs)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("validation_predictions", "models")},
                     indent=2, sort_keys=True))
    if result["status"] == "INSUFFICIENT_OR_INVALID_DATA":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
